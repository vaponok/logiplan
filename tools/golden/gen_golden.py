#!/usr/bin/env python3
"""
Генератор эталонов: прогоняет ОРИГИНАЛЬНУЮ Python-версию (legacy/) на
случайных, но воспроизводимых входных данных и сохраняет её ответы в
tests/golden/*.json. TypeScript-тесты (tests/golden.test.ts) сверяются с ними.

Что меняется в legacy-коде только на время прогона (и почему):
  * fair_allocator: бюджет времени -> без ограничения. Иначе результат
    зависит от скорости машины: Python останавливает поиск через 0.5 с.
  * fair_allocator: порядок ключей preload -> по имени ресурса. В оригинале
    он берётся из set() и меняется от запуска к запуску (PYTHONHASHSEED).
  * fair_allocator: x ** 2 -> x * x. pow() из libm может отличаться от x*x
    в последнем бите, а это влияет на выбор при точных ничьих.
  * datetime.now() -> фиксированная дата (дата плана в выводе).

Исправления ошибок старой версии, подтверждённые пользователем (TS-версия
ведёт себя так же; legacy/ не меняется, правка вносится только на время
прогона — см. load_patched_resource_splitter()):
  * resource_splitter: авиа-квота понимает свободный формат строк
    ("2 ящ. - Имя", "1 шт. - Имя", "3 - Имя", с необязательным [настройки]
    в конце). Раньше такие строки молча терялись — и в «Лётном», и в
    «Ресурсах на завод» по основной квоте.
  * resource_splitter: модификации МТО — позиция, отданная целиком
    человеку, у которого она уже есть, прибавляется к его количеству,
    а не затирает его (повторные строки одной модификации).
  * resource_splitter: предметы авиа-квоты без записи в resources.json,
    но известные i18n (Cloudrunner’s Vesture, Одеяние авиатора, Рюкзак
    парашютиста), делятся между лётчиками как обычные; совсем неизвестные
    попадают в «Неизвестные позиции».
Вся остальная логика исполняется как есть.

Изменения игры (tools/data_updates.py — те же, что попадают в src/data при
экспорте) применяются к данным legacy-версии на время прогона: цены в
resources.json, список завода и модификаций МТО.

Запуск:
  QT_QPA_PLATFORM=offscreen python tools/golden/gen_golden.py [--splitter 150]
"""
import argparse
import json
import os
import random
import sys
import tempfile
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY = os.path.join(ROOT, "legacy")
OUT = os.path.join(ROOT, "tests", "golden")
sys.path.insert(0, LEGACY)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # tools/
os.chdir(LEGACY)  # resource_splitter открывает resources.json относительно cwd
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# QSettings пишет в ~/.config — уводим во временную папку
_tmp_home = tempfile.mkdtemp(prefix="golden-home-")
os.environ["HOME"] = _tmp_home
os.environ["XDG_CONFIG_HOME"] = os.path.join(_tmp_home, ".config")


def load_patched_allocator():
    src = open(os.path.join(LEGACY, "fair_allocator.py"), encoding="utf-8").read()
    patches = [
        ("d += ((x1 - m_r) ** 2 - (x0 - m_r) ** 2) / (m_r * m_r)",
         "d += (_sq(x1 - m_r) - _sq(x0 - m_r)) / (m_r * m_r)"),
        ("j += ((L[i][r] / people[i] - m_r) / m_r) ** 2",
         "j += _sq((L[i][r] / people[i] - m_r) / m_r)"),
        ("def allocate(chunks, people, preload=None, time_budget=0.5):",
         "def allocate(chunks, people, preload=None, time_budget=1e9):\n"
         "    if preload:\n"
         "        preload = [dict(sorted(d.items())) for d in preload]"),
    ]
    for old, new in patches:
        assert src.count(old) == 1, f"патч не применился: {old}"
        src = src.replace(old, new)
    src = "def _sq(x):\n    return x * x\n\n" + src
    mod = types.ModuleType("fair_allocator")
    mod.__file__ = os.path.join(LEGACY, "fair_allocator.py")
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    sys.modules["fair_allocator"] = mod
    return mod


# Исправление 1: свободный формат авиа-строки. Вставляется перед
# parse_aviation_quota_line; регулярки и _resolve_loose_name — те же, что
# у parse_csv_line в legacy-версии.
_AV_LOOSE_SRC = r'''def _parse_aviation_loose(line: str):
    """
    Свободный формат авиа-строки: "2 ящ. - Tulka P4 Welkinrive [scrap=0]",
    "1 шт. - Luminary Mk. II Harbinger", "3 - Одеяние авиатора".
    False — строка не в свободном формате (разбирается как CSV);
    None — count <= 0; иначе (count, name, settings).
    """
    s = line.strip()
    m = re.match(r"^(.*?)\s*\[([^\]]*)\]\s*$", s)
    body, settings_raw = (m.group(1), m.group(2)) if m else (s, "")
    m = _LOOSE_LINE_RE.match(body)
    if m:
        count, unit, raw_name = int(m.group(1)), m.group(2).lower(), m.group(3)
    else:
        m = _LOOSE_NOUNIT_RE.match(body)
        if not m or ',' in body:
            return False
        count, unit, raw_name = int(m.group(1)), 'ящ', m.group(2)
    if count <= 0:
        return None
    name = _resolve_loose_name(raw_name, unit) or raw_name
    name = i18n.to_canonical_item_name(name)
    name = re.sub(r"\s*\(Ящик\)\s*$", "", name).strip()
    return (count, name, _parse_aviation_settings(settings_raw))


'''


def load_patched_resource_splitter():
    path = os.path.join(LEGACY, "resource_splitter.py")
    src = open(path, encoding="utf-8").read()
    patches = [
        # 1. разбор [...] — в отдельную функцию (общая для CSV и свободного формата)
        ("    # Дефолты\n    settings = {\n",
         "    return (count, name, _parse_aviation_settings(settings_raw))\n\n\n"
         "def _parse_aviation_settings(settings_raw: str):\n"
         "    # Дефолты\n    settings = {\n"),
        ("    return (count, name, settings)\n",
         "    return settings\n"),
        # 1. свободный формат — до CSV-разбора
        ("def parse_aviation_quota_line(line: str):",
         _AV_LOOSE_SRC + "def parse_aviation_quota_line(line: str):"),
        ("    if not line or not line.strip():\n"
         "        return None\n"
         "    \n"
         "    # Сначала отделяем число (после последней запятой)",
         "    if not line or not line.strip():\n"
         "        return None\n"
         "    loose = _parse_aviation_loose(line)\n"
         "    if loose is not False:\n"
         "        return loose\n"
         "    \n"
         "    # Сначала отделяем число (после последней запятой)"),
        # 2. модификации МТО: целиком одному — прибавляем, а не затираем
        ("                per_person_items[min_load_idx][name] = cnt",
         "                per_person_items[min_load_idx][name] = per_person_items[min_load_idx].get(name, 0) + cnt"),
        # 3а. Лётное: предметы без записи в resources.json, но известные i18n
        ("            entry = self.resource_db.get(name)\n"
         "            if not entry:\n"
         "                # неизвестное имя — игнорируем\n"
         "                continue\n"
         "            if entry.get(\"is_aviation\"):\n"
         "                avi_orders.append((count, name, settings, entry.get(\"recipe\", {})))\n"
         "            else:\n"
         "                # обычный предмет (типа аптечки) - имеет cost_per_box\n"
         "                common_orders.append((count, name, entry))",
         "            entry = self.resource_db.get(name)\n"
         "            if entry and entry.get(\"is_aviation\"):\n"
         "                avi_orders.append((count, name, settings, entry.get(\"recipe\", {})))\n"
         "            elif entry:\n"
         "                # обычный предмет (типа аптечки) - имеет cost_per_box\n"
         "                common_orders.append((count, name, entry))\n"
         "            elif name in i18n.ITEM_I18N:\n"
         "                common_orders.append((count, name, {}))\n"
         "            elif f\"{name} (Ящик)\" in i18n.ITEM_I18N:\n"
         "                # парсер срезал \"(Ящик)\": Одеяние авиатора, Рюкзак парашютиста\n"
         "                common_orders.append((count, f\"{name} (Ящик)\", {}))\n"
         "            # иначе неизвестное имя — попадёт в «Неизвестные позиции»"),
        # 3б. неизвестные позиции авиа-квоты — в «Неизвестные позиции»
        ("        self.undefined_area.setPlainText(\"\\n\".join(annotated_undefined))",
         "        for av_line in self.aviation_quota_input.toPlainText().splitlines():\n"
         "            parsed = parse_aviation_quota_line(av_line)\n"
         "            if parsed is None:\n"
         "                continue\n"
         "            av_name = parsed[1]\n"
         "            if not (self.resource_db.get(av_name) or av_name in i18n.ITEM_I18N\n"
         "                    or f\"{av_name} (Ящик)\" in i18n.ITEM_I18N):\n"
         "                annotated_undefined.append(av_name)\n"
         "        self.undefined_area.setPlainText(\"\\n\".join(annotated_undefined))"),
    ]
    # изменения игры: resources.json — через tools/data_updates.py
    patches.append(("                self.resource_db = json.load(f)",
                    "                self.resource_db = __import__('data_updates').update_resources(json.load(f))"))
    for old, new in patches:
        assert src.count(old) == 1, f"патч не применился: {old}"
        src = src.replace(old, new)
    mod = types.ModuleType("resource_splitter")
    mod.__file__ = path
    sys.modules["resource_splitter"] = mod
    exec(compile(src, path, "exec"), mod.__dict__)
    return mod


load_patched_allocator()
load_patched_resource_splitter()

from PyQt5 import QtWidgets  # noqa: E402
import i18n  # noqa: E402
import items  # noqa: E402
import calculator  # noqa: E402
import resource_splitter as rs  # noqa: E402
import quota_writer  # noqa: E402
import data_updates  # noqa: E402

data_updates.update_items(items)  # модификации МТО, особые позиции завода
data_updates.update_quota_writer(quota_writer)  # список завода по умолчанию

FIXED_TODAY = None


class FixedDatetime(rs.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(*FIXED_TODAY)


rs.datetime = FixedDatetime

DB = data_updates.update_resources(json.load(open(os.path.join(LEGACY, "resources.json"), encoding="utf-8")))
ALL_ITEMS = list(DB)
AVIATION_ITEMS = [k for k, v in DB.items() if v.get("is_aviation")]
REGULAR_ITEMS = [k for k, v in DB.items() if not v.get("is_aviation")]
I18N_KEYS = list(i18n.ITEM_I18N)
LANGS = list(i18n.LANGS)


def dump(name, obj):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=None, separators=(",", ":"))
    print(f"  {name}: {len(obj)} случаев, {os.path.getsize(path) // 1024} КБ")


# ---------------------------------------------------------------- строки квоты

def localized(rng, name):
    tr = i18n.ITEM_I18N.get(name)
    if not tr or rng.random() < 0.4:
        return name
    return tr.get(rng.choice(LANGS)) or name


def strip_crate(s):
    for suf in (" (Ящик)", " (Crate)", " (Caisse)"):
        if s.endswith(suf):
            return s[: -len(suf)]
    return s


def mangle(rng, s):
    """Небольшие «человеческие» искажения: регистр, кавычки, ё, пробелы."""
    r = rng.random()
    if r < 0.15:
        s = s.lower()
    elif r < 0.25:
        s = s.upper()
    if rng.random() < 0.2:
        s = s.replace("'", "’").replace('"', "“")
    if rng.random() < 0.15:
        s = s.replace("е", "ё", 1)
    if rng.random() < 0.15:
        s = s.replace(" ", "  ", 1)
    return s


def quota_line(rng, name, cnt):
    disp = localized(rng, name)
    style = rng.random()
    if style < 0.45:
        sep = rng.choice([",", ", ", " ,", " , "])
        return f"{disp}{sep}{cnt}"
    if style < 0.75:
        unit = rng.choice(["ящ.", "ящ", "Ящ.", "шт.", "шт"]) if disp.endswith(("(Ящик)", "(Crate)", "(Caisse)")) else rng.choice(["шт.", "ящ."])
        base = strip_crate(disp)
        if rng.random() < 0.3:
            base = mangle(rng, base)
        dash = rng.choice(["-", "–", "—"])
        return f"{cnt} {unit} {dash} {base}"
    if style < 0.9:
        return f"{cnt} - {disp}"
    return f"{mangle(rng, disp)},{cnt}"


JUNK = ["Неведомая штука (Ящик),3", "foo,bar", "просто текст", ",5", "Бинты (Ящик),0",
        "Бинты (Ящик),-2", "X: 12.5 Y: 7.25 Главный склад", "", "   ", "Sampo 77,2",
        "7 ящ. - Несуществующий предмет", "3 - ???", "Бинты (Ящик),1_0", "Бинты (Ящик), +4"]


# Предметы страницы «Лётное» без записи в resources.json — есть только в i18n
AV_PAGE_ONLY = ["Cloudrunner’s Vesture (Ящик)", "Одеяние авиатора (Ящик)", "Рюкзак парашютиста (Ящик)"]

# Авиа-строки с неизвестными именами и прочий мусор
AV_JUNK = ["Неведомый самолёт,2", "Неведомый самолёт [scrap=10],1", "2 шт. - Неведомый самолёт [scrap=10]",
           "3 - ???", "7 ящ. - Несуществующий предмет", "Sampo 77,2", "2 ящ. - Sampo 77", "1 — Foo Bar [coke=no_sulfur]",
           "5 -", "- Tulka P4 Welkinrive", "2-Tulka P4 Welkinrive", "1 - Tulka, P4 Welkinrive", "[scrap=50]",
           "2 ящ. - [coke=no_sulfur]", "abc - def", "4 шт - Luminary Mk. II Harbinger [coke=no_sulfur],2",
           "3 — Рюкзак парашютиста [fuel=coal] [scrap=5]", "1 - X [scrap=]", "0 - Tulka P4 Welkinrive [scrap=0]",
           "Бинты (Ящик),0", "12 – ", "3ящ.-Одеяние авиатора"]


def aviation_settings_tail(rng, sep=" "):
    parts = []
    if rng.random() < 0.3:
        parts.append(f"coke={rng.choice(['with_sulfur', 'no_sulfur', 'bad'])}")
    if rng.random() < 0.3:
        parts.append(f"fuel={rng.choice(['sulfur', 'coal', 'x'])}")
    if rng.random() < 0.3:
        parts.append(f"scrap={rng.choice(['0', '50', '100', '150', '-5', 'abc'])}")
    return f"{sep}[{', '.join(parts)}]" if parts else ""


def aviation_loose_line(rng, name, cnt):
    """Авиа-строка в свободном формате: "2 ящ. - Имя", "1 шт. - Имя", "3 - Имя"."""
    disp = localized(rng, name)
    dash = rng.choice(["-", "–", "—"])
    if rng.random() < 0.6:
        crated = disp.endswith(("(Ящик)", "(Crate)", "(Caisse)"))
        unit = rng.choice(["ящ.", "ящ", "Ящ.", "ЯЩ."] if crated else ["шт.", "шт", "Шт."])
        base = strip_crate(disp) if rng.random() < 0.8 else disp
        if rng.random() < 0.25:
            base = mangle(rng, base)
        sp = rng.choice([" ", " ", " ", ""])
        return f"{cnt}{sp}{unit}{sp}{dash}{sp}{base}"
    return f"{cnt} {dash} {disp if rng.random() < 0.7 else strip_crate(disp)}"


def random_quota(rng, n_lines, pool):
    lines = []
    for _ in range(n_lines):
        r = rng.random()
        if r < 0.08:
            lines.append(rng.choice(JUNK))
            continue
        name = rng.choice(pool)
        e = DB.get(name, {})
        dist = e.get("distribution")
        if dist == "per_person_one":
            cnt = rng.randint(1, 4)
        elif dist == "balance_fill":
            cnt = rng.randint(1, 12)
        elif e.get("group") == 8:
            cnt = rng.randint(1, 7)
        else:
            cnt = rng.randint(1, 40)
        lines.append(quota_line(rng, name, cnt))
    return "\n".join(lines)


# ---------------------------------------------------------------- 1. parse_csv_line

def gen_parse_cases(rng, n):
    cases = []
    for _ in range(n):
        name = rng.choice(I18N_KEYS + ALL_ITEMS)
        line = quota_line(rng, name, rng.randint(0, 120)) if rng.random() < 0.9 else rng.choice(JUNK)
        cases.append({"line": line, "result": list(rs.parse_csv_line(line) or []) or None})
    return cases


def gen_aviation_parse_cases(rng, n):
    cases = []
    pool = AVIATION_ITEMS + REGULAR_ITEMS[:30] + AV_PAGE_ONLY
    for _ in range(n):
        r = rng.random()
        if r < 0.5:  # CSV: "Имя [настройки],число"
            line = f"{localized(rng, rng.choice(pool))}{aviation_settings_tail(rng)},{rng.randint(-1, 5)}"
        elif r < 0.92:  # свободный формат: "2 ящ. - Имя [настройки]"
            tail = aviation_settings_tail(rng, sep=rng.choice([" ", " ", "", "  "]))
            line = aviation_loose_line(rng, rng.choice(pool), rng.randint(0, 5)) + tail
        else:
            line = rng.choice(AV_JUNK)
        defaults = {"coke": rng.choice(["with_sulfur", "no_sulfur"]),
                    "fuel": rng.choice(["sulfur", "coal"]), "scrap": rng.choice([0, 25, 100])}
        rs.AV_DEFAULT_COKE, rs.AV_DEFAULT_FUEL, rs.AV_DEFAULT_SCRAP = defaults["coke"], defaults["fuel"], defaults["scrap"]
        res = rs.parse_aviation_quota_line(line)
        out = None
        if res:
            cnt, nm, st = res
            out = [cnt, nm, st, rs.serialize_aviation_quota_line(cnt, nm, st)]
        cases.append({"line": line, "defaults": defaults, "result": out})
    rs.AV_DEFAULT_COKE, rs.AV_DEFAULT_FUEL, rs.AV_DEFAULT_SCRAP = "with_sulfur", "sulfur", 100
    return cases


# ---------------------------------------------------------------- 2. калькулятор

def gen_calculator_cases(rng, n):
    cases = []
    keys = ["steel", "m1", "m2", "m3", "m4", "m5", "proc", "rare", "build"]
    for _ in range(n):
        recipe = {k: (rng.randint(0, 200) if rng.random() < 0.5 else 0) for k in keys}
        coke = rng.choice(["with_sulfur", "no_sulfur"])
        fuel = rng.choice(["sulfur", "coal"])
        scrap = rng.choice([0.0, 0.25, 0.5, 0.75, 1.0, rng.randint(0, 100) / 100.0])
        bc = calculator.total_cost(recipe, coke, fuel, scrap)
        cases.append({"recipe": recipe, "coke": coke, "fuel": fuel, "scrap": scrap,
                      "result": {"coal": bc.coal, "scrap": bc.scrap, "components": bc.components,
                                 "sulfur": bc.sulfur, "rare_mats": bc.rare_mats,
                                 "sulfur_byproduct": bc.sulfur_byproduct, "net_sulfur": bc.net_sulfur()}})
    return cases


# ---------------------------------------------------------------- 3. распределитель

class Capture:
    def __init__(self, widget):
        self.value = None
        widget.setPlainText = self.set

    def set(self, text):
        self.value = text


def make_widget():
    w = rs.ResourceSplitter()
    w.cap_out = Capture(w.output_area)
    w.cap_undef = Capture(w.undefined_area)
    return w


def set_lists(w, omto, aviation):
    w._omto_user = list(omto)
    w._aviation_user = list(aviation)
    w._omto_apply_to_special_set()
    w._aviation_apply_to_special_set()


def random_names(rng, n, prefix):
    out = []
    for i in range(n):
        r = rng.random()
        out.append("" if r < 0.25 else ("   " if r < 0.3 else f"{prefix}{i + 1}_{rng.randint(1, 99)}"))
    return out


def gen_splitter_case(rng, w, size):
    global FIXED_TODAY
    lang = rng.choice(LANGS)
    w.lang = lang
    FIXED_TODAY = (2026, rng.randint(1, 12), rng.randint(1, 28), 12, 0, 0)

    n_div = rng.randint(1, 8)
    divisions = [{"name": rng.choice(["", f"@Отряд {i + 1}", f"Взвод-{rng.randint(1, 9)}", " "]),
                  "people": rng.randint(1, 30)} for i in range(n_div)]

    omto_list = list(w._omto_default)
    aviation_list = list(w._aviation_default)
    if rng.random() < 0.3:
        omto_list = rng.sample(omto_list, k=max(0, len(omto_list) - rng.randint(0, 5)))
    if rng.random() < 0.3:
        aviation_list = rng.sample(aviation_list, k=max(0, len(aviation_list) - rng.randint(0, 5)))

    pool = REGULAR_ITEMS + AVIATION_ITEMS[:4] + omto_list[:6]
    quota = random_quota(rng, size, pool)
    if rng.random() < 0.3:
        quota += "\n" + quota.split("\n")[0]  # дубликат строки
    if rng.random() < 0.25:  # самолёты в основной квоте свободным форматом
        for _ in range(rng.randint(1, 2)):
            tail = f" [scrap={rng.choice([0, 50])}]" if rng.random() < 0.3 else ""
            quota += "\n" + aviation_loose_line(rng, rng.choice(AVIATION_ITEMS), rng.randint(1, 3)) + tail

    omto_count = rng.choice([0, 0, 1, 1, 2, 3, 4])
    mod_lines = [f"{rng.choice(items.MTO_MODIFICATIONS)},{rng.randint(1, 12)}"
                 for _ in range(rng.randint(0, 5))] if items.MTO_MODIFICATIONS else []
    if mod_lines and rng.random() < 0.4:
        # повтор той же модификации — у одного человека количества складываются
        dup = rng.choice(mod_lines).rsplit(",", 1)[0]
        dup_line = f"{dup},{rng.randint(1, 12)}" if rng.random() < 0.5 else quota_line(rng, dup, rng.randint(1, 12))
        mod_lines.insert(rng.randint(0, len(mod_lines)), dup_line)
    mods = "\n".join(mod_lines)
    equipment = "\n".join(quota_line(rng, rng.choice(omto_list or REGULAR_ITEMS), rng.randint(1, 15))
                          for _ in range(rng.randint(0, 5)))
    aviation_count = rng.choice([0, 1, 2, 3])
    av_lines = []
    av_pool = (AVIATION_ITEMS + aviation_list[:5] or AVIATION_ITEMS) + AV_PAGE_ONLY
    for _ in range(rng.randint(0, 4)):
        r = rng.random()
        if r < 0.12:
            av_lines.append(rng.choice(AV_JUNK))
            continue
        nm = rng.choice(av_pool)
        tail = ""
        if rng.random() < 0.4:
            tail = f" [scrap={rng.choice([0, 50, 100])}, coke={rng.choice(['with_sulfur', 'no_sulfur'])}]"
        if r < 0.6:
            av_lines.append(f"{localized(rng, nm)}{tail},{rng.randint(1, 4)}")
        else:
            av_lines.append(aviation_loose_line(rng, nm, rng.randint(1, 4)) + tail)
    aviation_text = "\n".join(av_lines)
    if rng.random() < 0.2:
        aviation_text = ""

    av_defaults = {"coke": rng.choice(["with_sulfur", "no_sulfur"]),
                   "fuel": rng.choice(["sulfur", "coal"]), "scrap": rng.choice([0, 50, 100])}
    flags = {"enforceMul4": rng.random() < 0.7, "freeEmats": rng.random() < 0.3,
             "freeHemats": rng.random() < 0.3, "freeRmats": rng.random() < 0.3}

    inp = {
        "lang": lang, "quotaText": quota, "divisions": divisions,
        "unitName": rng.choice(["", "Полк", "@Unit"]), "storageName": rng.choice(["", "Склад А"]),
        "storagePass": rng.choice(["", "1234"]), "weekdayIndex": rng.randint(0, 6),
        "today": {"year": FIXED_TODAY[0], "month": FIXED_TODAY[1], "day": FIXED_TODAY[2]},
        "omtoName": rng.choice(["", "  ", "Завод-1"]), "omtoCount": omto_count,
        "omtoNames": random_names(rng, omto_count, "Мтошник"), "modsText": mods, "equipmentText": equipment,
        "aviationCount": aviation_count, "aviationNames": random_names(rng, aviation_count, "Пилот"),
        "aviationText": aviation_text, "omtoList": omto_list, "aviationList": aviation_list,
        "avDefaults": av_defaults, **flags,
    }

    # --- заполняем виджет ---
    rs.AV_DEFAULT_COKE, rs.AV_DEFAULT_FUEL, rs.AV_DEFAULT_SCRAP = av_defaults["coke"], av_defaults["fuel"], av_defaults["scrap"]
    w.unit_name_input.setText(inp["unitName"])
    w.storage_name_input.setText(inp["storageName"])
    w.storage_pass_input.setText(inp["storagePass"])
    w.weekday_combo.setCurrentIndex(inp["weekdayIndex"])
    w.division_count_input.setValue(n_div)
    w.generate_division_fields()
    for i, d in enumerate(divisions):
        w.division_names[i].setText(d["name"])
        w.division_inputs[i].setValue(d["people"])
    w.quota_input.setPlainText(quota)
    w.mods_quota_input.setPlainText(mods)
    w.equipment_quota_input.setPlainText(equipment)
    w.omto_name_input.setText(inp["omtoName"])
    w.omto_count_spin.setValue(omto_count)
    w._rebuild_omto_names(omto_count)
    for i, nm in enumerate(inp["omtoNames"]):
        w.omto_name_inputs[i].setText(nm)
    w.aviation_count_spin.setValue(aviation_count)
    w._rebuild_aviation_names(aviation_count)
    for i, nm in enumerate(inp["aviationNames"]):
        w.aviation_name_inputs[i].setText(nm)
    w.aviation_quota_input.setPlainText(aviation_text)
    w.enforce_multiple_of_4 = flags["enforceMul4"]
    w.free_emats, w.free_hemats, w.free_rmats = flags["freeEmats"], flags["freeHemats"], flags["freeRmats"]
    set_lists(w, omto_list, aviation_list)

    w.cap_out.value = None
    w.cap_undef.value = None
    t0 = time.time()
    w.calculate_distribution()
    elapsed = time.time() - t0
    return {"input": inp, "output": w.cap_out.value, "undefined": w.cap_undef.value, "pySeconds": round(elapsed, 3)}


def gen_quota_cases(rng, w, n):
    cases = []
    for _ in range(n):
        lang = rng.choice(LANGS)
        w.lang = lang
        omto_list = list(w._omto_default)
        aviation_list = list(w._aviation_default)
        pool = REGULAR_ITEMS + omto_list + aviation_list + list(items.MTO_MODIFICATIONS)
        names = rng.sample(pool, k=min(len(pool), rng.randint(1, 25)))
        required = "\n".join(quota_line(rng, nm, rng.randint(1, 60)) for nm in names)
        storage = "\n".join(f"{localized(rng, nm)},{rng.randint(0, 70)}" for nm in names if rng.random() < 0.6)
        if rng.random() < 0.3:
            storage = "X: 10.0 Y: 20.0 Склад\n" + storage
        set_lists(w, omto_list, aviation_list)
        w.required_input.setPlainText(required)
        w.storage_input.setPlainText(storage)
        caps = {k: Capture(getattr(w, k)) for k in
                ("quota_input", "mods_quota_input", "equipment_quota_input", "aviation_quota_input")}
        w._on_calc_quota_btn()
        cases.append({"storage": storage, "required": required, "omtoList": omto_list,
                      "aviationList": aviation_list, "lang": lang,
                      "result": {"main": caps["quota_input"].value, "mods": caps["mods_quota_input"].value,
                                 "equipment": caps["equipment_quota_input"].value,
                                 "aviation": caps["aviation_quota_input"].value}})
        for k in caps:  # вернуть настоящие методы
            del getattr(w, k).setPlainText
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--splitter", type=int, default=150)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    app = QtWidgets.QApplication(sys.argv)  # noqa: F841
    print("Эталоны:")
    dump("parse_csv.json", gen_parse_cases(rng, 3000))
    dump("parse_aviation.json", gen_aviation_parse_cases(rng, 1500))
    dump("calculator.json", gen_calculator_cases(rng, 600))

    w = make_widget()
    dump("calc_quota.json", gen_quota_cases(rng, w, 120))

    cases = []
    t0 = time.time()
    for k in range(args.splitter):
        size = rng.choice([3, 6, 10, 15, 20, 30]) if k % 10 else rng.choice([45, 60])
        cases.append(gen_splitter_case(rng, w, size))
    dump("splitter.json", cases)
    slowest = max(c["pySeconds"] for c in cases)
    print(f"  Python: {time.time() - t0:.1f} с на {len(cases)} расчётов, самый долгий {slowest:.2f} с")


if __name__ == "__main__":
    main()
