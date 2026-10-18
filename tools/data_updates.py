"""
Изменения игры поверх данных старой версии (legacy/ при этом не меняется).

Применяются в двух местах, чтобы TS-версия и эталон считали по одним данным:
  * tools/export_data.py — при выгрузке в src/data/*.json;
  * tools/golden/gen_golden.py — в Python-версии на время прогона эталонов.
"""

# Трейлеры Rooster больше не делаются на заводе (МТО): теперь это ящики
# массовой фабрики — 300 бмат за ящик, по 5 ящиков в очереди (per_person),
# как у прочей техники (group 8).
NOT_FACTORY = ["Rooster - Lamploader", "Rooster - Tumblebox"]
_MPF_TRAILER = {"resource": ["Бмат"], "cost_per_box": [300], "distribution": "per_person", "group": 8}
NEW_RESOURCES = {
    "Rooster - Lamploader (Ящик)": _MPF_TRAILER,
    "Rooster - Tumblebox (Ящик)": _MPF_TRAILER,
}
NEW_RESOURCES_AFTER = "Rooster - Junkwagon (Ящик)"  # куда вставить в resources.json


def update_resources(db):
    """Новый dict ресурсов: NEW_RESOURCES встают сразу после NEW_RESOURCES_AFTER."""
    out = {}
    for name, entry in db.items():
        if name not in NEW_RESOURCES:
            out[name] = entry
        if name == NEW_RESOURCES_AFTER:
            out.update({k: dict(v) for k, v in NEW_RESOURCES.items()})
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
