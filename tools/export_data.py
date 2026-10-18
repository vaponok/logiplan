#!/usr/bin/env python3
"""
Разовый (повторяемый) экспорт данных из Python-версии в JSON для веб-версии.

Источник — legacy/*.py (как есть, без правок) плюс изменения игры из
tools/data_updates.py. Результат:
  src/data/resources.json   — legacy/resources.json с изменениями игры
  src/data/i18n.json        — ITEM_I18N, UI_STRINGS, RESOURCE_LABELS, ...
  src/data/items.json       — MTO_MODIFICATIONS, списки завода и Лётки по умолчанию
  src/data/quotaPages.json  — страницы «Написания квоты»: кнопки и подписи
  src-tauri/icons/icon.png  — иконка приложения 256x256 (из legacy/icon.ico)

В JSON попадает только то, что читает программа: лишнее раздувало бы exe.
Картинки кнопок и вкладок (поля image / navIcon) ставит tools/quota_icons.py —
его нужно запустить после этого скрипта.

Запуск (нужны PyQt5 и Pillow):
  QT_QPA_PLATFORM=offscreen python tools/export_data.py
  python tools/quota_icons.py
"""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY = os.path.join(ROOT, "legacy")
sys.path.insert(0, LEGACY)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import data_updates  # noqa: E402
import i18n  # noqa: E402
import items  # noqa: E402
import quota_writer  # noqa: E402  (импорт тянет PyQt5, но окна не создаёт)

DATA = os.path.join(ROOT, "src", "data")

# Строки старой версии, которых в новой нет: трей, отдельные окна, ошибки
# загрузки файлов, всплывающие подсказки кнопок.
UNUSED_UI = {
    "tray_open", "tray_quit", "main_window_title", "wt_window_title",
    "err_quota_writer_missing", "err_quota_writer_create",
    "err_timer_missing", "err_timer_create", "db_load_error",
    "wt_refresh_tooltip", "calc_quota_tooltip", "aviation_recipe_tooltip",
}


def dump(name, obj, indent=1):
    path = os.path.join(DATA, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)
        f.write("\n")
    print(f"  {name}: {os.path.getsize(path) // 1024} КБ")


def item_translations():
    """ITEM_I18N без повторов: ru совпадает с ключом, fr часто совпадает с en —
    такие значения программа берёт сама (src/core/i18n.ts)."""
    out = {}
    for key, tr in i18n.ITEM_I18N.items():
        t = dict(tr)
        if t.get("ru") == key:
            del t["ru"]
        if "fr" in t and t["fr"] == t.get("en"):
            del t["fr"]
        out[key] = t
    return out


def defaults_from_quota_writer(page):
    """Копия ResourceSplitter._load_defaults_from_quota_writer."""
    prefix = f"p{page}_b"
    found = []
    for key, name in quota_writer.ITEM_TEXT.items():
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        if not rest.isdigit():
            continue
        if isinstance(name, str) and name.strip():
            found.append((int(rest), name.strip()))
    found.sort(key=lambda t: t[0])
    seen, out = set(), []
    for _i, n in found:
        if n.lower() in seen:
            continue
        seen.add(n.lower())
        out.append(n)
    return out


def main():
    from PIL import Image

    os.makedirs(DATA, exist_ok=True)
    data_updates.update_items(items)
    removed_buttons = data_updates.update_quota_writer(quota_writer)

    print("JSON:")
    with open(os.path.join(LEGACY, "resources.json"), encoding="utf-8") as f:
        resources = data_updates.update_resources(json.load(f))
    dump("resources.json", resources, indent=2)

    dump("i18n.json", {
        "langs": list(i18n.LANGS),
        "defaultLang": i18n.DEFAULT_LANG,
        "items": item_translations(),
        "ui": {k: data_updates.UI_OVERRIDES.get(k, v) for k, v in i18n.UI_STRINGS.items() if k not in UNUSED_UI},
        "resources": i18n.RESOURCE_LABELS,
        "aviationResources": i18n.AVIATION_RESOURCE_LABELS,
        "weekdays": i18n.WEEKDAYS,
    })

    omto_default = defaults_from_quota_writer(11) or sorted(n for n in items.SPECIAL_OMTO if n)
    aviation_default = defaults_from_quota_writer(12) or [n for n in items.SPECIAL_AVIATION if n]
    dump("items.json", {
        "mtoModifications": list(items.MTO_MODIFICATIONS),
        "omtoDefault": omto_default,
        "aviationDefault": aviation_default,
        # убрать из сохранённых списков завода пользователя (src/lib/state.svelte.ts)
        "notFactory": list(data_updates.NOT_FACTORY),
    })

    # Страницы «Написания квоты»; картинки ставит tools/quota_icons.py
    old_pages = {}
    pages_path = os.path.join(DATA, "quotaPages.json")
    if os.path.exists(pages_path):
        for p in json.load(open(pages_path, encoding="utf-8"))["pages"]:
            old_pages[p["page"]] = p
    pages = []
    for p, count in enumerate(quota_writer.PAGE_BUTTON_COUNTS, start=1):
        old_images = {b["key"]: b.get("image") for b in old_pages.get(p, {}).get("buttons", [])}
        buttons = []
        for idx in range(1, count + 1):
            key = f"p{p}_b{idx}"
            if key in removed_buttons:
                continue
            buttons.append({
                "key": key,
                "index": idx,
                "item": quota_writer.ITEM_TEXT.get(key) or None,
                "image": old_images.get(key),
            })
        pages.append({"page": p, "white": p == 11, "buttons": buttons,
                      "navIcon": old_pages.get(p, {}).get("navIcon")})
    dump("quotaPages.json", {"pages": pages})

    # --- иконка приложения для Tauri ---
    icons = os.path.join(ROOT, "src-tauri", "icons")
    os.makedirs(icons, exist_ok=True)
    ico = Image.open(os.path.join(LEGACY, "icon.ico")).convert("RGBA")
    ico.save(os.path.join(icons, "icon.png"))
    shutil.copyfile(os.path.join(LEGACY, "icon.ico"), os.path.join(icons, "icon.ico"))
    ico.resize((64, 64), Image.LANCZOS).save(os.path.join(ROOT, "public", "icon.png"))
    print("Иконки: src-tauri/icons/icon.png, icon.ico, public/icon.png")


if __name__ == "__main__":
    main()
