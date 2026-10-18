#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fair_allocator.py — векторная упаковка квоты по подразделениям
(замена _perform_distribution-жадности + _balance_by_per_person_load).

Модель стоимости идентична ResourceSplitter:
  - per_9   -> неделимые чанки по 9, скидка цикла 9 (S = _discounted_sum);
  - per_person -> чанки по 5, скидка цикла 5;
  - per_4   -> чанки по 4 БЕЗ скидки (как в _calculate_totals: else-ветка);
              при enforce_mul4=False — поштучно;
  - остальное (per_person_one и т.п.) -> поштучно, полная цена.
  Бесплатные ресурсы (count_resource_cost(name, r) == False) входят в вектор
  чанка НОМИНАЛОМ — это комбинированная метрика _combined_load_for_resource:
  бесплатное тоже делится по справедливости.

Скидочная кривая циклична с периодом g, поэтому S(a)+S(b) == S(a+b) при
чанках, кратных g: стоимость чанка не зависит от места назначения, и задача
становится чистой векторной упаковкой на машинах со "скоростями" p_i.

Алгоритм:
  1. BFD — чанки по убыванию нормированного веса, каждый в argmin прироста
     потенциала J = Σ_r Σ_i ((L_ir/p_i − μ_r)/μ_r)².
  2. Локальный поиск — лучший из всех переносов/обменов, пока J падает.
     J строго убывает => завершение гарантировано (плюс time_budget).

preload — уже занятые нагрузки (глыбы группы 8 / only_one, размещённые
старой логикой ДО вызова): участвуют в μ и в J, но не двигаются, так что
обычные предметы выравниваются ВОКРУГ них.
"""

import math
import time
from collections import defaultdict

CHUNK = {"per_4": 4, "per_9": 9, "per_person": 5}
DISCOUNT_G = {"per_9": 9, "per_person": 5}   # per_4 в модели приложения без скидки


def discounted_sum(base, count, g):
    """Кумулятивная стоимость count коробок при цикле скидки g
    (== ResourceSplitter._discounted_sum(..., per_box_round='floor'))."""
    return float(sum(
        math.floor(base * (1 - min(((k % g) + 1) * 0.1, 0.5)))
        for k in range(count)
    ))


def make_chunks(quota, resource_db, count_resource_cost=None, enforce_mul4=True):
    """
    quota: [(canonical_name, cnt)] -> [(name, boxes, {resource: cost_float})].
    count_resource_cost(name, r) -> bool; False => ресурс бесплатный,
    в вектор идёт номинал (комбинированная метрика).
    Округление до кратности чанка — как в normalized_entries.
    """
    chunks = []
    for name, cnt in quota:
        e = resource_db.get(name)
        if not e:
            continue
        dist = e.get("distribution", "per_person")
        res, cost = e.get("resource"), e.get("cost_per_box")
        if res is None or cost is None:
            continue
        pairs = list(zip(res, cost)) if isinstance(res, list) else [(res, cost)]

        step = CHUNK.get(dist)
        if dist == "per_4" and not enforce_mul4:
            step = None
        g = DISCOUNT_G.get(dist)

        if step:
            cnt = int(math.ceil(cnt / step) * step)
            sizes = [step] * (cnt // step)
        else:
            sizes = [1] * cnt

        for sz in sizes:
            vec = {}
            for r, c in pairs:
                paid = count_resource_cost(name, r) if count_resource_cost else True
                if paid and g:
                    v = discounted_sum(c, sz, g)
                else:
                    v = float(c * sz)          # полная цена / номинал бесплатного
                vec[r] = vec.get(r, 0.0) + v
            chunks.append((name, sz, vec))
    return chunks


def allocate(chunks, people, preload=None, time_budget=0.5):
    """
    Возвращает (loads, assign):
      loads  — [{resource: cost}] по подразделениям, ВКЛЮЧАЯ preload;
      assign — индекс подразделения для каждого чанка.
    """
    m = len(people)
    L = [defaultdict(float) for _ in range(m)]
    if preload:
        for i, d in enumerate(preload):
            for r, v in d.items():
                L[i][r] += v

    totals = defaultdict(float)
    for i in range(m):
        for r, v in L[i].items():
            totals[r] += v
    for _, _, vec in chunks:
        for r, v in vec.items():
            totals[r] += v

    total_people = sum(people) or 1
    mu = {r: t / total_people for r, t in totals.items() if t > 0}
    assign = [0] * len(chunks)
    if not chunks or m == 0:
        return L, assign

    def dJ_add(i, vec):
        d = 0.0
        for r, v in vec.items():
            m_r = mu.get(r)
            if not m_r:
                continue
            x0 = L[i][r] / people[i]
            x1 = x0 + v / people[i]
            d += ((x1 - m_r) ** 2 - (x0 - m_r) ** 2) / (m_r * m_r)
        return d

    # --- шаг 1: BFD (камни первыми) ---
    order = sorted(
        range(len(chunks)),
        key=lambda ci: -sum(v / mu[r] for r, v in chunks[ci][2].items() if r in mu),
    )
    for ci in order:
        vec = chunks[ci][2]
        best = min(range(m),
                   key=lambda i: (dJ_add(i, vec), sum(L[i].values()) / people[i]))
        assign[ci] = best
        for r, v in vec.items():
            L[best][r] += v

    # --- шаг 2: локальный поиск (best move / best swap) ---
    def J_now():
        j = 0.0
        for r, m_r in mu.items():
            for i in range(m):
                j += ((L[i][r] / people[i] - m_r) / m_r) ** 2
        return j

    def apply_move(ci, dst):
        src = assign[ci]
        for r, v in chunks[ci][2].items():
            L[src][r] -= v
            L[dst][r] += v
        assign[ci] = dst

    t0 = time.time()
    improved = True
    while improved and time.time() - t0 < time_budget:
        improved = False
        base = J_now()
        best_gain, best_op = 1e-12, None

        for ci in range(len(chunks)):
            src = assign[ci]
            for dst in range(m):
                if dst == src:
                    continue
                apply_move(ci, dst)
                gain = base - J_now()
                apply_move(ci, src)
                if gain > best_gain:
                    best_gain, best_op = gain, ("move", ci, dst)

        for ci in range(len(chunks)):
            for cj in range(ci + 1, len(chunks)):
                a, b = assign[ci], assign[cj]
                if a == b:
                    continue
                apply_move(ci, b); apply_move(cj, a)
                gain = base - J_now()
                apply_move(cj, b); apply_move(ci, a)
                if gain > best_gain:
                    best_gain, best_op = gain, ("swap", ci, cj)

        if best_op:
            improved = True
            if best_op[0] == "move":
                _, ci, dst = best_op
                apply_move(ci, dst)
            else:
                _, ci, cj = best_op
                a, b = assign[ci], assign[cj]
                apply_move(ci, b)
                apply_move(cj, a)

    return L, assign