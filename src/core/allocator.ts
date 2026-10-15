// Порт legacy/fair_allocator.py — векторная упаковка квоты по подразделениям.
//
// Модель стоимости (как в ResourceSplitter):
//   per_9      -> неделимые чанки по 9, скидка цикла 9;
//   per_person -> чанки по 5, скидка цикла 5;
//   per_4      -> чанки по 4 без скидки (при enforceMul4 = false — поштучно);
//   остальное  -> поштучно, полная цена.
// Бесплатные ресурсы входят в вектор чанка номиналом: бесплатное тоже
// делится по справедливости.
//
// Алгоритм: BFD (чанки по убыванию нормированного веса, каждый — в argmin
// прироста потенциала J = Σ_r Σ_i ((L_ir/p_i − μ_r)/μ_r)²), затем локальный
// поиск (лучший перенос/обмен, пока J падает, в пределах бюджета времени).
//
// Арифметика повторяет Python-версию операция в операцию (тот же порядок
// суммирования), поэтому при одинаковом числе итераций результат совпадает.
// Все нагрузки — целые числа во float, поэтому суммы нагрузок точные.

export const CHUNK: Record<string, number> = { per_4: 4, per_9: 9, per_person: 5 };
export const DISCOUNT_G: Record<string, number> = { per_9: 9, per_person: 5 };

export interface ResourceEntry {
  resource?: string | string[] | null;
  cost_per_box?: number | number[] | null;
  distribution?: string;
  group?: number;
  is_aviation?: boolean;
  only_one_per_division?: boolean;
  recipe?: Record<string, number>;
}
export type ResourceDb = Record<string, ResourceEntry>;

export interface Chunk {
  name: string;
  boxes: number;
  vec: Map<string, number>;
}

/** Кумулятивная стоимость count коробок при цикле скидки g (floor по коробке). */
export function discountedSum(base: number, count: number, g: number): number {
  let total = 0;
  for (let k = 0; k < count; k++) {
    total += Math.floor(base * (1 - Math.min(((k % g) + 1) * 0.1, 0.5)));
  }
  return total;
}

/** zip(resource, cost_per_box) или одна пара. */
export function resourcePairs(e: ResourceEntry): Array<[string, number]> {
  const res = e.resource;
  const cost = e.cost_per_box;
  if (Array.isArray(res)) {
    const costs = Array.isArray(cost) ? cost : [];
    const n = Math.min(res.length, costs.length);
    const out: Array<[string, number]> = [];
    for (let i = 0; i < n; i++) out.push([res[i], costs[i]]);
    return out;
  }
  return [[res as string, cost as number]];
}

export function makeChunks(
  quota: Array<[string, number]>,
  db: ResourceDb,
  countResourceCost: ((name: string, r: string) => boolean) | null,
  enforceMul4 = true,
): Chunk[] {
  const chunks: Chunk[] = [];
  for (const [name, cnt0] of quota) {
    const e = Object.prototype.hasOwnProperty.call(db, name) ? db[name] : undefined;
    if (!e) continue;
    const dist = e.distribution ?? "per_person";
    if (e.resource == null || e.cost_per_box == null) continue;
    const pairs = resourcePairs(e);

    let step: number | undefined = CHUNK[dist];
    if (dist === "per_4" && !enforceMul4) step = undefined;
    const g = DISCOUNT_G[dist];

    let sizes: number[];
    if (step) {
      const cnt = Math.ceil(cnt0 / step) * step;
      sizes = new Array(Math.floor(cnt / step)).fill(step);
    } else {
      sizes = new Array(Math.max(0, cnt0)).fill(1);
    }

    for (const sz of sizes) {
      const vec = new Map<string, number>();
      for (const [r, c] of pairs) {
        const paid = countResourceCost ? countResourceCost(name, r) : true;
        const v = paid && g ? discountedSum(c, sz, g) : c * sz;
        vec.set(r, (vec.get(r) ?? 0) + v);
      }
      chunks.push({ name, boxes: sz, vec });
    }
  }
  return chunks;
}

export interface AllocateResult {
  /** Нагрузки по подразделениям, включая preload. */
  loads: Array<Map<string, number>>;
  /** Индекс подразделения для каждого чанка. */
  assign: number[];
  /** Сколько итераций локального поиска выполнено. */
  iterations: number;
  /** true — поиск сошёлся, false — остановлен по бюджету времени. */
  converged: boolean;
}

const now = () => (typeof performance !== "undefined" ? performance.now() : Date.now());

export function allocate(
  chunks: Chunk[],
  people: number[],
  preload: Array<Map<string, number>> | null = null,
  timeBudgetMs = 500,
): AllocateResult {
  const m = people.length;

  // Индексы ресурсов в порядке появления в totals (как dict в Python).
  const totals = new Map<string, number>();
  const pre: Array<Map<string, number>> = [];
  for (let i = 0; i < m; i++) {
    const d = new Map<string, number>();
    if (preload && preload[i]) for (const [r, v] of preload[i]) d.set(r, (d.get(r) ?? 0) + v);
    pre.push(d);
  }
  for (let i = 0; i < m; i++) for (const [r, v] of pre[i]) totals.set(r, (totals.get(r) ?? 0) + v);
  for (const ch of chunks) for (const [r, v] of ch.vec) totals.set(r, (totals.get(r) ?? 0) + v);

  const resNames = [...totals.keys()];
  const R = resNames.length;
  const ridx = new Map(resNames.map((r, k) => [r, k]));

  const totalPeople = people.reduce((a, b) => a + b, 0) || 1;
  const mu = new Float64Array(R); // 0 — ресурса нет в μ (нулевой итог)
  const muOrder: number[] = [];
  resNames.forEach((r, k) => {
    const t = totals.get(r)!;
    if (t > 0) {
      mu[k] = t / totalPeople;
      muOrder.push(k);
    }
  });

  const L = new Float64Array(m * R); // L[i*R + r]
  const Ltot = new Float64Array(m); // sum(L[i].values())
  for (let i = 0; i < m; i++) {
    for (const [r, v] of pre[i]) {
      L[i * R + ridx.get(r)!] += v;
      Ltot[i] += v;
    }
  }

  const assign = new Array<number>(chunks.length).fill(0);
  const exportLoads = () =>
    Array.from({ length: m }, (_, i) => {
      const d = new Map<string, number>();
      resNames.forEach((r, k) => {
        if (L[i * R + k] !== 0 || pre[i].has(r)) d.set(r, L[i * R + k]);
      });
      return d;
    });
  if (!chunks.length || m === 0) return { loads: exportLoads(), assign, iterations: 0, converged: true };

  // Векторы чанков: пары [индекс ресурса, значение] в исходном порядке.
  const vecR: Int32Array[] = [];
  const vecV: Float64Array[] = [];
  for (const ch of chunks) {
    const rs = new Int32Array(ch.vec.size);
    const vs = new Float64Array(ch.vec.size);
    let j = 0;
    for (const [r, v] of ch.vec) {
      rs[j] = ridx.get(r)!;
      vs[j] = v;
      j++;
    }
    vecR.push(rs);
    vecV.push(vs);
  }

  const dJAdd = (i: number, ci: number): number => {
    let d = 0;
    const rs = vecR[ci];
    const vs = vecV[ci];
    for (let j = 0; j < rs.length; j++) {
      const mr = mu[rs[j]];
      if (!mr) continue;
      const x0 = L[i * R + rs[j]] / people[i];
      const x1 = x0 + vs[j] / people[i];
      const a = x1 - mr;
      const b = x0 - mr;
      d += (a * a - b * b) / (mr * mr);
    }
    return d;
  };

  // --- шаг 1: BFD (камни первыми) ---
  const weight = chunks.map((_, ci) => {
    let s = 0;
    const rs = vecR[ci];
    const vs = vecV[ci];
    for (let j = 0; j < rs.length; j++) if (mu[rs[j]]) s += vs[j] / mu[rs[j]];
    return -s;
  });
  const order = chunks.map((_, ci) => ci).sort((a, b) => weight[a] - weight[b]);
  for (const ci of order) {
    let best = 0;
    let bestA = Infinity;
    let bestB = Infinity;
    for (let i = 0; i < m; i++) {
      const a = dJAdd(i, ci);
      const b = Ltot[i] / people[i];
      if (a < bestA || (a === bestA && b < bestB)) {
        best = i;
        bestA = a;
        bestB = b;
      }
    }
    assign[ci] = best;
    const rs = vecR[ci];
    const vs = vecV[ci];
    for (let j = 0; j < rs.length; j++) L[best * R + rs[j]] += vs[j];
    for (let j = 0; j < rs.length; j++) Ltot[best] += vs[j];
  }

  // --- шаг 2: локальный поиск (best move / best swap) ---
  // Слагаемые J кэшируются; при переносе пересчитываются только затронутые,
  // а сама сумма каждый раз собирается заново в порядке Python.
  const M = muOrder.length;
  const muPos = new Int32Array(R).fill(-1);
  muOrder.forEach((k, pos) => (muPos[k] = pos));
  const T = new Float64Array(M * m);
  const term = (pos: number, i: number) => {
    const k = muOrder[pos];
    const mr = mu[k];
    const x = (L[i * R + k] / people[i] - mr) / mr;
    T[pos * m + i] = x * x;
  };
  for (let pos = 0; pos < M; pos++) for (let i = 0; i < m; i++) term(pos, i);
  const Jnow = () => {
    let j = 0;
    for (let q = 0; q < T.length; q++) j += T[q];
    return j;
  };

  const applyMove = (ci: number, dst: number) => {
    const src = assign[ci];
    const rs = vecR[ci];
    const vs = vecV[ci];
    for (let j = 0; j < rs.length; j++) {
      L[src * R + rs[j]] -= vs[j];
      L[dst * R + rs[j]] += vs[j];
      Ltot[src] -= vs[j];
      Ltot[dst] += vs[j];
    }
    for (let j = 0; j < rs.length; j++) {
      const pos = muPos[rs[j]];
      if (pos >= 0) {
        term(pos, src);
        term(pos, dst);
      }
    }
    assign[ci] = dst;
  };

  const C = chunks.length;
  const t0 = now();
  let improved = true;
  let iterations = 0;
  while (improved && now() - t0 < timeBudgetMs) {
    improved = false;
    iterations++;
    const base = Jnow();
    let bestGain = 1e-12;
    let bestOp: [0 | 1, number, number] | null = null;

    for (let ci = 0; ci < C; ci++) {
      const src = assign[ci];
      for (let dst = 0; dst < m; dst++) {
        if (dst === src) continue;
        applyMove(ci, dst);
        const gain = base - Jnow();
        applyMove(ci, src);
        if (gain > bestGain) {
          bestGain = gain;
          bestOp = [0, ci, dst];
        }
      }
    }

    for (let ci = 0; ci < C; ci++) {
      for (let cj = ci + 1; cj < C; cj++) {
        const a = assign[ci];
        const b = assign[cj];
        if (a === b) continue;
        applyMove(ci, b);
        applyMove(cj, a);
        const gain = base - Jnow();
        applyMove(cj, b);
        applyMove(ci, a);
        if (gain > bestGain) {
          bestGain = gain;
          bestOp = [1, ci, cj];
        }
      }
    }

    if (bestOp) {
      improved = true;
      if (bestOp[0] === 0) {
        applyMove(bestOp[1], bestOp[2]);
      } else {
        const [, ci, cj] = bestOp;
        const a = assign[ci];
        const b = assign[cj];
        applyMove(ci, b);
        applyMove(cj, a);
      }
    }
  }

  return { loads: exportLoads(), assign, iterations, converged: !improved };
}
