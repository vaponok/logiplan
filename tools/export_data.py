#!/usr/bin/env python3
"""
Разовый (повторяемый) экспорт данных из Python-версии в JSON для веб-версии.

Источник — legacy/*.py (как есть, без правок). Результат:
  src/data/resources.json   — копия legacy/resources.json
  src/data/i18n.json        — ITEM_I18N, UI_STRINGS, RESOURCE_LABELS, ...
  src/data/items.json       — ITEM_NAMES, SPECIAL_OMTO, MTO_MODIFICATIONS, ...
  src/data/quotaPages.json  — страницы «Написания квоты»: кнопки, картинки, подписи
  public/images/*.webp      — только картинки, на которые реально ссылается UI
  src-tauri/icons/icon.png  — иконка приложения 256x256 (из legacy/icon.ico)

Запуск (нужны PyQt5 и Pillow):
  QT_QPA_PLATFORM=offscreen python tools/export_data.py --images /путь/к/source/images
"""
import argparse
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY = os.path.join(ROOT, "legacy")
sys.path.insert(0, LEGACY)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import i18n  # noqa: E402
import items  # noqa: E402
import quota_writer  # noqa: E402  (импорт тянет PyQt5, но окна не создаёт)

DATA = os.path.join(ROOT, "src", "data")
IMAGES_OUT = os.path.join(ROOT, "public", "images")


def dump(name, obj):
    path = os.path.join(DATA, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"  {name}: {os.path.getsize(path) // 1024} КБ")


def slug(filename):
    base = os.path.splitext(os.path.basename(filename))[0].lower()
    s = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return s or "img"


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
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True, help="папка images из старого архива")
    ap.add_argument("--quality", type=int, default=90)
    args = ap.parse_args()

    from PIL import Image

    os.makedirs(DATA, exist_ok=True)
    os.makedirs(IMAGES_OUT, exist_ok=True)
    print("JSON:")
    shutil.copyfile(os.path.join(LEGACY, "resources.json"), os.path.join(DATA, "resources.json"))
    print("  resources.json: скопирован")

    dump("i18n.json", {
        "langs": list(i18n.LANGS),
        "defaultLang": i18n.DEFAULT_LANG,
        "items": i18n.ITEM_I18N,
        "ui": i18n.UI_STRINGS,
        "resources": i18n.RESOURCE_LABELS,
        "aviationResources": i18n.AVIATION_RESOURCE_LABELS,
        "weekdays": i18n.WEEKDAYS,
    })

    omto_default = defaults_from_quota_writer(11) or [n for n in items.SPECIAL_OMTO if n]
    aviation_default = defaults_from_quota_writer(12) or [n for n in items.SPECIAL_AVIATION if n]
    dump("items.json", {
        "itemNames": items.ITEM_NAMES,
        "specialOmto": list(items.SPECIAL_OMTO),
        "mtoModifications": list(items.MTO_MODIFICATIONS),
        "specialAviation": list(items.SPECIAL_AVIATION),
        "omtoDefault": omto_default,
        "aviationDefault": aviation_default,
    })

    # --- картинки: только те, на которые ссылается «Написание квоты» ---
    converted = {}  # исходный относительный путь -> имя webp (или None, если файла нет)
    total_in = total_out = 0

    def convert(rel_path, size=None):
        nonlocal total_in, total_out
        if rel_path in converted:
            return converted[rel_path]
        src = os.path.join(args.images, os.path.basename(rel_path))
        if not os.path.exists(src):
            converted[rel_path] = None
            return None
        name = slug(rel_path) + ".webp"
        taken = set(v for v in converted.values() if v)
        n = 2
        while name in taken:
            name = f"{slug(rel_path)}-{n}.webp"
            n += 1
        img = Image.open(src).convert("RGBA")
        if size and (img.width > size or img.height > size):
            img.thumbnail((size, size), Image.LANCZOS)
        out = os.path.join(IMAGES_OUT, name)
        img.save(out, "WEBP", quality=args.quality, method=6)
        total_in += os.path.getsize(src)
        total_out += os.path.getsize(out)
        converted[rel_path] = name
        return name

    pages = []
    missing = []
    for p, count in enumerate(quota_writer.PAGE_BUTTON_COUNTS, start=1):
        buttons = []
        for idx in range(1, count + 1):
            key = f"p{p}_b{idx}"
            path = quota_writer.IMAGE_MAPPING.get(key, f"images/p{p}_b{idx}.png")
            img = convert(path, size=300)
            if img is None:
                missing.append(path)
            buttons.append({
                "key": key,
                "index": idx,
                "item": quota_writer.ITEM_TEXT.get(key) or None,
                "image": img,
                "imageBasename": os.path.basename(path),
            })
        pages.append({"page": p, "scroll": p in (8, 11), "white": p == 11, "buttons": buttons})

    # Иконки навигации — как PAGE_ICON_MAPPING в quota_writer.MainWindow
    nav_icons = {
        0: "images/1.png", 1: "images/2.png", 2: "images/3.png", 3: "images/4.png",
        4: "images/5.png", 5: "images/6.png", 6: "images/7.png", 7: "images/8.png",
        8: "images/9.png", 9: "images/10.png",
        10: "images/ScoutVehicleOffensiveW.png",
        11: "images/Luminary Mk. II Harbinger.png",
    }
    for i, page in enumerate(pages):
        page["navIcon"] = convert(nav_icons.get(i, f"images/page{i + 1}.png"), size=128)

    dump("quotaPages.json", {"pages": pages})

    print(f"Картинки: {len([v for v in converted.values() if v])} шт., "
          f"{total_in // 1024} КБ PNG -> {total_out // 1024} КБ WebP")
    if missing:
        print(f"  нет файла для {len(missing)} кнопок (будет заглушка B<n>): {missing[:5]}…")

    # --- иконка приложения для Tauri ---
    icons = os.path.join(ROOT, "src-tauri", "icons")
    os.makedirs(icons, exist_ok=True)
    ico = Image.open(os.path.join(LEGACY, "icon.ico"))
    ico = ico.convert("RGBA")
    ico.save(os.path.join(icons, "icon.png"))
    shutil.copyfile(os.path.join(LEGACY, "icon.ico"), os.path.join(icons, "icon.ico"))
    ico.resize((64, 64), Image.LANCZOS).save(os.path.join(ROOT, "public", "icon.png"))
    print("Иконки: src-tauri/icons/icon.png, icon.ico, public/icon.png")


if __name__ == "__main__":
    main()
