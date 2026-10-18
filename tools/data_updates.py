"""
Изменения игры поверх данных старой версии (legacy/ при этом не меняется).

Применяются в двух местах, чтобы TS-версия и эталон считали по одним данным:
  * tools/export_data.py — при выгрузке в src/data/*.json;
  * tools/golden/gen_golden.py — в Python-версии на время прогона эталонов.
"""

# Трейлеры Rooster — ящики массовой фабрики: 300 бмат за ящик, по 5 ящиков
# в очереди (per_person), как у прочей техники (group 8). Lamploader и
# Tumblebox при этом больше не делаются на заводе (МТО); Junkwagon раньше
# стоил 30 рмат за ящик.
NOT_FACTORY = ["Rooster - Lamploader", "Rooster - Tumblebox"]
_MPF_TRAILER = {"resource": ["Бмат"], "cost_per_box": [300], "distribution": "per_person", "group": 8}
NEW_RESOURCES = {
    "Rooster - Junkwagon (Ящик)": _MPF_TRAILER,
    "Rooster - Lamploader (Ящик)": _MPF_TRAILER,
    "Rooster - Tumblebox (Ящик)": _MPF_TRAILER,
}
NEW_RESOURCES_AFTER = "Rooster - Junkwagon (Ящик)"  # куда вставить новые в resources.json

# Строки интерфейса, изменённые по сравнению со старой версией.
UI_OVERRIDES = {
    "aviation_recipe_btn": {"ru": "Настроить цены самолётов", "en": "Configure Aircraft Prices",
                            "fr": "Configurer le prix des avions"},  # было с «⚙ »
    "wt_header": {"ru": "Таймеры складов", "en": "Warehouse Timers", "fr": "Minuteries d'entrepôt"},  # было с «⏱️ »
    "wt_add_btn": {"ru": "Добавить склад", "en": "Add Warehouse", "fr": "Ajouter un entrepôt"},  # было с «➕ »
}


def update_resources(db):
    """Новый dict ресурсов: имеющиеся записи из NEW_RESOURCES заменяются на
    месте, новые встают сразу после NEW_RESOURCES_AFTER."""
    out = {}
    for name, entry in db.items():
        out[name] = dict(NEW_RESOURCES[name]) if name in NEW_RESOURCES else entry
        if name == NEW_RESOURCES_AFTER:
            for k, v in NEW_RESOURCES.items():
                if k not in db:
                    out[k] = dict(v)
    for k, v in NEW_RESOURCES.items():
        out.setdefault(k, dict(v))
    return out


def update_items(items_module):
    """Убирает трейлеры из модификаций и особых позиций завода (на месте)."""
    items_module.MTO_MODIFICATIONS[:] = [n for n in items_module.MTO_MODIFICATIONS if n not in NOT_FACTORY]
    for n in NOT_FACTORY:
        items_module.SPECIAL_OMTO.discard(n)


def factory_buttons_removed(quota_writer_module):
    """Ключи кнопок страницы «завод» (11) с позициями, которые больше не для завода."""
    return {k for k, v in quota_writer_module.ITEM_TEXT.items() if k.startswith("p11_") and v in NOT_FACTORY}


def update_quota_writer(quota_writer_module):
    """Убирает эти кнопки из ITEM_TEXT (на месте) — по ним старая версия
    строит список завода по умолчанию. Возвращает убранные ключи."""
    removed = factory_buttons_removed(quota_writer_module)
    for k in removed:
        del quota_writer_module.ITEM_TEXT[k]
    return removed
