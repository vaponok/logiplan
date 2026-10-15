#!/usr/bin/env python3
# resource_splitter.py
# This module contains only the ResourceSplitter widget and helpers.
# It can be imported by scanner_app.py or run standalone for testing.

import sys, os, re, json, math, logging
from collections import defaultdict
from datetime import datetime, timedelta
from PyQt5 import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)

import i18n
import fair_allocator
try:
    from items import SPECIAL_OMTO as _IMPORTED_SPECIAL_OMTO
    from items import ITEM_NAMES as _IMPORTED_ITEM_NAMES
    try:
        from items import SPECIAL_AVIATION as _IMPORTED_SPECIAL_AVIATION
    except Exception:
        _IMPORTED_SPECIAL_AVIATION = []
except Exception:
    _IMPORTED_SPECIAL_OMTO = []
    _IMPORTED_ITEM_NAMES = {}
    _IMPORTED_SPECIAL_AVIATION = []
# Импорт калькулятора авиа-ресурсов
try:
    from calculator import calculate_detail, total_cost, FirstLevelMats, BaseCost
    CALCULATOR_AVAILABLE = True
except Exception:
    CALCULATOR_AVAILABLE = False
    calculate_detail = None
    total_cost = None
    FirstLevelMats = None
    BaseCost = None
def _aviation_calc_base_cost(recipe_dict, count, coke_recipe="with_sulfur",
                              fuel_recipe="sulfur", scrap_ratio=1.0):
    """
    Считает базовые ресурсы для одного заказа из авиа-квоты.
    Возвращает BaseCost либо None.
    """
    if not CALCULATOR_AVAILABLE or not recipe_dict or count <= 0:
        return None
    try:
        scaled_costs = {
            k: int(recipe_dict.get(k, 0)) * count
            for k in ("steel", "m1", "m2", "m3", "m4", "m5", "proc", "rare", "build")
        }
        return total_cost(scaled_costs, coke_recipe=coke_recipe,
                          fuel_recipe=fuel_recipe, scrap_ratio=scrap_ratio)
    except Exception:
        return None


# Дефолтные параметры калькулятора (если в строке квоты не указаны)
AV_DEFAULT_COKE = "with_sulfur"
AV_DEFAULT_FUEL = "sulfur"
AV_DEFAULT_SCRAP = 100  # в процентах, 0..100

# --------- разбор "свободного" формата квоты: "27 ящ. - 7.92-мм" ---------
_LOOSE_LINE_RE = re.compile(r'^\s*(\d+)\s*(ящ|шт)\.?\s*[-–—]\s*(.+?)\s*$', re.IGNORECASE)
# "27 - №.2 Loughcaster (Ящик)" — без единицы. Дефис обязан быть отделён
# пробелом слева, чтобы не съедать CSV-строки вида "40-мм (Ящик),18".
_LOOSE_NOUNIT_RE = re.compile(r'^\s*(\d+)\s+[-–—]\s*(.+?)\s*$')

def _loose_tokens(s: str):
    """Токены имени для нечёткого сопоставления: нормализация кавычек,
    ё->е, ` -> ', № -> no, регистронезависимо, только слова/числа."""
    s = i18n.normalize_text(s).replace('`', "'").replace('ё', 'е').replace('№', 'no ')
    return tuple(re.findall(r'[a-zа-я0-9]+', s))

_CRATE_SUFFIXES = (" (Ящик)", " (Crate)", " (Caisse)")

_LOOSE_INDEX = None  # (crated, uncrated): списки (frozenset(tokens), canonical)

_PACK_TOKENS = frozenset({'ящик', 'crate', 'caisse'})

def _build_loose_index():
    """
    Индексирует токены ВСЕХ локализованных вариантов каждого предмета
    (ru/en/fr), а не только канонического русского имени: иначе после
    переключения языка строки вида "54 ящ. - RPG" не находятся, а "150mm"
    по вхождению токенов ошибочно липнет к "Huber Exalt 150mm".
    """
    global _LOOSE_INDEX
    crated, uncrated = {}, {}
    for key, tr in i18n.ITEM_I18N.items():
        bucket = crated if key.endswith('(Ящик)') else uncrated
        for variant in (key, *(tr.get(l) for l in i18n.LANGS)):
            if not variant:
                continue
            toks = frozenset(_loose_tokens(variant)) - _PACK_TOKENS
            if toks:
                bucket.setdefault(toks, set()).add(key)
    _LOOSE_INDEX = (crated, uncrated)

def _resolve_loose_name(name: str, unit: str):
    """
    Разрешает имя без суффикса "(Ящик)" в каноническое.
    unit: 'ящ' -> сначала ящичные варианты, 'шт' -> сначала штучные.
    Стратегия: 1) точно через i18n (все 3 языка); 2) совпадение множества
    токенов; 3) вхождение токенов (для имён без типа оружия: "Sampo 77" ->
    "Автоматическая винтовка Sampo 77 (Ящик)"). Неоднозначность -> None.
    """
    # суффиксные токены упаковки не участвуют в сопоставлении
    toks = frozenset(_loose_tokens(name)) - _PACK_TOKENS
    # 1) точно: пробуем суффикс упаковки на всех языках (RU/EN/FR)
    crated_variants = [f"{name}{suf}" for suf in _CRATE_SUFFIXES]
    variants = crated_variants + [name] if unit == 'ящ' else [name] + crated_variants
    for v in variants:
        canon = i18n.to_canonical_item_name(v)
        if canon in i18n.ITEM_I18N:
            return canon

    if _LOOSE_INDEX is None:
        _build_loose_index()
    if not toks:
        return None
    pools = (_LOOSE_INDEX[0], _LOOSE_INDEX[1]) if unit == 'ящ' else (_LOOSE_INDEX[1], _LOOSE_INDEX[0])
    # 2) точное совпадение множества токенов; 3) вхождение токенов
    #    ("Sampo 77" -> "Автоматическая винтовка Sampo 77"). На каждом этапе
    #    сначала предпочитаемый пул, и только единственное совпадение.
    for match_exact in (True, False):
        for pool in pools:
            if match_exact:
                hits = pool.get(toks, set())
            else:
                hits = set()
                for kt, keys in pool.items():
                    if toks <= kt:
                        hits |= keys
            if len(hits) == 1:
                return next(iter(hits))
            if len(hits) > 1:
                return None  # неоднозначно — пусть уйдёт в "не распознано"
    return None


def format_quota_line(name: str, cnt: int, lang: str) -> str:
    """Единый стиль позиций квоты: "N ящ. - Имя" (ящичные, суффикс убирается)
    или "N шт. - Имя" (штучные). Читается обратно parse_csv_line."""
    localized = i18n.tr_item(name, lang)
    for suf in _CRATE_SUFFIXES:
        if localized.endswith(suf):
            return f"{cnt} ящ. - {localized[:-len(suf)]}"
    return f"{cnt} шт. - {localized}"


def parse_csv_line(line: str):
    """
    Универсальный парсер строки квоты.
    Принимает: "Имя,число", "Имя ,  число", а также свободный формат
    "27 ящ. - 7.92-мм" / "3 шт. - O'Brien V.101 Freeman" (имена без
    "(Ящик)", допускаются опечатки в кавычках/пробелах, ё/е, порядок слов
    и пропущенный тип оружия).
    Возвращает (count, name) или None.
    Игнорирует строки с count=0.
    """
    if not line or not line.strip():
        return None
    # ищем последнюю запятую, после неё число
    s = line.strip()
    # пропускаем строки-заголовки склада (содержат "X:" "Y:" — координаты)
    if re.search(r"X:\s*[\d.]+\s+Y:\s*[\d.]+", s):
        return None
    # свободный формат: "<число> ящ./шт. - <имя>"
    m = _LOOSE_LINE_RE.match(s)
    if m:
        count, unit, raw_name = int(m.group(1)), m.group(2).lower(), m.group(3)
        if count <= 0:
            return None
        canon = _resolve_loose_name(raw_name, unit)
        return (count, canon if canon else raw_name)
    # свободный формат без единицы: "<число> - <имя>" (имя обычно уже
    # с "(Ящик)"; без суффикса по умолчанию предпочитаем ящичный вариант)
    m = _LOOSE_NOUNIT_RE.match(s)
    if m and ',' not in s:
        count, raw_name = int(m.group(1)), m.group(2)
        if count <= 0:
            return None
        canon = _resolve_loose_name(raw_name, 'ящ')
        return (count, canon if canon else raw_name)
    # разделяем по последней запятой
    last_comma = s.rfind(",")
    if last_comma == -1:
        return None
    name = s[:last_comma].strip()
    num_part = s[last_comma+1:].strip()
    if not name:
        return None
    try:
        count = int(num_part)
    except ValueError:
        return None
    if count <= 0:
        return None
    # Поддержка квоты на любом из 3 языков (RU/EN/FR) — приводим к каноническому
    # русскому имени, которым проиндексирована resources.json. Если точное
    # разрешение не сработало — пробуем сленг и нечёткое сопоставление
    # (единственность совпадения обязательна). Иначе имя возвращается как
    # есть и уходит в "не распознано".
    canon = i18n.to_canonical_item_name(name)
    if canon not in i18n.ITEM_I18N:
        loose = _resolve_loose_name(name, 'ящ')
        if loose:
            canon = loose
    return (count, canon)

def parse_aviation_quota_line(line: str):
    """
    Разбирает одну строку из aviation_quota_input в формате CSV.
    Формат: "Имя[,переопределения],число"
    
    Возвращает (count, name, settings) или None.
    
    Примеры:
        "Tulka I1.9 White Raven,2"
            → (2, "Tulka I1.9 White Raven", дефолты)
        "Luminary Mk. II Harbinger [coke=no_sulfur, scrap=50],1"
            → (1, "Luminary Mk. II Harbinger", {"coke": "no_sulfur", ...})
        "Tulka P4 Welkinrive (Ящик) [scrap=0],3"
            → (3, "Tulka P4 Welkinrive", {"scrap": 0, ...})
    """
    if not line or not line.strip():
        return None
    
    # Сначала отделяем число (после последней запятой)
    s = line.strip()
    last_comma = s.rfind(",")
    if last_comma == -1:
        return None
    name_part = s[:last_comma].strip()
    num_part = s[last_comma+1:].strip()
    
    if not name_part:
        return None
    try:
        count = int(num_part)
    except ValueError:
        return None
    if count <= 0:
        return None
    
    # Из name_part вычленяем [...] если есть
    m = re.match(r"^(.+?)(?:\s*\[([^\]]*)\])?\s*$", name_part)
    if not m:
        return None
    name = m.group(1).strip()
    settings_raw = m.group(2) or ""

    # Поддержка EN/FR: сперва приводим к каноническому русскому имени
    # (может быть ещё с суффиксом "(Ящик)"/"(Crate)"/"(Caisse)"), потом обрезаем суффикс.
    name = i18n.to_canonical_item_name(name)

    # Обрезаем "(Ящик)" с конца имени
    name = re.sub(r"\s*\(Ящик\)\s*$", "", name).strip()
    
    # Дефолты
    settings = {
        "coke": AV_DEFAULT_COKE,
        "fuel": AV_DEFAULT_FUEL,
        "scrap": AV_DEFAULT_SCRAP,
    }
    
    # Парсим [...]
    if settings_raw:
        for pair in settings_raw.split(","):
            pair = pair.strip()
            if "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            k = k.strip().lower()
            v = v.strip()
            if k == "coke" and v in ("with_sulfur", "no_sulfur"):
                settings["coke"] = v
            elif k == "fuel" and v in ("sulfur", "coal"):
                settings["fuel"] = v
            elif k == "scrap":
                try:
                    settings["scrap"] = max(0, min(100, int(v)))
                except ValueError:
                    pass
    
    return (count, name, settings)


def serialize_aviation_quota_line(count, name, settings):
    """
    Собирает строку обратно в CSV-формат.
    Если все настройки совпадают с дефолтом — [...] не добавляет.
    """
    # Проверяем настройки на дефолты
    is_default = (
        settings.get("coke", AV_DEFAULT_COKE) == AV_DEFAULT_COKE and
        settings.get("fuel", AV_DEFAULT_FUEL) == AV_DEFAULT_FUEL and
        settings.get("scrap", AV_DEFAULT_SCRAP) == AV_DEFAULT_SCRAP
    )
    if is_default:
        return f"{name},{count}"
    
    parts = []
    if settings.get("coke", AV_DEFAULT_COKE) != AV_DEFAULT_COKE:
        parts.append(f"coke={settings['coke']}")
    if settings.get("fuel", AV_DEFAULT_FUEL) != AV_DEFAULT_FUEL:
        parts.append(f"fuel={settings['fuel']}")
    if settings.get("scrap", AV_DEFAULT_SCRAP) != AV_DEFAULT_SCRAP:
        parts.append(f"scrap={settings['scrap']}")
    return f"{name} [{', '.join(parts)}],{count}"

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return relative_path
class AviationRecipeDialog(QtWidgets.QDialog):
    """Диалог настройки параметров калькулятора для каждого заказа из aviation_quota_input."""

    def __init__(self, parent, parsed_lines, default_coke, default_fuel, default_scrap, lang="ru"):
        """
        parsed_lines: список tuple (line_index, count, name, settings, recipe_dict).
                      Только авиа-предметы (с is_aviation: true в resources.json).
        default_coke, default_fuel, default_scrap: текущие глобальные дефолты.
        lang: текущий язык интерфейса ("ru"/"en"/"fr").
        """
        super().__init__(parent)
        self.lang = lang
        self.setWindowTitle(i18n.tr("av_dialog_title", self.lang))
        self.setMinimumSize(700, 500)

        self.parsed_lines = parsed_lines
        self.row_widgets = []  # список dict с виджетами по каждой строке

        main_layout = QtWidgets.QVBoxLayout(self)

        # ---- Дефолты ----
        defaults_group = QtWidgets.QGroupBox(i18n.tr("av_defaults_group", self.lang))
        defaults_layout = QtWidgets.QGridLayout()

        # Кокс
        defaults_layout.addWidget(QtWidgets.QLabel(i18n.tr("coke_label", self.lang)), 0, 0)
        self.default_coke_with = QtWidgets.QRadioButton(i18n.tr("coke_with_sulfur", self.lang))
        self.default_coke_no = QtWidgets.QRadioButton(i18n.tr("coke_no_sulfur", self.lang))
        coke_grp = QtWidgets.QButtonGroup(self)
        coke_grp.addButton(self.default_coke_with)
        coke_grp.addButton(self.default_coke_no)
        if default_coke == "no_sulfur":
            self.default_coke_no.setChecked(True)
        else:
            self.default_coke_with.setChecked(True)
        coke_row = QtWidgets.QHBoxLayout()
        coke_row.addWidget(self.default_coke_with)
        coke_row.addWidget(self.default_coke_no)
        coke_row.addStretch()
        defaults_layout.addLayout(coke_row, 0, 1)

        # Топливо
        defaults_layout.addWidget(QtWidgets.QLabel(i18n.tr("fuel_label", self.lang)), 1, 0)
        self.default_fuel_sulfur = QtWidgets.QRadioButton(i18n.tr("fuel_sulfur", self.lang))
        self.default_fuel_coal = QtWidgets.QRadioButton(i18n.tr("fuel_coal", self.lang))
        fuel_grp = QtWidgets.QButtonGroup(self)
        fuel_grp.addButton(self.default_fuel_sulfur)
        fuel_grp.addButton(self.default_fuel_coal)
        if default_fuel == "coal":
            self.default_fuel_coal.setChecked(True)
        else:
            self.default_fuel_sulfur.setChecked(True)
        fuel_row = QtWidgets.QHBoxLayout()
        fuel_row.addWidget(self.default_fuel_sulfur)
        fuel_row.addWidget(self.default_fuel_coal)
        fuel_row.addStretch()
        defaults_layout.addLayout(fuel_row, 1, 1)

        # Скрап
        defaults_layout.addWidget(QtWidgets.QLabel(i18n.tr("scrap_via_label", self.lang)), 2, 0)
        self.default_scrap_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.default_scrap_slider.setRange(0, 100)
        self.default_scrap_slider.setValue(int(default_scrap))
        self.default_scrap_label = QtWidgets.QLabel(f"{int(default_scrap)}%")
        self.default_scrap_slider.valueChanged.connect(
            lambda v: self.default_scrap_label.setText(f"{v}%")
        )
        scrap_row = QtWidgets.QHBoxLayout()
        scrap_row.addWidget(self.default_scrap_slider, 1)
        scrap_row.addWidget(self.default_scrap_label)
        defaults_layout.addLayout(scrap_row, 2, 1)

        defaults_group.setLayout(defaults_layout)
        main_layout.addWidget(defaults_group)

        # ---- Список заказов ----
        orders_group = QtWidgets.QGroupBox(i18n.tr("av_orders_group", self.lang))
        orders_layout = QtWidgets.QVBoxLayout()

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_inner = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_inner)

        if not parsed_lines:
            no_orders = QtWidgets.QLabel(i18n.tr("av_no_orders", self.lang))
            scroll_layout.addWidget(no_orders)
        else:
            for entry in parsed_lines:
                line_index, count, name, settings, recipe_dict = entry
                row = self._create_order_row(line_index, count, name, settings)
                scroll_layout.addLayout(row["layout"])
                self.row_widgets.append(row)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_inner)
        orders_layout.addWidget(scroll)
        orders_group.setLayout(orders_layout)
        main_layout.addWidget(orders_group, 1)

        # ---- Кнопки ----
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        self.cancel_btn = QtWidgets.QPushButton(i18n.tr("btn_cancel", self.lang))
        self.save_btn = QtWidgets.QPushButton(i18n.tr("btn_save", self.lang))
        self.save_btn.setDefault(True)
        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.save_btn)
        main_layout.addLayout(btn_row)

    def _create_order_row(self, line_index, count, name, settings):
        """Создаёт строку UI под один заказ. Возвращает dict с виджетами."""
        layout = QtWidgets.QVBoxLayout()

        # Заголовок: "#N: Tulka I1.9 White Raven (×2)" + чекбокс "Кастом"
        header = QtWidgets.QHBoxLayout()
        display_name = i18n.tr_item(name, self.lang)
        title = QtWidgets.QLabel(f"#{line_index + 1}: {display_name} (×{count})")
        f = title.font()
        f.setBold(True)
        title.setFont(f)
        header.addWidget(title)

        # Чекбокс "Использовать кастомные настройки"
        custom_cb = QtWidgets.QCheckBox(i18n.tr("custom_settings_cb", self.lang))
        # По умолчанию: отмечен если settings отличаются от дефолтов "глобальной шапки"
        # Но проще: если в строке quotа явно есть [...], значит уже custom.
        # Мы не знаем здесь "явно", но можем определить эвристикой:
        # если settings содержит non-default коке/fuel/scrap → отмечаем
        is_custom = (
            settings.get("coke") != AV_DEFAULT_COKE or
            settings.get("fuel") != AV_DEFAULT_FUEL or
            settings.get("scrap") != AV_DEFAULT_SCRAP
        )
        custom_cb.setChecked(is_custom)
        header.addWidget(custom_cb)
        header.addStretch()
        layout.addLayout(header)

        # Контейнер с настройками — виден только при custom_cb=True
        sub = QtWidgets.QWidget()
        sub_layout = QtWidgets.QGridLayout(sub)
        sub_layout.setContentsMargins(20, 0, 0, 8)

        sub_layout.addWidget(QtWidgets.QLabel(i18n.tr("coke_label", self.lang)), 0, 0)
        coke_with = QtWidgets.QRadioButton(i18n.tr("coke_with_sulfur", self.lang))
        coke_no = QtWidgets.QRadioButton(i18n.tr("coke_no_sulfur", self.lang))
        coke_grp = QtWidgets.QButtonGroup(sub)
        coke_grp.addButton(coke_with)
        coke_grp.addButton(coke_no)
        if settings.get("coke") == "no_sulfur":
            coke_no.setChecked(True)
        else:
            coke_with.setChecked(True)
        coke_h = QtWidgets.QHBoxLayout()
        coke_h.addWidget(coke_with)
        coke_h.addWidget(coke_no)
        coke_h.addStretch()
        sub_layout.addLayout(coke_h, 0, 1)

        sub_layout.addWidget(QtWidgets.QLabel(i18n.tr("fuel_label", self.lang)), 1, 0)
        fuel_sulfur = QtWidgets.QRadioButton(i18n.tr("fuel_sulfur", self.lang))
        fuel_coal = QtWidgets.QRadioButton(i18n.tr("fuel_coal", self.lang))
        fuel_grp = QtWidgets.QButtonGroup(sub)
        fuel_grp.addButton(fuel_sulfur)
        fuel_grp.addButton(fuel_coal)
        if settings.get("fuel") == "coal":
            fuel_coal.setChecked(True)
        else:
            fuel_sulfur.setChecked(True)
        fuel_h = QtWidgets.QHBoxLayout()
        fuel_h.addWidget(fuel_sulfur)
        fuel_h.addWidget(fuel_coal)
        fuel_h.addStretch()
        sub_layout.addLayout(fuel_h, 1, 1)

        sub_layout.addWidget(QtWidgets.QLabel(i18n.tr("via_scrap_label", self.lang)), 2, 0)
        scrap_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        scrap_slider.setRange(0, 100)
        scrap_slider.setValue(int(settings.get("scrap", AV_DEFAULT_SCRAP)))
        scrap_lbl = QtWidgets.QLabel(f"{scrap_slider.value()}%")
        scrap_slider.valueChanged.connect(lambda v: scrap_lbl.setText(f"{v}%"))
        scrap_h = QtWidgets.QHBoxLayout()
        scrap_h.addWidget(scrap_slider, 1)
        scrap_h.addWidget(scrap_lbl)
        sub_layout.addLayout(scrap_h, 2, 1)

        sub.setVisible(is_custom)
        custom_cb.toggled.connect(sub.setVisible)
        layout.addWidget(sub)

        # Разделитель
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(sep)

        return {
            "layout": layout,
            "line_index": line_index,
            "name": name,
            "count": count,
            "custom_cb": custom_cb,
            "coke_with": coke_with,
            "coke_no": coke_no,
            "fuel_sulfur": fuel_sulfur,
            "fuel_coal": fuel_coal,
            "scrap_slider": scrap_slider,
        }

    def get_results(self):
        """
        Возвращает кортеж (defaults_dict, per_line_settings_dict).
        defaults_dict: {"coke", "fuel", "scrap"}
        per_line_settings_dict: {line_index: {"coke", "fuel", "scrap"}}
                                — только для строк с custom=True.
        Для остальных строк надо использовать defaults.
        """
        defaults = {
            "coke": "no_sulfur" if self.default_coke_no.isChecked() else "with_sulfur",
            "fuel": "coal" if self.default_fuel_coal.isChecked() else "sulfur",
            "scrap": int(self.default_scrap_slider.value()),
        }

        per_line = {}
        for row in self.row_widgets:
            if not row["custom_cb"].isChecked():
                continue
            per_line[row["line_index"]] = {
                "coke": "no_sulfur" if row["coke_no"].isChecked() else "with_sulfur",
                "fuel": "coal" if row["fuel_coal"].isChecked() else "sulfur",
                "scrap": int(row["scrap_slider"].value()),
            }
        return defaults, per_line
class ResourceSplitter(QtWidgets.QWidget):
    def _load_defaults_from_quota_writer(self, page):
        """Имена предметов с вкладки quota_writer: page=11 → МТО, page=12 → Лётка.
        Берём из ITEM_TEXT по ключам pN_bM (сортировка по номеру кнопки).
        При любой ошибке возвращаем [] — вызывающий код откатится на SPECIAL_*."""
        try:
            from quota_writer import ITEM_TEXT
        except Exception:
            return []
        prefix = f"p{page}_b"
        items = []
        for key, name in ITEM_TEXT.items():
            if not key.startswith(prefix):
                continue
            rest = key[len(prefix):]
            if not rest.isdigit():
                continue
            if isinstance(name, str) and name.strip():
                items.append((int(rest), name.strip()))
        items.sort(key=lambda t: t[0])
        seen, out = set(), []
        for _i, n in items:
            if n.lower() in seen:
                continue
            seen.add(n.lower())
            out.append(n)
        return out

    def __init__(self):
        super().__init__()
        self.lang = "ru"
        self.settings = QtCore.QSettings("Vaponok", "LogisticsPlanner")
        self.setWindowTitle(i18n.tr("main_window_title", self.lang))
        # Геометрия окна — восстанавливаем из QSettings, иначе дефолт
        geom = self.settings.value("window_geometry", None) if hasattr(self, 'settings') else None
        if geom:
            try:
                self.restoreGeometry(geom)
            except Exception:
                self.resize(1200, 520)
        else:
            self.resize(1200, 520)

        # CHG: names that must NOT be treated as free even if flags set (normalized lower-case)
        self.free_exceptions = {
            "рмат (ящик)",
            "емат (ящик)",
            "хемат (ящик)",
        }

        # Styling params
        primary_color = '#0066FF'
        base_border = '3px solid #000'
        font = QtGui.QFont("Inter", 10)
        self.setFont(font)

        # --- hover shadow helper ---
        class _HoverShadowFilter(QtCore.QObject):
            def __init__(self, widget, shadow, blur_anim):
                super().__init__(widget)
                self.widget = widget
                self.shadow = shadow
                self.blur_anim = blur_anim

            def eventFilter(self, obj, ev):
                t = ev.type()
                if t == QtCore.QEvent.Enter:
                    self.blur_anim.stop()
                    self.blur_anim.setStartValue(self.shadow.blurRadius())
                    self.blur_anim.setEndValue(28)
                    self.blur_anim.setDuration(180)
                    self.blur_anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
                    self.blur_anim.start()
                elif t == QtCore.QEvent.Leave:
                    self.blur_anim.stop()
                    self.blur_anim.setStartValue(self.shadow.blurRadius())
                    self.blur_anim.setEndValue(12)
                    self.blur_anim.setDuration(160)
                    self.blur_anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
                    self.blur_anim.start()
                elif t == QtCore.QEvent.MouseButtonPress:
                    self.blur_anim.stop()
                    self.blur_anim.setStartValue(self.shadow.blurRadius())
                    self.blur_anim.setEndValue(8)
                    self.blur_anim.setDuration(90)
                    self.blur_anim.setEasingCurve(QtCore.QEasingCurve.InCubic)
                    self.blur_anim.start()
                elif t == QtCore.QEvent.MouseButtonRelease:
                    inside = self.widget.rect().contains(self.widget.mapFromGlobal(QtGui.QCursor.pos()))
                    target = 28 if inside else 12
                    self.blur_anim.stop()
                    self.blur_anim.setStartValue(self.shadow.blurRadius())
                    self.blur_anim.setEndValue(target)
                    self.blur_anim.setDuration(120)
                    self.blur_anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
                    self.blur_anim.start()
                return False

        # --- layout & widgets ---
        main_layout = QtWidgets.QVBoxLayout(self)
        # === Блок "Расчёт квоты" (содержимое склада + необходимое → результат) ===
        self.calc_group = QtWidgets.QGroupBox(i18n.tr("calc_quota_group", self.lang))
        self.calc_group.setFont(font)
        calc_layout = QtWidgets.QVBoxLayout()

        calc_row = QtWidgets.QHBoxLayout()

        # Содержимое склада
        storage_col = QtWidgets.QVBoxLayout()
        self.storage_label = QtWidgets.QLabel(i18n.tr("storage_label", self.lang))
        self.storage_label.setFont(font)
        storage_col.addWidget(self.storage_label)
        self.storage_input = QtWidgets.QPlainTextEdit()
        self.storage_input.setFont(font)
        self.storage_input.setPlaceholderText(i18n.tr("storage_placeholder", self.lang))
        self.storage_input.setMinimumHeight(200)
        storage_col.addWidget(self.storage_input)
        calc_row.addLayout(storage_col, 1)

        # Необходимое снаряжение
        required_col = QtWidgets.QVBoxLayout()
        self.required_label = QtWidgets.QLabel(i18n.tr("required_label", self.lang))
        self.required_label.setFont(font)
        required_col.addWidget(self.required_label)
        self.required_input = QtWidgets.QPlainTextEdit()
        self.required_input.setFont(font)
        self.required_input.setPlaceholderText(i18n.tr("required_placeholder", self.lang))
        self.required_input.setMinimumHeight(200)
        required_col.addWidget(self.required_input)
        calc_row.addLayout(required_col, 1)

        calc_layout.addLayout(calc_row)

        # Кнопка "Рассчитать квоту"
        self.calc_quota_btn = QtWidgets.QPushButton(i18n.tr("calc_quota_btn", self.lang))
        self.calc_quota_btn.setFont(font)
        self.calc_quota_btn.setToolTip(i18n.tr("calc_quota_tooltip", self.lang))
        self.calc_quota_btn.clicked.connect(self._on_calc_quota_btn)
        calc_layout.addWidget(self.calc_quota_btn)

        self.calc_group.setLayout(calc_layout)
        main_layout.addWidget(self.calc_group)

        # === конец блока "Расчёт квоты" ===
        self.unit_name_label = QtWidgets.QLabel(i18n.tr("unit_name_label", self.lang))
        self.unit_name_label.setFont(font)
        main_layout.addWidget(self.unit_name_label)
        self.unit_name_input = QtWidgets.QLineEdit(); self.unit_name_input.setFont(font); main_layout.addWidget(self.unit_name_input)

        self.main_storage_label = QtWidgets.QLabel(i18n.tr("main_storage_label", self.lang))
        self.main_storage_label.setFont(font)
        main_layout.addWidget(self.main_storage_label)
        self.storage_name_input = QtWidgets.QLineEdit(); self.storage_name_input.setFont(font); main_layout.addWidget(self.storage_name_input)

        self.storage_password_label = QtWidgets.QLabel(i18n.tr("storage_password_label", self.lang))
        self.storage_password_label.setFont(font)
        main_layout.addWidget(self.storage_password_label)
        self.storage_pass_input = QtWidgets.QLineEdit(); self.storage_pass_input.setFont(font); main_layout.addWidget(self.storage_pass_input)

        self.plan_until_label = QtWidgets.QLabel(i18n.tr("plan_until_label", self.lang))
        self.plan_until_label.setFont(font)
        main_layout.addWidget(self.plan_until_label)
        self.weekday_combo = QtWidgets.QComboBox(); self.weekday_combo.setFont(font)
        self.weekday_names = i18n.WEEKDAYS[self.lang]
        self.weekday_combo.addItems(self.weekday_names); main_layout.addWidget(self.weekday_combo)

        self.division_count_label = QtWidgets.QLabel(i18n.tr("division_count_label", self.lang))
        self.division_count_label.setFont(font)
        main_layout.addWidget(self.division_count_label)
        self.division_count_input = QtWidgets.QSpinBox(); self.division_count_input.setFont(font); self.division_count_input.setRange(1,100); self.division_count_input.setValue(3)
        self.division_count_input.valueChanged.connect(self.generate_division_fields); main_layout.addWidget(self.division_count_input)

        # container for dynamic division fields
        self.division_inputs_container = QtWidgets.QVBoxLayout(); main_layout.addLayout(self.division_inputs_container)

        # keep lists (CHG: used for saving/restoring people counts)
        self.division_inputs = []
        self.division_names = []

        # quota main
        self.quota_label = QtWidgets.QLabel(i18n.tr("quota_label", self.lang))
        self.quota_label.setFont(font)
        main_layout.addWidget(self.quota_label)
        self.quota_input = QtWidgets.QPlainTextEdit(); self.quota_input.setFont(font)
        self.quota_input.setMinimumHeight(300)
        main_layout.addWidget(self.quota_input)

# === Блок "Завод" ===
        self.factory_group = QtWidgets.QGroupBox(i18n.tr("factory_group", self.lang))
        self.factory_group.setFont(font)
        factory_layout = QtWidgets.QVBoxLayout()

        # ---- Суб-блок МТО ----
        self.omto_subgroup = QtWidgets.QGroupBox(i18n.tr("omto_subgroup", self.lang))
        self.omto_subgroup.setFont(font)
        omto_inner_layout = QtWidgets.QVBoxLayout()

        # Верхняя строка МТО: имя + численность
        omto_top_row = QtWidgets.QHBoxLayout()
        self.omto_name_label = QtWidgets.QLabel(i18n.tr("omto_name_label", self.lang))
        self.omto_name_label.setFont(font)
        omto_top_row.addWidget(self.omto_name_label)
        self.omto_name_input = QtWidgets.QLineEdit()
        self.omto_name_input.setFont(font)
        omto_top_row.addWidget(self.omto_name_input, 1)

        self.omto_count_label = QtWidgets.QLabel(i18n.tr("headcount_label", self.lang))
        self.omto_count_label.setFont(font)
        omto_top_row.addWidget(self.omto_count_label)
        self.omto_count_spin = QtWidgets.QSpinBox()
        self.omto_count_spin.setRange(0, 50)
        self.omto_count_spin.setValue(0)
        self.omto_count_spin.setFont(font)
        omto_top_row.addWidget(self.omto_count_spin)
        omto_inner_layout.addLayout(omto_top_row)

        # Поля имён МТО (динамически)
        self.omto_names_container = QtWidgets.QWidget()
        self.omto_names_layout = QtWidgets.QVBoxLayout(self.omto_names_container)
        self.omto_names_layout.setContentsMargins(0, 0, 0, 0)
        self.omto_name_inputs = []
        omto_inner_layout.addWidget(self.omto_names_container)

        # Поля Модификации / Снаряжение
        omto_quota_row = QtWidgets.QHBoxLayout()

        mods_col = QtWidgets.QVBoxLayout()
        self.mods_label = QtWidgets.QLabel(i18n.tr("mods_label", self.lang))
        self.mods_label.setFont(font)
        mods_col.addWidget(self.mods_label)
        self.mods_quota_input = QtWidgets.QPlainTextEdit()
        self.mods_quota_input.setFont(font)
        self.mods_quota_input.setMinimumHeight(self.quota_input.minimumHeight())
        mods_col.addWidget(self.mods_quota_input)
        omto_quota_row.addLayout(mods_col, 1)

        eq_col = QtWidgets.QVBoxLayout()
        self.equipment_label = QtWidgets.QLabel(i18n.tr("equipment_label", self.lang))
        self.equipment_label.setFont(font)
        eq_col.addWidget(self.equipment_label)
        self.equipment_quota_input = QtWidgets.QPlainTextEdit()
        self.equipment_quota_input.setFont(font)
        self.equipment_quota_input.setMinimumHeight(self.quota_input.minimumHeight())
        eq_col.addWidget(self.equipment_quota_input)
        omto_quota_row.addLayout(eq_col, 1)

        omto_inner_layout.addLayout(omto_quota_row)

        # Алиас на старое имя для обратной совместимости
        self.factory_quota_input = self.mods_quota_input

        # Здесь дальше ВНИЗ пойдёт omto_editor_group (строки 187-242 ниже)
        # — но он добавится в omto_inner_layout, а не в factory_layout.
        # Делается ниже после создания группы.

        self.omto_subgroup.setLayout(omto_inner_layout)
        factory_layout.addWidget(self.omto_subgroup)

        # ---- Суб-блок Лётное отделение ----
        self.aviation_subgroup = QtWidgets.QGroupBox(i18n.tr("aviation_subgroup", self.lang))
        self.aviation_subgroup.setFont(font)
        aviation_inner_layout = QtWidgets.QVBoxLayout()

        # Верхняя строка Лётки: численность
        av_top_row = QtWidgets.QHBoxLayout()
        self.aviation_count_label = QtWidgets.QLabel(i18n.tr("headcount_label", self.lang))
        self.aviation_count_label.setFont(font)
        av_top_row.addWidget(self.aviation_count_label)
        self.aviation_count_spin = QtWidgets.QSpinBox()
        self.aviation_count_spin.setRange(0, 50)
        self.aviation_count_spin.setValue(0)
        self.aviation_count_spin.setFont(font)
        av_top_row.addWidget(self.aviation_count_spin)
        av_top_row.addStretch()
        aviation_inner_layout.addLayout(av_top_row)

        # Поля имён лётчиков (динамически)
        self.aviation_names_container = QtWidgets.QWidget()
        self.aviation_names_layout = QtWidgets.QVBoxLayout(self.aviation_names_container)
        self.aviation_names_layout.setContentsMargins(0, 0, 0, 0)
        self.aviation_name_inputs = []
        aviation_inner_layout.addWidget(self.aviation_names_container)

        # Поле квоты Лётки
        self.aviation_label = QtWidgets.QLabel(i18n.tr("aviation_label", self.lang))
        self.aviation_label.setFont(font)
        aviation_inner_layout.addWidget(self.aviation_label)
        self.aviation_quota_input = QtWidgets.QPlainTextEdit()
        self.aviation_quota_input.setFont(font)
        self.aviation_quota_input.setMinimumHeight(self.quota_input.minimumHeight())
        aviation_inner_layout.addWidget(self.aviation_quota_input)

        # Кнопка настройки цен самолётов (пока заглушка, на будущее)
        self.aviation_recipe_btn = QtWidgets.QPushButton(i18n.tr("aviation_recipe_btn", self.lang))
        self.aviation_recipe_btn.setFont(font)
        self.aviation_recipe_btn.setToolTip(i18n.tr("aviation_recipe_tooltip", self.lang))
        self.aviation_recipe_btn.clicked.connect(self._on_aviation_recipe_btn)
        aviation_inner_layout.addWidget(self.aviation_recipe_btn)

        # Здесь дальше вниз пойдёт aviation_editor_group (создаётся ниже,
        # но добавится в aviation_inner_layout)

        self.aviation_subgroup.setLayout(aviation_inner_layout)
        factory_layout.addWidget(self.aviation_subgroup)
                # === OMTO editor (раскрывающийся блок) ===
        self.omto_editor_group = QtWidgets.QGroupBox(i18n.tr("omto_editor_group", self.lang))
        self.omto_editor_group.setFont(font)
        self.omto_editor_group.setCheckable(True)
        self.omto_editor_group.setChecked(False)  # свёрнут по умолчанию

        omto_layout = QtWidgets.QVBoxLayout()

        # два списка — слева "Доступные", справа "В OMTO"
        lists_row = QtWidgets.QHBoxLayout()

        left_col = QtWidgets.QVBoxLayout()
        self.omto_all_items_label = QtWidgets.QLabel(i18n.tr("all_items_label", self.lang))
        left_col.addWidget(self.omto_all_items_label)
        self.omto_search = QtWidgets.QLineEdit()
        self.omto_search.setPlaceholderText(i18n.tr("omto_search_placeholder", self.lang))
        self.omto_search.setFont(font)
        left_col.addWidget(self.omto_search)
        self.omto_available_list = QtWidgets.QListWidget()
        self.omto_available_list.setMinimumHeight(300)
        self.omto_available_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.omto_available_list.setFont(font)
        left_col.addWidget(self.omto_available_list)
        lists_row.addLayout(left_col, 1)

        # колонка с кнопками между списками
        btn_col = QtWidgets.QVBoxLayout()
        btn_col.addStretch()
        self.omto_add_btn = QtWidgets.QPushButton("→  +")
        self.omto_add_btn.setToolTip(i18n.tr("add_to_omto_tooltip", self.lang))
        self.omto_remove_btn = QtWidgets.QPushButton("−  ←")
        self.omto_remove_btn.setToolTip(i18n.tr("remove_from_omto_tooltip", self.lang))
        btn_col.addWidget(self.omto_add_btn)
        btn_col.addWidget(self.omto_remove_btn)
        btn_col.addStretch()
        lists_row.addLayout(btn_col)

        right_col = QtWidgets.QVBoxLayout()
        self.in_omto_label = QtWidgets.QLabel(i18n.tr("in_omto_label", self.lang))
        right_col.addWidget(self.in_omto_label)
        self.omto_selected_list = QtWidgets.QListWidget()
        self.omto_selected_list.setMinimumHeight(300)
        self.omto_selected_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.omto_selected_list.setFont(font)
        right_col.addWidget(self.omto_selected_list)
        lists_row.addLayout(right_col, 1)

        omto_layout.addLayout(lists_row)

        # нижний ряд — сброс к дефолту
        bottom_row = QtWidgets.QHBoxLayout()
        bottom_row.addStretch()
        self.omto_reset_btn = QtWidgets.QPushButton(i18n.tr("reset_default_btn", self.lang))
        self.omto_reset_btn.setToolTip(i18n.tr("reset_omto_tooltip", self.lang))
        bottom_row.addWidget(self.omto_reset_btn)
        omto_layout.addLayout(bottom_row)

        self.omto_editor_group.setLayout(omto_layout)
        omto_inner_layout.addWidget(self.omto_editor_group)
        # === end OMTO editor ===
        # === Aviation editor (внутри блока Завод) ===
        self.aviation_editor_group = QtWidgets.QGroupBox(i18n.tr("aviation_editor_group", self.lang))
        self.aviation_editor_group.setFont(font)
        self.aviation_editor_group.setCheckable(True)
        self.aviation_editor_group.setChecked(False)

        av_layout = QtWidgets.QVBoxLayout()

        av_lists_row = QtWidgets.QHBoxLayout()

        av_left_col = QtWidgets.QVBoxLayout()
        self.aviation_all_items_label = QtWidgets.QLabel(i18n.tr("all_items_label", self.lang))
        av_left_col.addWidget(self.aviation_all_items_label)
        self.aviation_search = QtWidgets.QLineEdit()
        self.aviation_search.setPlaceholderText(i18n.tr("aviation_search_placeholder", self.lang))
        self.aviation_search.setFont(font)
        av_left_col.addWidget(self.aviation_search)
        self.aviation_available_list = QtWidgets.QListWidget()
        self.aviation_available_list.setMinimumHeight(300)
        self.aviation_available_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.aviation_available_list.setFont(font)
        av_left_col.addWidget(self.aviation_available_list)
        av_lists_row.addLayout(av_left_col, 1)

        av_btn_col = QtWidgets.QVBoxLayout()
        av_btn_col.addStretch()
        self.aviation_add_btn = QtWidgets.QPushButton("→  +")
        self.aviation_add_btn.setToolTip(i18n.tr("add_to_aviation_tooltip", self.lang))
        self.aviation_remove_btn = QtWidgets.QPushButton("−  ←")
        self.aviation_remove_btn.setToolTip(i18n.tr("remove_from_aviation_tooltip", self.lang))
        av_btn_col.addWidget(self.aviation_add_btn)
        av_btn_col.addWidget(self.aviation_remove_btn)
        av_btn_col.addStretch()
        av_lists_row.addLayout(av_btn_col)

        av_right_col = QtWidgets.QVBoxLayout()
        self.in_aviation_label = QtWidgets.QLabel(i18n.tr("in_aviation_label", self.lang))
        av_right_col.addWidget(self.in_aviation_label)
        self.aviation_selected_list = QtWidgets.QListWidget()
        self.aviation_selected_list.setMinimumHeight(300)
        self.aviation_selected_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.aviation_selected_list.setFont(font)
        av_right_col.addWidget(self.aviation_selected_list)
        av_lists_row.addLayout(av_right_col, 1)

        av_layout.addLayout(av_lists_row)

        av_bottom_row = QtWidgets.QHBoxLayout()
        av_bottom_row.addStretch()
        self.aviation_reset_btn = QtWidgets.QPushButton(i18n.tr("reset_default_btn", self.lang))
        self.aviation_reset_btn.setToolTip(i18n.tr("reset_aviation_tooltip", self.lang))
        av_bottom_row.addWidget(self.aviation_reset_btn)
        av_layout.addLayout(av_bottom_row)

        self.aviation_editor_group.setLayout(av_layout)
        aviation_inner_layout.addWidget(self.aviation_editor_group)
        # === end Aviation editor ===
        self.factory_group.setLayout(factory_layout)
        main_layout.addWidget(self.factory_group)
        # === конец блока "Завод" ===


        # CHG: checkbox for multiple-of-4 enforcement
        self.mul4_checkbox = QtWidgets.QCheckBox(i18n.tr("mul4_checkbox", self.lang))
        self.mul4_checkbox.setFont(font)
        main_layout.addWidget(self.mul4_checkbox)

        # CHG: three resource-specific free toggles (Emats, Hemats, Rmats)
        self.free_emats_checkbox = QtWidgets.QCheckBox(i18n.tr("free_emats_checkbox", self.lang))
        self.free_emats_checkbox.setFont(font)
        main_layout.addWidget(self.free_emats_checkbox)

        self.free_hemats_checkbox = QtWidgets.QCheckBox(i18n.tr("free_hemats_checkbox", self.lang))
        self.free_hemats_checkbox.setFont(font)
        main_layout.addWidget(self.free_hemats_checkbox)

        # Note: label says "Рматы" — this checkbox controls only RMAT tokens (рмат), not БМАТ.
        self.free_rmats_checkbox = QtWidgets.QCheckBox(i18n.tr("free_rmats_checkbox", self.lang))
        self.free_rmats_checkbox.setFont(font)
        main_layout.addWidget(self.free_rmats_checkbox)

        # Calculate button
        self.calculate_button = QtWidgets.QPushButton(i18n.tr("calculate_btn", self.lang))
        self.calculate_button.setFont(font)
        self.calculate_button.clicked.connect(self.calculate_distribution)
        main_layout.addWidget(self.calculate_button)

        # results area
        content_layout = QtWidgets.QHBoxLayout()
        left_layout = QtWidgets.QVBoxLayout()
        self.result_label = QtWidgets.QLabel(i18n.tr("result_label", self.lang))
        self.result_label.setFont(font)
        left_layout.addWidget(self.result_label)
        self.output_area = QtWidgets.QPlainTextEdit(); self.output_area.setFont(font); self.output_area.setReadOnly(True); left_layout.addWidget(self.output_area)

        right_layout = QtWidgets.QVBoxLayout()
        self.unknown_positions_label = QtWidgets.QLabel(i18n.tr("unknown_positions_label", self.lang))
        self.unknown_positions_label.setFont(font)
        self.unknown_positions_label.setStyleSheet("color: red;")
        right_layout.addWidget(self.unknown_positions_label)
        self.undefined_area = QtWidgets.QPlainTextEdit()
        self.undefined_area.setFont(font)
        self.undefined_area.setReadOnly(True)
        self.undefined_area.setStyleSheet("") 
        self.undefined_area.setMinimumHeight(300)
        right_layout.addWidget(self.undefined_area)

        content_layout.addLayout(left_layout)
        content_layout.addLayout(right_layout)
        main_layout.addLayout(content_layout)

        # --- load resource DB ---
        try:
            with open(resource_path("resources.json"), encoding="utf-8") as f:
                self.resource_db = json.load(f)
        except Exception as e:
            self.output_area.setPlainText(i18n.tr("db_load_error", self.lang, e=e))
            self.resource_db = {}

        self._normalized = { k.lower(): k for k in self.resource_db }
        # Дефолтный список OMTO (из items.py) — для "Сбросить к дефолту"
        # Загружаем дефолтные списки МТО и Лётки из quota_writer (11 и 12 вкладки).
        # Если по каким-то причинам не получится — fallback на SPECIAL_OMTO/SPECIAL_AVIATION.
        _omto_default_from_qw = self._load_defaults_from_quota_writer(page=11)
        _aviation_default_from_qw = self._load_defaults_from_quota_writer(page=12)
        if _omto_default_from_qw:
            self._omto_default = _omto_default_from_qw
        else:
            self._omto_default = [n for n in _IMPORTED_SPECIAL_OMTO if n and isinstance(n, str)]
        self._omto_user = list(self._omto_default)
        self._special_omto = set(n.strip().lower() for n in self._omto_user)
        self._omto_group_expanded = False

        if _aviation_default_from_qw:
            self._aviation_default = _aviation_default_from_qw
        else:
            self._aviation_default = [n for n in _IMPORTED_SPECIAL_AVIATION if n and isinstance(n, str)]
        self._aviation_user = list(self._aviation_default)
        self._special_aviation = set(n.strip().lower() for n in self._aviation_user)
        self._aviation_group_expanded = False
        self.discounted_items = {"Dunne Fuelrunner 2d","Dunne Loadlugger 3c","Dunne Transport","BMS - Aquatipper","BMS - Ironship",
                                 "Kivela Power Wheel 80-1","Dunne Responder 3e","O'Brien V.190 Knave","Dunne Caravaner 2f",
                                 "BMS - Universal Assembly Rig","BMS - Class 2 Mobile Auto-Crane"}

        # CHG: feature flags defaults
        self.enforce_multiple_of_4 = True
        self.free_emats = False
        self.free_hemats = False
        self.free_rmats = False

        # load settings (restores division_count and saved counts/names)
        self.load_settings()
        self.generate_division_fields()
        # OMTO editor сигналы
        self.omto_add_btn.clicked.connect(self._omto_on_add)
        # Численность МТО / Лётки → перегенерация полей имён
        self.omto_count_spin.valueChanged.connect(self._rebuild_omto_names)
        self.aviation_count_spin.valueChanged.connect(self._rebuild_aviation_names)
        self.omto_remove_btn.clicked.connect(self._omto_on_remove)
        self.omto_reset_btn.clicked.connect(self._omto_on_reset)
        self.omto_search.textChanged.connect(self._omto_on_search)
        self.omto_available_list.itemDoubleClicked.connect(lambda _it: self._omto_on_add())
        self.omto_selected_list.itemDoubleClicked.connect(lambda _it: self._omto_on_remove())
        self._omto_refresh_lists()
        # Aviation editor сигналы
        self.aviation_add_btn.clicked.connect(self._aviation_on_add)
        self.aviation_remove_btn.clicked.connect(self._aviation_on_remove)
        self.aviation_reset_btn.clicked.connect(self._aviation_on_reset)
        self.aviation_search.textChanged.connect(self._aviation_on_search)
        self.aviation_available_list.itemDoubleClicked.connect(lambda _it: self._aviation_on_add())
        self.aviation_selected_list.itemDoubleClicked.connect(lambda _it: self._aviation_on_remove())
        self._aviation_refresh_lists()
        # apply checkbox states & connect handlers
        self.mul4_checkbox.setChecked(self.enforce_multiple_of_4)
        self.mul4_checkbox.stateChanged.connect(self._on_mul4_toggled)

        self.free_emats_checkbox.setChecked(self.free_emats)
        self.free_emats_checkbox.stateChanged.connect(self._on_free_emats_toggled)

        self.free_hemats_checkbox.setChecked(self.free_hemats)
        self.free_hemats_checkbox.stateChanged.connect(self._on_free_hemats_toggled)

        self.free_rmats_checkbox.setChecked(self.free_rmats)
        self.free_rmats_checkbox.stateChanged.connect(self._on_free_rmats_toggled)

        # set factory quota / omto values from settings
        # Загружаем новые ключи; если их ещё нет (первый запуск после обновления),
        # старое значение factory_quota_text копируем в "Модификации".
        mods_val = self.settings.value("mods_quota_text", None)
        eq_val = self.settings.value("equipment_quota_text", None)
        if mods_val is None and eq_val is None:
            old_val = self.settings.value("factory_quota_text", "")
            self.mods_quota_input.setPlainText(old_val or "")
            self.equipment_quota_input.setPlainText("")
        else:
            self.mods_quota_input.setPlainText(mods_val or "")
            self.equipment_quota_input.setPlainText(eq_val or "")
        self.omto_name_input.setText(self.settings.value("omto_name", ""))

        # styles
        self.setStyleSheet(f"""
            QWidget {{
                background-color: #ffffff;
            }}
            QPlainTextEdit {{
                border: {base_border};
                border-radius: 12px;
                padding: 8px;
                background: transparent;
                font-family: 'JetBrains Mono', 'DejaVu Sans', monospace;
            }}
            QListWidget {{
                border: {base_border};
                border-radius: 8px;
                padding: 4px;
                background: #ffffff;
                outline: 0;
            }}
            QListWidget::item {{
                padding: 3px 6px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background: {primary_color};
                color: white;
            }}
            QListWidget::item:hover {{
                background: #e8f0ff;
            }}
            QGroupBox {{
                border: {base_border};
                border-radius: 12px;
                margin-top: 8px;
                padding-top: 28px;
                padding-left: 12px;
                padding-right: 12px;
                padding-bottom: 12px;
                background: #ffffff;
            }}
            QGroupBox::title {{
                subcontrol-origin: padding;
                subcontrol-position: top left;
                left: 12px;
                top: 6px;
                padding: 0;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: {base_border};
                border-radius: 3px;
                background: #ffffff;
            }}
            QCheckBox::indicator:checked {{
                background: {primary_color};
            }}
                        QGroupBox::indicator {{
                width: 16px;
                height: 16px;
                border: {base_border};
                border-radius: 3px;
                background: #ffffff;
            }}
            QGroupBox::indicator:checked {{
                background: {primary_color};
            }}
            QLineEdit, QSpinBox, QComboBox {{
                border: {base_border};
                border-radius: 8px;
                padding: 6px;
                background: #ffffff;
            }}
            QPushButton {{
                border-radius: 12px;
                padding: 10px 14px;
                font-weight: 700;
                color: white;
                border: {base_border};
                background-color: {primary_color};
            }}
            QPushButton:hover {{
                background-color: #1a7bff;
            }}
            QPushButton:pressed {{
                background-color: #0047b3;
            }}
            QComboBox QAbstractItemView {{
                background: transparent;
                selection-background-color: rgba(0,102,255,0.18);
                selection-color: #071422;
                outline: none;
            }}
            QComboBox::drop-down {{
                width: 0px;
                border: none;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0px; height: 0px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 0px;
                border: none;
                subcontrol-origin: padding;
                subcontrol-position: top right;
            }}
            QSpinBox::up-arrow, QSpinBox::down-arrow {{
                image: none;
                width: 0px;
                height: 0px;
            }}
            QSpinBox, QAbstractSpinArea {{
                color: #071422;
            }}
            QLabel {{
                border: none;
                color: #071422;
                background: transparent;
            }}
        """)

        # button shadow
        def setup_button_shadow(btn):
            shadow = QtWidgets.QGraphicsDropShadowEffect()
            shadow.setBlurRadius(12)
            shadow.setXOffset(0)
            shadow.setYOffset(0)
            try:
                sc = QtGui.QColor(primary_color); sc.setAlpha(140); shadow.setColor(sc)
            except Exception:
                shadow.setColor(QtGui.QColor(0,0,0,140))
            btn.setGraphicsEffect(shadow)
            blur_anim = QtCore.QPropertyAnimation(shadow, b"blurRadius")
            hf = _HoverShadowFilter(btn, shadow, blur_anim)
            btn.installEventFilter(hf)
            if not hasattr(btn, "_ui_anims"):
                btn._ui_anims = []
            btn._ui_anims.extend([shadow, blur_anim, hf])

        setup_button_shadow(self.calculate_button)
    # --------------------- settings handlers ---------------------
    def _on_mul4_toggled(self, state):
        self.enforce_multiple_of_4 = bool(state)
        self.settings.setValue("enforce_mul4", self.enforce_multiple_of_4)

    def _on_free_emats_toggled(self, state):
        self.free_emats = bool(state)
        self.settings.setValue("free_emats", self.free_emats)

    def _on_free_hemats_toggled(self, state):
        self.free_hemats = bool(state)
        self.settings.setValue("free_hemats", self.free_hemats)

    def _on_free_rmats_toggled(self, state):
        self.free_rmats = bool(state)
        self.settings.setValue("free_rmats", self.free_rmats)

    # ---- локализация интерфейса ----
    def set_language(self, lang):
        """Переключить язык интерфейса. Вызывается извне (main.py)."""
        if lang not in i18n.LANGS:
            return
        self.lang = lang
        self.retranslate_ui()

    def retranslate_ui(self):
        L = self.lang
        self.setWindowTitle(i18n.tr("main_window_title", L))

        self.calc_group.setTitle(i18n.tr("calc_quota_group", L))
        self.storage_label.setText(i18n.tr("storage_label", L))
        self.storage_input.setPlaceholderText(i18n.tr("storage_placeholder", L))
        self.required_label.setText(i18n.tr("required_label", L))
        self.required_input.setPlaceholderText(i18n.tr("required_placeholder", L))
        self.calc_quota_btn.setText(i18n.tr("calc_quota_btn", L))
        self.calc_quota_btn.setToolTip(i18n.tr("calc_quota_tooltip", L))

        self.unit_name_label.setText(i18n.tr("unit_name_label", L))
        self.main_storage_label.setText(i18n.tr("main_storage_label", L))
        self.storage_password_label.setText(i18n.tr("storage_password_label", L))
        self.plan_until_label.setText(i18n.tr("plan_until_label", L))

        # weekday combo — пересоздаём список, сохраняя текущий выбранный индекс
        cur_idx = self.weekday_combo.currentIndex()
        self.weekday_combo.blockSignals(True)
        self.weekday_combo.clear()
        self.weekday_names = i18n.WEEKDAYS[L]
        self.weekday_combo.addItems(self.weekday_names)
        if 0 <= cur_idx < self.weekday_combo.count():
            self.weekday_combo.setCurrentIndex(cur_idx)
        self.weekday_combo.blockSignals(False)

        self.division_count_label.setText(i18n.tr("division_count_label", L))
        self.quota_label.setText(i18n.tr("quota_label", L))

        self.factory_group.setTitle(i18n.tr("factory_group", L))
        self.omto_subgroup.setTitle(i18n.tr("omto_subgroup", L))
        self.omto_name_label.setText(i18n.tr("omto_name_label", L))
        self.omto_count_label.setText(i18n.tr("headcount_label", L))
        self.mods_label.setText(i18n.tr("mods_label", L))
        self.equipment_label.setText(i18n.tr("equipment_label", L))

        self.aviation_subgroup.setTitle(i18n.tr("aviation_subgroup", L))
        self.aviation_count_label.setText(i18n.tr("headcount_label", L))
        self.aviation_label.setText(i18n.tr("aviation_label", L))
        self.aviation_recipe_btn.setText(i18n.tr("aviation_recipe_btn", L))
        self.aviation_recipe_btn.setToolTip(i18n.tr("aviation_recipe_tooltip", L))

        self.omto_editor_group.setTitle(i18n.tr("omto_editor_group", L))
        self.omto_all_items_label.setText(i18n.tr("all_items_label", L))
        self.omto_search.setPlaceholderText(i18n.tr("omto_search_placeholder", L))
        self.omto_add_btn.setToolTip(i18n.tr("add_to_omto_tooltip", L))
        self.omto_remove_btn.setToolTip(i18n.tr("remove_from_omto_tooltip", L))
        self.in_omto_label.setText(i18n.tr("in_omto_label", L))
        self.omto_reset_btn.setText(i18n.tr("reset_default_btn", L))
        self.omto_reset_btn.setToolTip(i18n.tr("reset_omto_tooltip", L))

        self.aviation_editor_group.setTitle(i18n.tr("aviation_editor_group", L))
        self.aviation_all_items_label.setText(i18n.tr("all_items_label", L))
        self.aviation_search.setPlaceholderText(i18n.tr("aviation_search_placeholder", L))
        self.aviation_add_btn.setToolTip(i18n.tr("add_to_aviation_tooltip", L))
        self.aviation_remove_btn.setToolTip(i18n.tr("remove_from_aviation_tooltip", L))
        self.in_aviation_label.setText(i18n.tr("in_aviation_label", L))
        self.aviation_reset_btn.setText(i18n.tr("reset_default_btn", L))
        self.aviation_reset_btn.setToolTip(i18n.tr("reset_aviation_tooltip", L))

        self.mul4_checkbox.setText(i18n.tr("mul4_checkbox", L))
        self.free_emats_checkbox.setText(i18n.tr("free_emats_checkbox", L))
        self.free_hemats_checkbox.setText(i18n.tr("free_hemats_checkbox", L))
        self.free_rmats_checkbox.setText(i18n.tr("free_rmats_checkbox", L))

        self.calculate_button.setText(i18n.tr("calculate_btn", L))
        self.result_label.setText(i18n.tr("result_label", L))
        self.unknown_positions_label.setText(i18n.tr("unknown_positions_label", L))

        # Динамические поля подразделений — пересоздаём с новыми подписями,
        # значения (имена/численность) сохраняются через QSettings автоматически.
        self.generate_division_fields()

        # Поля имён МТО / лётчиков — плейсхолдеры на новом языке
        self._rebuild_omto_names(self.omto_count_spin.value())
        self._rebuild_aviation_names(self.aviation_count_spin.value())

        # Списки предметов OMTO / Лётного отделения — показываем на новом языке
        self._omto_refresh_lists(self.omto_search.text())
        self._aviation_refresh_lists(self.aviation_search.text())

    # ---- OMTO editor helpers ----
    def _omto_all_item_names(self):
        """Все русские названия из ITEM_NAMES (values), без дубликатов, отсортированные."""
        try:
            names = set(v for v in _IMPORTED_ITEM_NAMES.values() if v and isinstance(v, str))
        except Exception:
            names = set()
        # Добавим и те, что уже в OMTO (могут быть вручную добавленные, которых нет в ITEM_NAMES)
        names |= set(self._omto_user)
        return sorted(names, key=lambda s: s.lower())

    def _omto_refresh_lists(self, search_text=""):
        """Перерисовывает оба QListWidget на основе self._omto_user. Поиск фильтрует оба списка."""
        self.omto_available_list.clear()
        self.omto_selected_list.clear()

        selected_lower = set(s.lower() for s in self._omto_user)
        # ВАЖНО: исключаем из доступных всё, что уже в Лётном (взаимоисключающие)
        try:
            aviation_lower = set(s.lower() for s in self._aviation_user)
        except AttributeError:
            aviation_lower = set()
        search_lower = (search_text or "").strip().lower()

        for name in self._omto_all_item_names():
            if name.lower() in selected_lower:
                continue
            if name.lower() in aviation_lower:
                continue
            if search_lower and search_lower not in name.lower():
                continue
            item = QtWidgets.QListWidgetItem(i18n.tr_item(name, self.lang))
            item.setData(QtCore.Qt.UserRole, name)
            self.omto_available_list.addItem(item)

        # Правый список (в МТО) — тоже фильтруем по тому же поиску
        for name in sorted(self._omto_user, key=lambda s: s.lower()):
            if search_lower and search_lower not in name.lower():
                continue
            item = QtWidgets.QListWidgetItem(i18n.tr_item(name, self.lang))
            item.setData(QtCore.Qt.UserRole, name)
            self.omto_selected_list.addItem(item)

    def _omto_apply_to_special_set(self):
        """Синхронизирует self._special_omto с self._omto_user (используется в is_special_omto)."""
        self._special_omto = set(i18n.normalize_text(n) for n in self._omto_user if n and isinstance(n, str))
    def _rebuild_omto_names(self, count=None):
        """Пересоздаёт поля имён людей МТО под текущую численность."""
        if count is None:
            count = self.omto_count_spin.value()
        # Сохраним старые значения
        old_values = [w.text() for w in self.omto_name_inputs]
        # Очистим контейнер
        for w in self.omto_name_inputs:
            self.omto_names_layout.removeWidget(w)
            w.deleteLater()
        self.omto_name_inputs = []
        # Создадим новые
        for i in range(count):
            le = QtWidgets.QLineEdit()
            le.setPlaceholderText(i18n.tr("person_name_placeholder", self.lang, i=i+1))
            le.setFont(self.omto_name_input.font())
            if i < len(old_values):
                le.setText(old_values[i])
            le.editingFinished.connect(self.save_settings)
            self.omto_names_layout.addWidget(le)
            self.omto_name_inputs.append(le)

    def _rebuild_aviation_names(self, count=None):
        """Пересоздаёт поля имён лётчиков под текущую численность."""
        if count is None:
            count = self.aviation_count_spin.value()
        old_values = [w.text() for w in self.aviation_name_inputs]
        for w in self.aviation_name_inputs:
            self.aviation_names_layout.removeWidget(w)
            w.deleteLater()
        self.aviation_name_inputs = []
        for i in range(count):
            le = QtWidgets.QLineEdit()
            le.setPlaceholderText(i18n.tr("pilot_name_placeholder", self.lang, i=i+1))
            le.setFont(self.aviation_quota_input.font())
            if i < len(old_values):
                le.setText(old_values[i])
            le.editingFinished.connect(self.save_settings)
            self.aviation_names_layout.addWidget(le)
            self.aviation_name_inputs.append(le)
    def _omto_on_add(self):
        items = self.omto_available_list.selectedItems()
        if not items:
            return
        for it in items:
            name = it.data(QtCore.Qt.UserRole) or it.text()
            if name not in self._omto_user:
                self._omto_user.append(name)
        self._omto_apply_to_special_set()
        self._omto_refresh_lists(self.omto_search.text())
        self.save_settings()

    def _omto_on_remove(self):
        items = self.omto_selected_list.selectedItems()
        if not items:
            return
        to_drop = set((it.data(QtCore.Qt.UserRole) or it.text()) for it in items)
        self._omto_user = [n for n in self._omto_user if n not in to_drop]
        self._omto_apply_to_special_set()
        self._omto_refresh_lists(self.omto_search.text())
        self.save_settings()

    def _omto_on_reset(self):
        reply = QtWidgets.QMessageBox.question(
            self, i18n.tr("reset_omto_dialog_title", self.lang),
            i18n.tr("reset_omto_dialog_text", self.lang),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self._omto_user = list(self._omto_default)
        self._omto_apply_to_special_set()
        self._omto_refresh_lists(self.omto_search.text())
        self.save_settings()

    def _omto_on_search(self, text):
        self._omto_refresh_lists(text)
    # ---- end OMTO editor helpers ----
    # ---- Aviation editor helpers ----
    def _aviation_refresh_lists(self, search_text=""):
        self.aviation_available_list.clear()
        self.aviation_selected_list.clear()

        # Исключаем из доступных всё, что уже в МТО (взаимоисключающие)
        omto_lower = set(s.lower() for s in self._omto_user)
        selected_lower = set(s.lower() for s in self._aviation_user)
        search_lower = (search_text or "").strip().lower()

        for name in self._omto_all_item_names():
            if name.lower() in omto_lower:
                continue
            if name.lower() in selected_lower:
                continue
            if search_lower and search_lower not in name.lower():
                continue
            item = QtWidgets.QListWidgetItem(i18n.tr_item(name, self.lang))
            item.setData(QtCore.Qt.UserRole, name)
            self.aviation_available_list.addItem(item)

        for name in sorted(self._aviation_user, key=lambda s: s.lower()):
            if search_lower and search_lower not in name.lower():
                continue
            item = QtWidgets.QListWidgetItem(i18n.tr_item(name, self.lang))
            item.setData(QtCore.Qt.UserRole, name)
            self.aviation_selected_list.addItem(item)

    def _aviation_apply_to_special_set(self):
        self._special_aviation = set(i18n.normalize_text(n) for n in self._aviation_user if n and isinstance(n, str))

    def _aviation_on_add(self):
        items = self.aviation_available_list.selectedItems()
        if not items:
            return
        for it in items:
            name = it.data(QtCore.Qt.UserRole) or it.text()
            if name not in self._aviation_user:
                self._aviation_user.append(name)
        self._aviation_apply_to_special_set()
        self._aviation_refresh_lists(self.aviation_search.text())
        self._omto_refresh_lists(self.omto_search.text())
        self.save_settings()

    def _aviation_on_remove(self):
        items = self.aviation_selected_list.selectedItems()
        if not items:
            return
        to_drop = set((it.data(QtCore.Qt.UserRole) or it.text()) for it in items)
        self._aviation_user = [n for n in self._aviation_user if n not in to_drop]
        self._aviation_apply_to_special_set()
        self._aviation_refresh_lists(self.aviation_search.text())
        self._omto_refresh_lists(self.omto_search.text())
        self.save_settings()

    def _aviation_on_reset(self):
        reply = QtWidgets.QMessageBox.question(
            self, i18n.tr("reset_aviation_dialog_title", self.lang),
            i18n.tr("reset_aviation_dialog_text", self.lang),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self._aviation_user = list(self._aviation_default)
        self._aviation_apply_to_special_set()
        self._aviation_refresh_lists(self.aviation_search.text())
        self._omto_refresh_lists(self.omto_search.text())
        self.save_settings()

    def _aviation_on_search(self, text):
        self._aviation_refresh_lists(text)

    def is_special_aviation(self, raw_name: str) -> bool:
        if not raw_name:
            return False

        def normalize_name(s: str) -> str:
            return i18n.normalize_text(s)

        rn_norm = normalize_name(raw_name)

        if rn_norm in self._special_aviation:
            return True

        try:
            fq_text = (self.aviation_quota_input.toPlainText() or "").strip()
        except Exception:
            fq_text = ""
        if fq_text:
            for line in fq_text.splitlines():
                if not line:
                    continue
                parsed = parse_csv_line(line)
                name_part = parsed[1] if parsed else line.strip()
                if normalize_name(name_part) == rn_norm:
                    return True
        return False
    # ---- end Aviation editor helpers ----

    def _on_calc_quota_btn(self):
        """
        Вычитает содержимое склада из необходимого, результат раскладывает
        по 4 полям квоты: основная / модификации МТО / снаряжение МТО / лётка.
        """
        # Импорт списка модификаций — он в items.py
        try:
            from items import MTO_MODIFICATIONS
        except Exception:
            MTO_MODIFICATIONS = []

        # 1. Парсим необходимое
        required = {}  # name -> count
        for line in self.required_input.toPlainText().splitlines():
            parsed = parse_csv_line(line)
            if not parsed:
                continue
            cnt, name = parsed
            required[name] = required.get(name, 0) + cnt

        # 2. Парсим содержимое склада
        storage = {}
        for line in self.storage_input.toPlainText().splitlines():
            parsed = parse_csv_line(line)
            if not parsed:
                continue
            cnt, name = parsed
            storage[name] = storage.get(name, 0) + cnt

        # 3. Вычитаем: для каждого предмета из required, отнимаем то что есть на складе
        result = {}  # name -> need_more
        for name, need_cnt in required.items():
            have_cnt = storage.get(name, 0)
            diff = need_cnt - have_cnt
            if diff > 0:
                result[name] = diff
        # Если на складе больше — игнорируем (не доплачиваем)
        # Если предмета нет в required — игнорируем

        # 4. Раскладываем результат по 4 полям
        # МТО-список
        try:
            omto_set = set(i18n.normalize_text(s) for s in self._omto_user if s)
        except Exception as e:
            logger.warning(f"_on_calc_quota_btn: omto_set build failed: {e}")
            omto_set = set()
        # Авиа-список
        try:
            aviation_set = set(i18n.normalize_text(s) for s in self._aviation_user if s)
        except Exception as e:
            logger.warning(f"_on_calc_quota_btn: aviation_set build failed: {e}")
            aviation_set = set()
        # Модификации (жёсткий список из items.py)
        mods_set = set(MTO_MODIFICATIONS)

        main_lines = []
        mods_lines = []
        equipment_lines = []
        aviation_lines = []

        for name, cnt in sorted(result.items(), key=lambda x: -x[1]):
            nl = i18n.normalize_text(name)
            line_csv = format_quota_line(name, cnt, self.lang)
            if nl in aviation_set:
                aviation_lines.append(line_csv)
            elif nl in omto_set:
                # Внутри МТО: модификация или снаряжение?
                if name in mods_set:
                    mods_lines.append(line_csv)
                else:
                    equipment_lines.append(line_csv)
            else:
                main_lines.append(line_csv)

        self.quota_input.setPlainText("\n".join(main_lines))
        self.mods_quota_input.setPlainText("\n".join(mods_lines))
        self.equipment_quota_input.setPlainText("\n".join(equipment_lines))
        try:
            self.aviation_quota_input.setPlainText("\n".join(aviation_lines))
        except Exception as e:
            logger.warning(f"_on_calc_quota_btn: writing aviation_quota_input failed: {e}")
    def _on_aviation_recipe_btn(self):
        """Открывает диалог настройки стоимости самолётов."""
        global AV_DEFAULT_COKE, AV_DEFAULT_FUEL, AV_DEFAULT_SCRAP

        # Парсим текущее содержимое квоты Лётки
        text = self.aviation_quota_input.toPlainText()
        lines = text.splitlines()

        # Извлекаем только авиа-заказы
        aviation_entries = []
        for idx, raw_line in enumerate(lines):
            parsed = parse_aviation_quota_line(raw_line)
            if parsed is None:
                continue
            count, name, settings = parsed
            entry = self.resource_db.get(name)
            if not entry or not entry.get("is_aviation"):
                continue
            recipe = entry.get("recipe", {})
            aviation_entries.append((idx, count, name, settings, recipe))

        # Открываем диалог
        dlg = AviationRecipeDialog(
            self,
            aviation_entries,
            default_coke=AV_DEFAULT_COKE,
            default_fuel=AV_DEFAULT_FUEL,
            default_scrap=AV_DEFAULT_SCRAP,
            lang=getattr(self, "lang", "ru"),
        )
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return

        defaults, per_line = dlg.get_results()

        AV_DEFAULT_COKE = defaults["coke"]
        AV_DEFAULT_FUEL = defaults["fuel"]
        AV_DEFAULT_SCRAP = defaults["scrap"]

        # Перезаписываем строки квоты с новыми настройками
        new_lines = list(lines)
        for idx, count, name, _, _ in aviation_entries:
            if idx in per_line:
                settings = per_line[idx]
            else:
                settings = {
                    "coke": defaults["coke"],
                    "fuel": defaults["fuel"],
                    "scrap": defaults["scrap"],
                }
            new_lines[idx] = serialize_aviation_quota_line(count, i18n.tr_item(name, self.lang), settings)

        self.aviation_quota_input.setPlainText("\n".join(new_lines))
        self.save_settings()
        
    def _build_mto_equipment_output(self):
        """
        Распределяет equipment_quota_input (Снаряжение МТО) по людям МТО.
        Без округления; раздаётся по 1 ящику самому ненагруженному человеку.
        Позиции с ценой и без цены — два независимых пула нагрузки.
        """
        eq_text = self.equipment_quota_input.toPlainText()
        if not eq_text or not eq_text.strip():
            return []

        n_people = self.omto_count_spin.value()
        names = [w.text().strip() or i18n.tr("person_default_name", self.lang, i=i+1)
                 for i, w in enumerate(self.omto_name_inputs)]
        if n_people == 0 or not names:
            return []

        # Парсим позиции
        positions_with_price = []  # (name, count_rounded, cost_per_box_sum)
        positions_no_price = []    # (name, count_rounded)
        for line in eq_text.splitlines():
            parsed = parse_csv_line(line)
            if not parsed:
                continue
            cnt, name = parsed
            entry = self.resource_db.get(name)
            if entry and entry.get("cost_per_box") is not None:
                costs = entry.get("cost_per_box")
                if isinstance(costs, list):
                    cost_sum = sum(c for c in costs if c)
                else:
                    cost_sum = costs or 0
                positions_with_price.append((name, cnt, cost_sum))
            else:
                positions_no_price.append((name, cnt))

        # Раздаём по 1 штуке за раз человеку с минимальной текущей нагрузкой
        # (жадный алгоритм, не чанками — комментарий ниже раньше врал про чанки по 10)
        # per_person_items: list of dicts {name: count}
        per_person_items = [dict() for _ in range(n_people)]
        # Нагрузки по двум пулам
        load_with_price = [0] * n_people
        load_no_price = [0] * n_people

        # Сначала позиции с ценой (тяжёлые)
        # Сортируем по убыванию цены — большие чанки раньше
        positions_with_price.sort(key=lambda x: -x[2])
        for name, cnt, cost_per_box in positions_with_price:
            left = cnt
            while left > 0:
                # ищем человека с минимальной нагрузкой
                idx = load_with_price.index(min(load_with_price))
                per_person_items[idx][name] = per_person_items[idx].get(name, 0) + 1
                load_with_price[idx] += cost_per_box
                left -= 1

        # Затем без цены
        for name, cnt in positions_no_price:
            left = cnt
            while left > 0:
                idx = load_no_price.index(min(load_no_price))
                per_person_items[idx][name] = per_person_items[idx].get(name, 0) + 1
                load_no_price[idx] += 1
                left -= 1  

        # Вывод
        out = []
        for i in range(n_people):
            if not per_person_items[i]:
                continue  # пустой — пропускаем
            out.append(i18n.tr("equipment_section_header", self.lang, name=names[i]))
            for name, cnt in per_person_items[i].items():
                out.append(f"  {format_quota_line(name, cnt, self.lang)}")
        if out:
            out.append("")
        return out

    def _build_mto_modifications_output(self):
        """
        Распределяет mods_quota_input (Модификации МТО) по людям МТО.
        Не округляет. Старается отдать позицию целиком одному человеку,
        если это не сильно нарушает равномерность.
        """
        mods_text = self.mods_quota_input.toPlainText()
        if not mods_text or not mods_text.strip():
            return []

        n_people = self.omto_count_spin.value()
        names = [w.text().strip() or i18n.tr("person_default_name", self.lang, i=i+1)
                 for i, w in enumerate(self.omto_name_inputs)]
        if n_people == 0 or not names:
            return []

        # Парсим позиции
        positions = []  # (name, count)
        total = 0
        for line in mods_text.splitlines():
            parsed = parse_csv_line(line)
            if not parsed:
                continue
            cnt, name = parsed
            positions.append((name, cnt))
            total += cnt

        if not positions:
            return []

        avg_per_person = total / n_people if n_people else 0

        per_person_items = [dict() for _ in range(n_people)]
        loads = [0] * n_people

        # Сортируем позиции по убыванию количества
        positions.sort(key=lambda x: -x[1])

        for name, cnt in positions:
            # Если позиция целиком помещается одному, и это не нарушает равномерность
            min_load_idx = loads.index(min(loads))
            after = loads[min_load_idx] + cnt
            
            # Целиком одному, если после этого его нагрузка не превышает
            # avg + max_position_size_in_remaining (грубо: не сильно перегружен)
            if cnt <= avg_per_person + 1 or after <= avg_per_person + cnt / 2:
                per_person_items[min_load_idx][name] = cnt
                loads[min_load_idx] += cnt
            else:
                # Раскидываем равномерно с остатком первым
                base = cnt // n_people
                rem = cnt - base * n_people
                for i in range(n_people):
                    portion = base + (1 if i < rem else 0)
                    if portion > 0:
                        per_person_items[i][name] = per_person_items[i].get(name, 0) + portion
                        loads[i] += portion

        # Вывод
        out = []
        for i in range(n_people):
            if not per_person_items[i]:
                continue
            out.append(i18n.tr("mods_section_header", self.lang, name=names[i]))
            for name, cnt in per_person_items[i].items():
                out.append(f"  {format_quota_line(name, cnt, self.lang)}")
        if out:
            out.append("")
        return out
    def _build_aviation_output(self):
        """
        Парсит aviation_quota_input, считает базовые ресурсы через калькулятор,
        делит всё на лётчиков и возвращает список строк для вывода.
        Если авиа-квота пуста — возвращает [].
        """
        av_text = self.aviation_quota_input.toPlainText()
        if not av_text or not av_text.strip():
            return []

        # Сколько лётчиков
        n_pilots = self.aviation_count_spin.value()
        pilot_names = [w.text().strip() or i18n.tr("person_default_name", self.lang, i=i+1)
                       for i, w in enumerate(self.aviation_name_inputs)]
        if n_pilots == 0 or not pilot_names:
            return [i18n.tr("aviation_section_header", self.lang),
                    i18n.tr("aviation_zero_pilots", self.lang),
                    ""]

        # Парсим каждую строку
        # aviation_items_per_pilot: список словарей по каждому лётчику с обычными предметами
        # base_per_pilot: список словарей по каждому лётчику с базовыми ресами
        avi_orders = []  # самолёты
        common_orders = []  # обычные

        for raw_line in av_text.splitlines():
            parsed = parse_aviation_quota_line(raw_line)
            if parsed is None:
                continue
            count, name, settings = parsed
            entry = self.resource_db.get(name)
            if not entry:
                # неизвестное имя — игнорируем
                continue
            if entry.get("is_aviation"):
                avi_orders.append((count, name, settings, entry.get("recipe", {})))
            else:
                # обычный предмет (типа аптечки) - имеет cost_per_box
                common_orders.append((count, name, entry))

        # === Считаем базовые ресы для авиа ===
        total_base = {"coal": 0, "scrap": 0, "components": 0,
                      "sulfur": 0, "rare_mats": 0}

        for count, name, settings, recipe in avi_orders:
            scrap_ratio = settings.get("scrap", AV_DEFAULT_SCRAP) / 100.0
            bc = _aviation_calc_base_cost(
                recipe,
                count,
                coke_recipe=settings.get("coke", AV_DEFAULT_COKE),
                fuel_recipe=settings.get("fuel", AV_DEFAULT_FUEL),
                scrap_ratio=scrap_ratio,
            )
            if bc is None:
                continue
            total_base["coal"] += getattr(bc, "coal", 0)
            total_base["scrap"] += getattr(bc, "scrap", 0)
            total_base["components"] += getattr(bc, "components", 0)
            total_base["sulfur"] += bc.net_sulfur() if hasattr(bc, "net_sulfur") else getattr(bc, "sulfur", 0)
            total_base["rare_mats"] += getattr(bc, "rare_mats", 0)

        # === Делим базовые ресы на лётчиков (поровну, остаток первым) ===
        per_pilot_base = [{"coal": 0, "scrap": 0, "components": 0,
                          "sulfur": 0, "rare_mats": 0}
                         for _ in range(n_pilots)]
        for resource, total in total_base.items():
            base = total // n_pilots
            remainder = total - base * n_pilots
            for i in range(n_pilots):
                per_pilot_base[i][resource] = base + (1 if i < remainder else 0)

        # === Делим обычные предметы (count - name) на лётчиков ===
        # Простое деление целыми штуками, остаток первым
        per_pilot_common = [[] for _ in range(n_pilots)]
        for total_count, name, entry in common_orders:
            base = total_count // n_pilots
            remainder = total_count - base * n_pilots
            for i in range(n_pilots):
                cnt = base + (1 if i < remainder else 0)
                if cnt > 0:
                    per_pilot_common[i].append((cnt, name))

        # === Формируем вывод ===
        out = [i18n.tr("aviation_section_header", self.lang)]
        for i in range(n_pilots):
            pname = pilot_names[i] if i < len(pilot_names) else i18n.tr("person_default_name", self.lang, i=i+1)
            out.append(f"  {pname}:")
            # Обычные предметы
            for cnt, name in per_pilot_common[i]:
                out.append(f"    {cnt} - {i18n.tr_item(name, self.lang)}")
            # Базовые ресы
            for key in ("coal", "scrap", "components", "sulfur", "rare_mats"):
                v = per_pilot_base[i].get(key, 0)
                if v > 0:
                    out.append(f"    {i18n.tr_aviation_resource(key, self.lang)}: {v}")
        out.append("")
        return out
    def save_settings(self):
        try:
            self.settings.setValue("av_default_coke", AV_DEFAULT_COKE)
            self.settings.setValue("av_default_fuel", AV_DEFAULT_FUEL)
            self.settings.setValue("av_default_scrap", AV_DEFAULT_SCRAP)
        except Exception as e:
            logger.warning(f"settings: av_default_coke failed: {e}")
        self.settings.setValue("unit_name", self.unit_name_input.text())
        self.settings.setValue("storage_name", self.storage_name_input.text())
        self.settings.setValue("storage_pass", self.storage_pass_input.text())
        self.settings.setValue("division_count", self.division_count_input.value())
        self.settings.setValue("quota_text", self.quota_input.toPlainText())
        self.settings.setValue("target_weekday", self.weekday_combo.currentIndex())
        for i, (name_edit, spin) in enumerate(zip(self.division_names, self.division_inputs)):
            self.settings.setValue(f"division_name_{i}", name_edit.text())
            self.settings.setValue(f"division_people_{i}", spin.value())
        self.settings.setValue("mods_quota_text", self.mods_quota_input.toPlainText())
        self.settings.setValue("equipment_quota_text", self.equipment_quota_input.toPlainText())
        # Старый ключ оставляем для обратной совместимости (на случай отката)
        self.settings.setValue("factory_quota_text", self.mods_quota_input.toPlainText())
        self.settings.setValue("omto_name", self.omto_name_input.text())
        self.settings.setValue("enforce_mul4", self.enforce_multiple_of_4)
        self.settings.setValue("free_emats", self.free_emats)
        self.settings.setValue("free_hemats", self.free_hemats)
        self.settings.setValue("free_rmats", self.free_rmats)
        # Пользовательский список МТО
        # OMTO custom list + state
        try:
            self.settings.setValue("omto_custom_list", json.dumps(self._omto_user, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"settings: omto_custom_list failed: {e}")
        try:
            self.settings.setValue("omto_group_expanded", bool(self.omto_editor_group.isChecked()))
        except Exception as e:
            logger.warning(f"settings: omto_group_expanded failed: {e}")

        # Aviation custom list + state + text
        try:
            self.settings.setValue("aviation_custom_list", json.dumps(self._aviation_user, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"settings: aviation_custom_list failed: {e}")
        try:
            self.settings.setValue("aviation_group_expanded", bool(self.aviation_editor_group.isChecked()))
        except Exception as e:
            logger.warning(f"settings: aviation_group_expanded failed: {e}")
        try:
            self.settings.setValue("aviation_quota_text", self.aviation_quota_input.toPlainText())
        except Exception as e:
            logger.warning(f"settings: aviation_quota_text failed: {e}")
        try:
            self.settings.setValue("storage_input", self.storage_input.toPlainText())
        except Exception as e:
            logger.warning(f"settings: storage_input failed: {e}")
        try:
            self.settings.setValue("required_input", self.required_input.toPlainText())
        except Exception as e:
            logger.warning(f"settings: required_input failed: {e}")
# Численность МТО (сохраняем всегда)
        try:
            self.settings.setValue("omto_count", self.omto_count_spin.value())
        except Exception as e:
            logger.warning(f"settings: omto_count failed: {e}")
        # Имена МТО — только если есть текущие поля (не затираем при count=0)
        try:
            if self.omto_name_inputs:
                self.settings.setValue("omto_names",
                    json.dumps([w.text() for w in self.omto_name_inputs], ensure_ascii=False))
        except Exception as e:
            logger.warning(f"settings: omto_names failed: {e}")

        # Численность Лётки (сохраняем всегда)
        try:
            self.settings.setValue("aviation_count", self.aviation_count_spin.value())
        except Exception as e:
            logger.warning(f"settings: aviation_count failed: {e}")
        # Имена Лётки — только если есть текущие поля
        try:
            if self.aviation_name_inputs:
                self.settings.setValue("aviation_names",
                    json.dumps([w.text() for w in self.aviation_name_inputs], ensure_ascii=False))
        except Exception as e:
            logger.warning(f"settings: aviation_names failed: {e}")
    def load_settings(self):
                # Дефолты калькулятора авиа (глобальные)
        global AV_DEFAULT_COKE, AV_DEFAULT_FUEL, AV_DEFAULT_SCRAP
        try:
            v = self.settings.value("av_default_coke", AV_DEFAULT_COKE)
            if v in ("with_sulfur", "no_sulfur"):
                AV_DEFAULT_COKE = v
            v = self.settings.value("av_default_fuel", AV_DEFAULT_FUEL)
            if v in ("sulfur", "coal"):
                AV_DEFAULT_FUEL = v
            v = self.settings.value("av_default_scrap", AV_DEFAULT_SCRAP)
            try:
                AV_DEFAULT_SCRAP = max(0, min(100, int(v)))
            except (ValueError, TypeError):
                pass
        except Exception as e:
            logger.warning(f"settings: av_default_coke failed: {e}")
        self.unit_name_input.setText(self.settings.value("unit_name", ""))
        self.storage_name_input.setText(self.settings.value("storage_name", ""))
        self.storage_pass_input.setText(self.settings.value("storage_pass", ""))
        try:
            self.division_count_input.setValue(int(self.settings.value("division_count", 3)))
        except Exception:
            self.division_count_input.setValue(3)
        self.quota_input.setPlainText(self.settings.value("quota_text", ""))
        try:
            idx = int(self.settings.value("target_weekday", 4))
        except Exception:
            idx = 4
        if 0 <= idx < len(self.weekday_names):
            self.weekday_combo.setCurrentIndex(idx)
        try:
            self.enforce_multiple_of_4 = bool(self.settings.value("enforce_mul4", True) in (True, 'true', '1', 1, 'True', 'true'))
        except Exception:
            self.enforce_multiple_of_4 = True
        try:
            self.free_emats = bool(self.settings.value("free_emats", False) in (True, 'true', '1', 1, 'True', 'true'))
        except Exception:
            self.free_emats = False
        try:
            self.free_hemats = bool(self.settings.value("free_hemats", False) in (True, 'true', '1', 1, 'True', 'true'))
        except Exception:
            self.free_hemats = False
        try:
            if self.settings.contains("free_rmats"):
                self.free_rmats = bool(self.settings.value("free_rmats", False) in (True, 'true', '1', 1, 'True', 'true'))
            else:
                self.free_rmats = bool(self.settings.value("free_bmats", False) in (True, 'true', '1', 1, 'True', 'true'))
        except Exception:
            self.free_rmats = False
                    # OMTO custom list
        try:
            raw = self.settings.value("omto_custom_list", "")
            if raw:
                loaded = json.loads(raw)
                if isinstance(loaded, list):
                    self._omto_user = [str(n) for n in loaded if n]
                else:
                    self._omto_user = list(self._omto_default)
            else:
                self._omto_user = list(self._omto_default)
        except Exception:
            self._omto_user = list(self._omto_default)
        self._omto_apply_to_special_set()

        # OMTO group expanded state
        try:
            val = self.settings.value("omto_group_expanded", False)
            expanded = bool(val in (True, 'true', 'True', 1, '1'))
            self.omto_editor_group.setChecked(expanded)
        except Exception as e:
            logger.warning(f"settings: omto_group_expanded failed: {e}")

        # Aviation custom list
        try:
            raw = self.settings.value("aviation_custom_list", "")
            if raw:
                loaded = json.loads(raw)
                if isinstance(loaded, list):
                    self._aviation_user = [str(n) for n in loaded if n]
                else:
                    self._aviation_user = list(self._aviation_default)
            else:
                self._aviation_user = list(self._aviation_default)
        except Exception:
            self._aviation_user = list(self._aviation_default)
        self._aviation_apply_to_special_set()

        # Aviation group expanded state
        try:
            val = self.settings.value("aviation_group_expanded", False)
            expanded = bool(val in (True, 'true', 'True', 1, '1'))
            self.aviation_editor_group.setChecked(expanded)
        except Exception as e:
            logger.warning(f"settings: aviation_group_expanded failed: {e}")

        # Aviation quota text
        try:
            self.aviation_quota_input.setPlainText(self.settings.value("aviation_quota_text", ""))
        except Exception as e:
            logger.warning(f"settings: aviation_quota_text failed: {e}")
        try:
            self.storage_input.setPlainText(self.settings.value("storage_input", ""))
        except Exception as e:
            logger.warning(f"settings: storage_input failed: {e}")
        try:
            self.required_input.setPlainText(self.settings.value("required_input", ""))
        except Exception as e:
            logger.warning(f"settings: required_input failed: {e}")
        # Численность МТО и Лётки + имена
        try:
            cnt = int(self.settings.value("omto_count", 0))
            self.omto_count_spin.setValue(cnt)
            self._rebuild_omto_names(cnt)
            raw = self.settings.value("omto_names", "")
            if raw:
                names = json.loads(raw)
                for i, name in enumerate(names):
                    if i < len(self.omto_name_inputs):
                        self.omto_name_inputs[i].setText(str(name))
        except Exception as e:
            logger.warning(f"settings: omto_count failed: {e}")

        try:
            cnt = int(self.settings.value("aviation_count", 0))
            self.aviation_count_spin.setValue(cnt)
            self._rebuild_aviation_names(cnt)
            raw = self.settings.value("aviation_names", "")
            if raw:
                names = json.loads(raw)
                for i, name in enumerate(names):
                    if i < len(self.aviation_name_inputs):
                        self.aviation_name_inputs[i].setText(str(name))
        except Exception as e:
            logger.warning(f"settings: aviation_count failed: {e}")

    def closeEvent(self, event):
        try:
            for i, (ne, sp) in enumerate(zip(self.division_names, self.division_inputs)):
                self.settings.setValue(f"division_name_{i}", ne.text())
                self.settings.setValue(f"division_people_{i}", sp.value())
        except Exception as e:
            logger.warning(f"settings: operation failed: {e}")
# Сохраняем геометрию окна
        try:
            self.settings.setValue("window_geometry", self.saveGeometry())
        except Exception as e:
            logger.warning(f"settings: window_geometry failed: {e}")
        self.save_settings()
        super().closeEvent(event)

    # --------------------- dynamic division fields ---------------------
    def generate_division_fields(self):
        try:
            for i, (ne, sp) in enumerate(zip(self.division_names, self.division_inputs)):
                self.settings.setValue(f"division_name_{i}", ne.text())
                self.settings.setValue(f"division_people_{i}", sp.value())
        except Exception as e:
            logger.warning(f"settings: operation failed: {e}")

        def clear_layout(layout):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                elif item.layout():
                    clear_layout(item.layout())
        clear_layout(self.division_inputs_container)

        self.division_inputs = []
        self.division_names = []

        font = self.font()
        count = self.division_count_input.value()
        for i in range(count):
            hbox = QtWidgets.QHBoxLayout()
            name_edit = QtWidgets.QLineEdit(); name_edit.setFont(font); name_edit.setPlaceholderText(i18n.tr("unit_name_input_placeholder", self.lang)); name_edit.setMinimumWidth(250)
            spin = QtWidgets.QSpinBox(); spin.setFont(font); spin.setRange(1,100); spin.setValue(1)

            name_edit.setText(self.settings.value(f"division_name_{i}", ""))
            try:
                spin.setValue(int(self.settings.value(f"division_people_{i}", spin.value())))
            except Exception:
                spin.setValue(spin.value())

            label = QtWidgets.QLabel(i18n.tr("division_number_label", self.lang, i=i+1)); label.setFont(font)
            hbox.addWidget(label); hbox.addWidget(name_edit); hbox.addWidget(QtWidgets.QLabel(i18n.tr("people_suffix_label", self.lang))); hbox.addWidget(spin)
            self.division_inputs_container.addLayout(hbox)
            self.division_names.append(name_edit); self.division_inputs.append(spin)

            def make_people_handler(idx):
                def handler(val):
                    try:
                        self.settings.setValue(f"division_people_{idx}", int(val))
                    except Exception as e:
                        logger.warning(f"settings: operation failed: {e}")
                return handler
            spin.valueChanged.connect(make_people_handler(i))

            def make_name_handler(idx):
                def handler(text):
                    try:
                        self.settings.setValue(f"division_name_{idx}", text)
                    except Exception as e:
                        logger.warning(f"settings: operation failed: {e}")
                return handler
            name_edit.textChanged.connect(make_name_handler(i))

    # --------------------- quota parsing & totals ---------------------
    def _collect_quota_entries(self):
        # Дубликаты строк одного предмета сливаются ДО округления до кратности:
        # иначе "Бинты,2" + "Бинты,2" двумя строками дают ceil(2/4)*4 + ceil(2/4)*4 = 8
        # ящиков вместо ceil(4/4)*4 = 4, а две строки техники группы 8 — две
        # отдельные "глыбы" в разные подразделения.
        merged, undefined = {}, []
        for line in self.quota_input.toPlainText().splitlines():
            parsed = parse_csv_line(line)
            if not parsed:
                continue
            cnt, raw = parsed
            key = raw.lower()
            if key in self._normalized:
                name = self._normalized[key]
                merged[name] = merged.get(name, 0) + cnt
            else:
                undefined.append(raw)
        return list(merged.items()), undefined
    
    def _is_omto_raw(self, raw: str) -> bool:
        if not raw:
            return False

        def normalize_name(s: str) -> str:
            if not s:
                return ""
            s = i18n.normalize_text(s)

            def remove_unit_parentheticals(text: str) -> str:
                out = text
                for m in re.finditer(r'\(([^)]*)\)', text):
                    inside = m.group(1).strip().lower()
                    if re.fullmatch(r'(?:(?:шт(?:\.|))|штука|ящ(?:\.|ик)?|box|crate|короб(?:к)?)', inside, flags=re.IGNORECASE):
                        out = out.replace(m.group(0), ' ')
                return out
            s = remove_unit_parentheticals(s)
            s = re.sub(r'(?:\s|^)(?:шт(?:\.|)|штука|ящ(?:\.|ик)?|box|crate|короб(?:к)?)\s*$', '', s, flags=re.IGNORECASE)
            s = re.sub(r'["\'.,:;!?]+', ' ', s)
            s = re.sub(r'\s+', ' ', s).strip()
            return s

        rn_norm = normalize_name(raw)

        # Проверяем только точное совпадение с SPECIAL_OMTO
        for s in self._special_omto:
            if not s:
                continue
            if normalize_name(s) == rn_norm:
                return True

# Проверяем оба поля заводской квоты для точного совпадения
        for fq_text in [
            (self.mods_quota_input.toPlainText() or "").strip(),
            (self.equipment_quota_input.toPlainText() or "").strip(),
        ]:
            if not fq_text:
                continue
            for line in fq_text.splitlines():
                if not line:
                    continue
                parsed = parse_csv_line(line)
                name_part = parsed[1] if parsed else line.strip()
                if normalize_name(name_part) == rn_norm:
                    return True

        return False

    def _is_box_position(self, item_name: str, resource_name: str) -> bool:
        if not item_name or not resource_name:
            return False
        iname = item_name.lower()
        rname = resource_name.lower()
        if iname == rname:
            return True
        if iname.startswith(rname) or iname.endswith(rname):
            return True
        if rname in iname and any(k in iname for k in ('ящ', 'ящ.', 'box', 'короб', 'коробк', 'crate')):
            return True
        return False

    def _should_count_resource_cost(self, item_name: str, resource_name: str) -> bool:
        if not resource_name:
            return True

        item_norm = (item_name or "").strip().lower()
        res_norm = resource_name.strip().lower()

        if item_norm in getattr(self, "free_exceptions", set()):
            return True

        def matches_any_in(s, tokens):
            for t in tokens:
                pattern = r'(?<![0-9A-Za-zА-Яа-яЁё])' + re.escape(t) + r'(?![0-9A-Za-zА-Яа-яЁё])'
                if re.search(pattern, s, flags=re.IGNORECASE):
                    return True
            return False

        emat_tokens = ['emat', 'емат', 'emats', 'ематы']
        hemat_tokens = ['hemat', 'хемат', 'xemat', 'hemats', 'хематы']
        rmat_tokens = ['rmat', 'рмат', 'rmats', 'рматы']
        bmat_tokens = ['bmat', 'бмат', 'bmats', 'бматы']

        if matches_any_in(res_norm, emat_tokens):
            return not getattr(self, "free_emats", False)

        if matches_any_in(res_norm, hemat_tokens):
            return not getattr(self, "free_hemats", False)

        if matches_any_in(res_norm, rmat_tokens):
            return not getattr(self, "free_rmats", False)

        if matches_any_in(res_norm, bmat_tokens):
            return True

        return True

    def _calculate_totals(self, item_entries):
        totals = defaultdict(float)
        for name, cnt in item_entries:
            entry = self.resource_db.get(name)
            if not entry:
                continue
            # Авиа-предметы обрабатываются отдельно (через _build_aviation_output)
            if entry.get('is_aviation'):
                continue
            scheme = entry.get("distribution", "per_person")
            resources = entry.get('resource')
            costs = entry.get('cost_per_box')
            if resources is None or costs is None:
                continue
            pairs = list(zip(resources, costs)) if isinstance(resources, list) else [(resources, costs)]

            for r, c in pairs:
                if not self._should_count_resource_cost(name, r):
                    continue

                if scheme == "per_9":
                    used = self._discounted_sum(c, cnt, 9)
                elif scheme == "per_person":
                    used = self._discounted_sum(c, cnt, 5)
                else:
                    used = c * cnt

                totals[r] += used
        return totals

    def _discounted_sum(self, base, count, group_size, per_box_round='floor'):
        vals = []
        for k in range(count):
            pos = (k % group_size) + 1
            disc = min(pos * 0.1, 0.5)
            vals.append(base * (1 - disc))

        if per_box_round is None:
            return sum(vals)

        if per_box_round == 'round_total':
            return float(round(sum(vals)))

        total = 0.0
        if per_box_round == 'floor':
            for v in vals:
                total += math.floor(v)
        elif per_box_round == 'ceil':
            for v in vals:
                total += math.ceil(v)
        elif per_box_round == 'round':
            for v in vals:
                total += round(v)
        else:
            total = sum(vals)
        return float(total)

    def _format_totals_output(self, total_resources, avg_per_person):
        lines = [i18n.tr("totals_header", self.lang)]
        for r,v in total_resources.items(): lines.append(f"  {i18n.tr_resource(r, self.lang)}: {v}")
        lines.append(""); lines.append(i18n.tr("avg_per_person_header", self.lang))
        for r,avg in avg_per_person.items(): lines.append(f"  {i18n.tr_resource(r, self.lang)}: {round(avg,2)}")
        lines.append(""); return lines

    # --------------------- grouping helpers ---------------------
    def _group_items_per_person(self, division_index, group_name, distribution, divisions):
        if group_name is None:
            return 0.0
        total = 0
        for iname, cnt in distribution[division_index].items():
            entry = self.resource_db.get(iname, {})
            if entry.get("group") == group_name:
                total += cnt
        people = divisions[division_index] if divisions[division_index] else 1
        return total / people

    def _combined_load_for_resource(self, div_idx, resource, used_actual, used_nominal):
        """
        Нагрузка подразделения div_idx по одному ресурсу для балансировки:
        actual, если он платный (actual > 0), иначе nominal (ресурс бесплатный,
        но всё равно должен распределяться по справедливости).
        Общая точка входа — раньше эта формула была скопирована в 6 разных местах.
        """
        actual_val = used_actual[div_idx].get(resource, 0)
        nominal_val = used_nominal[div_idx].get(resource, 0)
        if nominal_val > 0 and actual_val == 0:
            return nominal_val
        return actual_val

    def _combined_load_total(self, div_idx, used_actual, used_nominal):
        """Сумма _combined_load_for_resource по всем ресурсам подразделения div_idx."""
        all_res = set(used_actual[div_idx].keys()) | set(used_nominal[div_idx].keys())
        return sum(self._combined_load_for_resource(div_idx, r, used_actual, used_nominal)
                   for r in all_res)

    def _min_load_index(self, distribution, used_actual, used_nominal, divisions):
        loads = []
        for i in range(len(divisions)):
            combined_load = self._combined_load_total(i, used_actual, used_nominal)
            per_person_load = (combined_load/divisions[i]) if divisions[i] else float('inf')
            box_count = sum(distribution[i].values())
            loads.append((per_person_load, box_count, i))
        return min(loads)[2]

    # --------------------- main distribution ---------------------
    def _perform_distribution(self, item_entries, divisions, avg_per_person):
        """
        Гибрид:
          1. "Глыбы" (группа 8: весь заказ одному подразделению кратно 5;
             only_one_per_division) — старой логикой, ПЕРВЫМИ.
          2. Все обычные предметы (per_4 / per_9 / per_person / поштучные) —
             fair_allocator: неделимые чанки, BFD по потенциалу + локальный
             поиск move/swap. Глыбы передаются как preload, так что обычные
             предметы выравниваются вокруг них.
          3. balance_fill — как раньше, добивает дефициты последним.
        Пост-балансировка (_balance_by_per_person_load) больше не нужна:
        локальный поиск внутри allocate() делает её работу строго лучше
        (глобальный критерий по всем ресурсам сразу, обмены, гарантированное
        завершение без порогов и max_iterations).
        """
        distribution = defaultdict(lambda: defaultdict(int))
        used_actual = {i: defaultdict(float) for i in range(len(divisions))}
        used_nominal = {i: defaultdict(float) for i in range(len(divisions))}

        delayed, regular = [], []
        for name, cnt in item_entries:
            entry = self.resource_db.get(name, {})
            dist = entry.get("distribution", "per_person")
            if dist == "balance_fill":
                continue
            if (dist == "per_person" and entry.get("group") == 8) \
                    or entry.get("only_one_per_division"):
                delayed.append((name, cnt, dist))
                continue
            regular.append((name, cnt))

        # --- 1. глыбы первыми ---
        self._distribute_delayed(delayed, divisions, distribution, used_actual, used_nominal)

        # --- 2. обычные предметы через fair_allocator ---
        chunks = fair_allocator.make_chunks(
            regular,
            self.resource_db,
            count_resource_cost=self._should_count_resource_cost,
            enforce_mul4=getattr(self, "enforce_multiple_of_4", True),
        )
        if chunks:
            preload = []
            for i in range(len(divisions)):
                d = {}
                for r in set(used_actual[i]) | set(used_nominal[i]):
                    d[r] = self._combined_load_for_resource(i, r, used_actual, used_nominal)
                preload.append(d)

            _loads, assign = fair_allocator.allocate(chunks, divisions, preload=preload)

            placed = defaultdict(lambda: defaultdict(int))
            for (name, boxes, _vec), di in zip(chunks, assign):
                placed[di][name] += boxes

            # used_* восстанавливаем из целых счётчиков — инвариант
            # used_actual[div] == S(count_in_div) держится точно, потому что
            # счётчики кратны размеру чанка (S аддитивна на кратных цикла).
            for i, items_here in placed.items():
                for name, cnt in items_here.items():
                    distribution[i][name] += cnt
                    entry = self.resource_db.get(name, {})
                    dist = entry.get("distribution", "per_person")
                    g = fair_allocator.DISCOUNT_G.get(dist)
                    res = entry.get("resource")
                    cost = entry.get("cost_per_box")
                    pairs = list(zip(res, cost)) if isinstance(res, list) else [(res, cost)]
                    for r, c in pairs:
                        used_nominal[i][r] += c * cnt
                        if not self._should_count_resource_cost(name, r):
                            continue
                        if g:
                            used_actual[i][r] += self._discounted_sum(c, cnt, g)
                        else:
                            used_actual[i][r] += float(c * cnt)

        # --- 3. balance_fill последним ---
        self._distribute_balance(item_entries, divisions, avg_per_person, distribution, used_actual, used_nominal)

        return distribution, used_actual, used_nominal

    def _distribute_delayed(self, delayed, divisions, distribution, used_actual, used_nominal):
        assigned_pp = defaultdict(int); assigned_once = set()
        for name, cnt, dtype in delayed:
            entry = self.resource_db.get(name, {})
            res = entry.get("resource"); cost = entry.get("cost_per_box")
            pairs = list(zip(res, cost)) if isinstance(res, list) else [(res, cost)]
            
            if dtype == "per_person":
                group = entry.get("group")
                # Специальная логика для группы 8: распределяем только 1 раз, кратно 5
                if group == 8:
                    # Округляем до кратности 5
                    boxes_to_give = int(math.ceil(cnt / 5) * 5)
                    
                    # Находим подразделение с минимальной нагрузкой
                    best_i = None
                    best_score = None
                    for i in range(len(divisions)):
                        gc_pp = self._group_items_per_person(i, group, distribution, divisions)
                        combined_load = self._combined_load_total(i, used_actual, used_nominal)
                        per_person_load = (combined_load / divisions[i]) if divisions[i] else float('inf')
                        box_count = sum(distribution[i].values())
                        score = (gc_pp, per_person_load, box_count)
                        if best_score is None or score < best_score:
                            best_score = score
                            best_i = i
                    
                    if best_i is not None:
                        distribution[best_i][name] += boxes_to_give
                        for r, c in pairs:
                            used_nominal[best_i][r] += c * boxes_to_give
                            if not self._should_count_resource_cost(name, r):
                                continue
                            used_actual[best_i][r] += self._discounted_sum(c, boxes_to_give, 5)
                else:
                    # Обычная логика для других групп
                    chunks = [5] * (cnt // 5) + ([cnt % 5] if cnt % 5 else [])
                    limit = 1
                    for chunk in chunks:
                        placed = False
                        while not placed:
                            candidates = []
                            for i in range(len(divisions)):
                                if assigned_pp[i] < limit:
                                    gc_pp = self._group_items_per_person(i, entry.get("group"), distribution, divisions)
                                    combined_load = self._combined_load_total(i, used_actual, used_nominal)
                                    per_person_load = (combined_load / divisions[i]) if divisions[i] else float('inf')
                                    box_count = sum(distribution[i].values())
                                    candidates.append(((gc_pp, per_person_load, box_count, i), i))
                            if candidates:
                                candidates.sort(key=lambda x: x[0])
                                chosen_i = candidates[0][1]
                                distribution[chosen_i][name] += chunk
                                for r, c in pairs:
                                    used_nominal[chosen_i][r] += c * chunk
                                    if not self._should_count_resource_cost(name, r):
                                        continue
                                    used_actual[chosen_i][r] += self._discounted_sum(c, chunk, 5)
                                assigned_pp[chosen_i] += 1
                                placed = True
                            else:
                                limit += 1
            else:
                # only_one_per_division
                for _ in range(cnt):
                    placed = False
                    available = [j for j in range(len(divisions)) if j not in assigned_once]
                    best = None
                    for j in available:
                        gc_pp = self._group_items_per_person(j, entry.get("group"), distribution, divisions)
                        combined_load = self._combined_load_total(j, used_actual, used_nominal)
                        per_person_load = (combined_load / divisions[j]) if divisions[j] else float('inf')
                        box_count = sum(distribution[j].values())
                        score = (gc_pp, per_person_load, box_count)
                        if best is None or score < best[0]:
                            best = (score, j)
                    if best is not None:
                        chosen = best[1]
                        distribution[chosen][name] += 1
                        for r, c in pairs:
                            used_nominal[chosen][r] += c
                            used_actual[chosen][r] += c
                        assigned_once.add(chosen)
                        placed = True
                    if not placed:
                        i = self._min_load_index(distribution, used_actual, used_nominal, divisions)
                        distribution[i][name] += 1
                        for r, c in pairs:
                            used_nominal[i][r] += c
                            used_actual[i][r] += c

    def _distribute_balance(self, item_entries, divisions, avg_per_person, distribution, used_actual, used_nominal):
        counts = defaultdict(int)
        for name,cnt in item_entries: counts[name]+=cnt
        for name,cnt in counts.items():
            entry = self.resource_db.get(name,{})
            if entry.get("distribution") != "balance_fill": continue
            res = entry.get("resource"); cost = entry.get("cost_per_box")
            pairs = list(zip(res, cost)) if isinstance(res, list) else [(res, cost)]
            for _ in range(cnt):
                best_i=None; best_score=None
                for i in range(len(divisions)):
                    deficit=0.0
                    for r,_ in pairs:
                        ideal = avg_per_person.get(r,0)*divisions[i]
                        actual_load = self._combined_load_for_resource(i, r, used_actual, used_nominal)
                        deficit += max(0.0, ideal-actual_load)
                    box_count = sum(distribution[i].values()) if distribution[i] else 0
                    score = (deficit, -box_count)
                    if best_score is None or score>best_score:
                        best_score=score; best_i=i
                if best_i is None:
                    loads=[]
                    for i in range(len(divisions)):
                        combined_load = self._combined_load_total(i, used_actual, used_nominal)
                        per_person_load = (combined_load / divisions[i]) if divisions[i] else float('inf')
                        box_count = sum(distribution[i].values())
                        loads.append((per_person_load, box_count, i))
                    best_i = min(loads)[2]
                distribution[best_i][name]+=1
                for r,c in pairs:
                    used_nominal[best_i][r]+=c
                    if self._should_count_resource_cost(name, r):
                        used_actual[best_i][r]+=c

    # --------------------- balancing after distribution ---------------------
    # --------------------- formatting output ---------------------
    def _format_distribution_output(self, distribution, used, divisions, per_div_base=None):
        lines=[]; unit=self.unit_name_input.text(); storage=self.storage_name_input.text(); code=self.storage_pass_input.text()
        selected_index = self.weekday_combo.currentIndex(); target_date = self.next_weekday(selected_index)
        lines.append(f"@{unit}"); lines.append(""); lines.append(i18n.tr("logistics_plan_header", self.lang, date=target_date))
        lines.append(i18n.tr("main_storage_line", self.lang, storage=storage)); lines.append(i18n.tr("storage_password_line", self.lang, code=code)); lines.append("")
        for i in range(len(divisions)):
            lines.append(self.division_names[i].text() if i < len(self.division_names) else i18n.tr("division_label", self.lang, i=i+1))
            for name,cnt in sorted(distribution[i].items(), key=lambda x: self.resource_db[x[0]].get("group",999)):
                lines.append(f"    {cnt} – {i18n.tr_item(name, self.lang)}")
            # Базовые ресурсы за самолёты в обычной квоте (если есть)
            if per_div_base and i < len(per_div_base):
                base = per_div_base[i]
                if any(base.values()):
                    lines.append(i18n.tr("factory_resources_header", self.lang))
                    for key in ("coal", "scrap", "components", "sulfur", "rare_mats"):
                        v = base.get(key, 0)
                        if v > 0:
                            lines.append(f"      {i18n.tr_aviation_resource(key, self.lang)}: {v}")
            lines.append("")
        omto = self.omto_name_input.text().strip()
        n_omto = self.omto_count_spin.value() if hasattr(self, 'omto_count_spin') else 0

        if n_omto > 0:
            # Есть численность МТО — распределяем поимённо
            if omto:
                lines.append(f"=== {omto} ===")
            else:
                lines.append(i18n.tr("mto_section_marker", self.lang))
            lines.extend(self._build_mto_modifications_output())
            lines.extend(self._build_mto_equipment_output())
        else:
            # Численность не задана — старый вид без распределения
            # Модификации
            mods_text = self.mods_quota_input.toPlainText()
            if mods_text and mods_text.strip():
                if omto:
                    lines.append(i18n.tr("mods_section_header", self.lang, name=omto))
                else:
                    lines.append(i18n.tr("factory_mods_header", self.lang))
                for line in mods_text.splitlines():
                    if line is None:
                        continue
                    lines.append(f"  {line.rstrip()}")
                lines.append("")

            # Снаряжение
            eq_text = self.equipment_quota_input.toPlainText()
            if eq_text and eq_text.strip():
                if omto:
                    lines.append(i18n.tr("equipment_section_header", self.lang, name=omto))
                else:
                    lines.append(i18n.tr("factory_equipment_header", self.lang))
                for line in eq_text.splitlines():
                    if line is None:
                        continue
                    lines.append(f"  {line.rstrip()}")
                lines.append("")
        # Лётное отделение — реальное распределение через калькулятор
        lines.extend(self._build_aviation_output())
        lines.append(i18n.tr("resources_spent_header", self.lang))
        for i in range(len(divisions)):
            div_label = self.division_names[i].text() if i < len(self.division_names) and self.division_names[i].text().strip() else i18n.tr("division_label", self.lang, i=i+1)
            lines.append(f"{div_label}:")
            for r,v in used[i].items():
                lines.append(f"  {i18n.tr_resource(r, self.lang)}: {v}")
        return lines

    # --------------------- orchestration ---------------------
    def calculate_distribution(self):
        divisions = [spin.value() for spin in self.division_inputs]; total_people = sum(divisions)
        item_entries, undefined = self._collect_quota_entries()
        # Не выходим, если основная квота пуста, но есть содержимое в МТО/Лётке —
        # снаряжение/модификации/самолёты строятся ниже в _format_distribution_output.
        _has_factory_or_aviation = any([
            self.mods_quota_input.toPlainText().strip(),
            self.equipment_quota_input.toPlainText().strip(),
            self.aviation_quota_input.toPlainText().strip(),
        ])
        if not item_entries and not _has_factory_or_aviation:
            return self.output_area.setPlainText(i18n.tr("no_valid_entries_error", self.lang))

        step_map = {
            "per_4": 4,
            "per_9": 9,
            "per_person": 5,
            "per_person_one": 1
        }
        # Собираем авиа-предметы из обычной квоты отдельно — они дадут базовые
        # ресурсы для обычных подразделений (плашка "Ресурсы на завод").
        # parsed_quota_lines — список (count, name, settings, recipe) для авиа.
        self._aviation_in_main_quota = []
        for line in self.quota_input.toPlainText().splitlines():
            parsed = parse_aviation_quota_line(line)
            if parsed is None:
                continue
            count, name, settings = parsed
            entry = self.resource_db.get(name)
            if entry and entry.get('is_aviation'):
                self._aviation_in_main_quota.append((count, name, settings, entry.get('recipe', {})))

        normalized_entries = []
        for name, cnt in item_entries:
            entry = self.resource_db.get(name, {})
            # Авиа-предметы обрабатываются отдельно (см. self._aviation_in_main_quota)
            if entry.get('is_aviation'):
                continue
            dist = entry.get("distribution", "per_person")
            group = entry.get("group")
            
            # Для группы 8 не округляем здесь - это будет сделано в _distribute_delayed
            if group == 8:
                normalized_entries.append((name, cnt))
                continue
                
            step = step_map.get(dist)
            if dist == "per_4" and not getattr(self, "enforce_multiple_of_4", True):
                step = None
            if step and step > 1:
                cnt = int(math.ceil(cnt / step) * step)
            normalized_entries.append((name, cnt))
        item_entries = normalized_entries

        total_resources = self._calculate_totals(item_entries)
        avg_per_person = {r: total_resources[r] / total_people for r in total_resources} if total_people else {}
        distribution, used_actual, used_nominal = self._perform_distribution(item_entries, divisions, avg_per_person)
        
        totals_from_used = defaultdict(float)
        for i in used_actual:
            for r,v in used_actual[i].items(): totals_from_used[r] += v
        avg_from_used = {r: totals_from_used[r] / total_people for r in totals_from_used} if total_people else {}
        lines = self._format_totals_output(totals_from_used, avg_from_used)

        # === Базовые ресурсы за самолёты в обычной квоте ===
        per_div_base = [{"coal": 0, "scrap": 0, "components": 0,
                        "sulfur": 0, "rare_mats": 0}
                       for _ in range(len(divisions))]
        if self._aviation_in_main_quota and total_people > 0:
            total_base = {"coal": 0, "scrap": 0, "components": 0,
                          "sulfur": 0, "rare_mats": 0}
            for count, name, settings, recipe in self._aviation_in_main_quota:
                scrap_ratio = settings.get("scrap", AV_DEFAULT_SCRAP) / 100.0
                bc = _aviation_calc_base_cost(
                    recipe, count,
                    coke_recipe=settings.get("coke", AV_DEFAULT_COKE),
                    fuel_recipe=settings.get("fuel", AV_DEFAULT_FUEL),
                    scrap_ratio=scrap_ratio,
                )
                if bc is None:
                    continue
                total_base["coal"] += getattr(bc, "coal", 0)
                total_base["scrap"] += getattr(bc, "scrap", 0)
                total_base["components"] += getattr(bc, "components", 0)
                total_base["sulfur"] += bc.net_sulfur() if hasattr(bc, "net_sulfur") else getattr(bc, "sulfur", 0)
                total_base["rare_mats"] += getattr(bc, "rare_mats", 0)

            for resource, total in total_base.items():
                remaining = total
                shares = []
                for i in range(len(divisions)):
                    share = (total * divisions[i]) // total_people if total_people else 0
                    shares.append(share)
                    remaining -= share
                idx = 0
                while remaining > 0:
                    shares[idx] += 1
                    remaining -= 1
                    idx = (idx + 1) % len(divisions)
                for i in range(len(divisions)):
                    per_div_base[i][resource] = shares[i]
        # === конец блока ===

        lines += self._format_distribution_output(distribution, used_actual, divisions, per_div_base)
        annotated_undefined = []
        for raw in undefined:
            if self.is_special_aviation(raw):
                annotated_undefined.append(f"{raw}{i18n.tr('undefined_aviation_suffix', self.lang)}")
            elif self._is_omto_raw(raw):
                annotated_undefined.append(f"{raw}{i18n.tr('undefined_factory_suffix', self.lang)}")
            else:
                annotated_undefined.append(raw)

        self.output_area.setPlainText("\n".join(lines))

        self.undefined_area.setPlainText("\n".join(annotated_undefined))

        try:
            selections = []
            doc = self.undefined_area.document()
            block = doc.firstBlock()
            while block.isValid():
                text = block.text()
                if text:
                    cursor = QtGui.QTextCursor(doc)
                    cursor.setPosition(block.position())
                    cursor.select(QtGui.QTextCursor.BlockUnderCursor)

                    sel = QtWidgets.QTextEdit.ExtraSelection()
                    sel.cursor = cursor
                    fmt = QtGui.QTextCharFormat()

                    if text.endswith(i18n.tr('undefined_aviation_suffix', self.lang)):
                        fmt.setForeground(QtGui.QBrush(QtGui.QColor("#3ba0ff")))
                    elif text.endswith(i18n.tr('undefined_factory_suffix', self.lang)):
                        fmt.setForeground(QtGui.QBrush(QtGui.QColor("#ffe600")))
                    else:
                        fmt.setForeground(QtGui.QBrush(QtGui.QColor("#ff3b3b")))

                    sel.format = fmt
                    selections.append(sel)
                block = block.next()
            self.undefined_area.setExtraSelections(selections)
        except Exception as e:
            logger.warning(f"undefined_area highlight failed: {e}")

    @staticmethod
    def next_weekday(target_weekday):
        today = datetime.now(); days_ahead = target_weekday - today.weekday()
        if days_ahead <= 0: days_ahead += 7
        return (today + timedelta(days=days_ahead)).strftime("%d.%m.%Y")


# Allow running this module standalone for quick testing
if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    # Иконка приложения
    icon_path = resource_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QtGui.QIcon(icon_path))
    w = ResourceSplitter()
    # Иконка окна
    if os.path.exists(icon_path):
        w.setWindowIcon(QtGui.QIcon(icon_path))
    w.show()
    sys.exit(app.exec_())