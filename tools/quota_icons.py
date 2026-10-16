#!/usr/bin/env python3
"""
Картинки кнопок «Написания квоты» — единый набор 256x256.

Источник — оригинальные иконки игры с официальной вики (foxhole.wiki.gg).
Часть из них в игре 100x100 или 128x128; такие увеличиваются нейросетью
Real-ESRGAN (x4plus) и уменьшаются до 256x256, остальные берутся как есть.

Какой файл вики у какой кнопки — tools/quota_icons.json (ключ кнопки ->
имя файла). Его можно пересобрать по английским названиям предметов:
    python tools/quota_icons.py --resolve
(существующие строки не трогаются, новые/пропавшие кнопки дописываются).

Сборка картинок (нужны torch, spandrel, Pillow, numpy; модель скачивается
сама в tools/.cache):
    python tools/quota_icons.py
Результат: public/images/items/*.webp, public/images/nav/*.webp (иконки
вкладок) и поля image / navIcon в src/data/quotaPages.json.
"""
import argparse
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_FILE = os.path.join(ROOT, "tools", "quota_icons.json")
PAGES_FILE = os.path.join(ROOT, "src", "data", "quotaPages.json")
I18N_FILE = os.path.join(ROOT, "src", "data", "i18n.json")
OUT_DIR = os.path.join(ROOT, "public", "images", "items")
CACHE = os.path.join(ROOT, "tools", ".cache")
API = "https://foxhole.wiki.gg/api.php"
UA = {"User-Agent": "logiplan-quota-icons/1.0"}
TARGET = 256

MODEL_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
MODEL_SHA256 = "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"

# Названия, которые на вики записаны иначе (кавычки, другая страница).
PAGE_OVERRIDES = {
    '250mm "Fury" Shell': "250mm “Fury” Shell",
    '250mm "Purity" Shell': "250mm “Purity” Shell",
    "Abisme AT-99 Mine": "Abisme AT-99",
    "Barbed Wire": "Barbed Wire (Material)",
    "No.1 “The Liar” Submachinegun": "No.1 “The Liar” Submachine Gun",
}
# Предметы без своей страницы (вики перенаправляет на соседний предмет).
FILE_OVERRIDES = {
    "Gas Mask Filter": "GasMaskFilterIcon.png",
    "Havoc Charge Detonator": "SatchelChargeTIcon.png",
}
# Нейросеть превращает решётку поддона в полосы — тут обычное увеличение.
PLAIN_RESIZE = {"MaterialPlatformItemIcon.png"}
# Иконки вкладок 1-9 — значки категорий игры (128x128: на кнопке 64 px,
# двойной запас); 10-12 — картинка одной из кнопок вкладки.
NAV_ICONS = {
    1: "IconFilterSmallWeapons.png",
    2: "IconFilterHeavyWeapons.png",
    3: "IconFilterHeavyAmmunition.png",
    4: "IconFilterUtility.png",
    5: "IconFilterResource.png",
    6: "IconFilterMedical.png",
    7: "IconFilterUniforms.png",
    8: "IconFilterVehicle.png",
    9: "IconFilterShippables.png",
}
NAV_FROM_BUTTON = {10: "p10_b1", 11: "p11_b36", 12: "p12_b2"}
NAV_DIR = os.path.join(ROOT, "public", "images", "nav")


def fetch(url, retries=4):
    for i in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)


def api(**kw):
    kw.update(format="json", formatversion="2")
    return json.loads(fetch(API + "?" + urllib.parse.urlencode(kw)))


def base_name(en):
    return re.sub(r"\s*\(Crate\)\s*$", "", en or "").strip()


def load_buttons():
    pages = json.load(open(PAGES_FILE, encoding="utf-8"))
    items = json.load(open(I18N_FILE, encoding="utf-8"))["items"]
    for p in pages["pages"]:
        for b in p["buttons"]:
            en = items.get(b["item"], {}).get("en") if b["item"] else None
            yield b, en


def infobox_image(title):
    d = api(action="query", titles=title, redirects=1, prop="revisions", rvprop="content", rvslots="main")
    p = d["query"]["pages"][0]
    if p.get("missing"):
        return None
    text = p["revisions"][0]["slots"]["main"]["content"]
    m = re.search(r"^\|\s*image\s*=\s*(.+?)\s*$", text, re.M)
    return m.group(1) if m else None


def resolve():
    mapping = json.load(open(MAP_FILE, encoding="utf-8")) if os.path.exists(MAP_FILE) else {}
    for b, en in load_buttons():
        if b["key"] in mapping:
            continue
        name = base_name(en)
        f = FILE_OVERRIDES.get(name)
        if not f and name:
            title = PAGE_OVERRIDES.get(name) or name
            f = infobox_image(title) or infobox_image(title.replace("’", "'"))
        print(f"  {b['key']}: {name} -> {f}")
        mapping[b["key"]] = f
    keys = sorted(mapping, key=lambda k: tuple(int(x) for x in re.findall(r"\d+", k)))
    with open(MAP_FILE, "w", encoding="utf-8") as fh:
        json.dump({k: mapping[k] for k in keys}, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    missing = [k for k in keys if not mapping[k]]
    print(f"{len(keys)} кнопок, без картинки: {missing or 'нет'}")


def download(files):
    os.makedirs(os.path.join(CACHE, "wiki"), exist_ok=True)
    for i in range(0, len(files), 40):
        chunk = files[i:i + 40]
        d = api(action="query", titles="|".join("File:" + f for f in chunk), prop="imageinfo", iiprop="url")
        norm = {n["to"]: n["from"] for n in d["query"].get("normalized", [])}
        for p in d["query"]["pages"]:
            name = norm.get(p["title"], p["title"])[len("File:"):]
            if not p.get("imageinfo"):
                raise SystemExit(f"нет файла на вики: {name}")
            path = os.path.join(CACHE, "wiki", name)
            if not os.path.exists(path):
                open(path, "wb").write(fetch(p["imageinfo"][0]["url"]))


def load_model():
    import torch
    from spandrel import ModelLoader
    path = os.path.join(CACHE, os.path.basename(MODEL_URL))
    if not os.path.exists(path):
        os.makedirs(CACHE, exist_ok=True)
        data = fetch(MODEL_URL)
        if hashlib.sha256(data).hexdigest() != MODEL_SHA256:
            raise SystemExit("модель Real-ESRGAN: не совпала контрольная сумма")
        open(path, "wb").write(data)
    torch.set_num_threads(os.cpu_count() or 1)
    return ModelLoader().load_from_file(path).eval()


def to_256(img, model, plain=False):
    """RGBA любого размера -> 256x256; меньшие — через Real-ESRGAN x4."""
    import numpy as np
    import torch
    from PIL import Image, ImageFilter

    if img.size == (TARGET, TARGET):
        return img
    if min(img.size) > TARGET:
        return img.resize((TARGET, TARGET), Image.LANCZOS)
    if plain:
        big = img.resize((TARGET, TARGET), Image.BICUBIC)
        return big.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))

    def sr(rgb):
        t = torch.from_numpy(np.ascontiguousarray(rgb)).permute(2, 0, 1)[None]
        with torch.no_grad():
            y = model(t)
        return y[0].permute(1, 2, 0).clamp(0, 1).numpy()

    x = np.asarray(img).astype(np.float32) / 255
    rgb, a = x[..., :3].copy(), x[..., 3]
    # у прозрачных пикселей цвет чёрный — «растягиваем» цвет соседей,
    # иначе по краям после увеличения появится тёмная кайма
    known = a > 0
    for _ in range(12):
        if known.all():
            break
        acc = np.zeros_like(rgb)
        cnt = np.zeros(a.shape, np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            k = np.roll(known, (dy, dx), (0, 1))
            acc += np.roll(rgb, (dy, dx), (0, 1)) * k[..., None]
            cnt += k
        new = ~known & (cnt > 0)
        rgb[new] = acc[new] / cnt[new][:, None]
        known |= new
    up = np.dstack([sr(rgb), sr(np.repeat(a[..., None], 3, 2)).mean(2)])
    big = Image.fromarray((up * 255 + 0.5).astype(np.uint8), "RGBA")
    return big.resize((TARGET, TARGET), Image.LANCZOS)


def slug(filename):
    s = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(filename)[0].lower()).strip("-")
    return s or "img"


def build(quality, alpha_quality):
    from PIL import Image

    mapping = json.load(open(MAP_FILE, encoding="utf-8"))
    files = sorted({f for f in mapping.values() if f})
    print(f"Вики: {len(files)} файлов")
    download(files + sorted(NAV_ICONS.values()))
    model = None
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(CACHE, "256"), exist_ok=True)
    names = {}
    for f in files:
        # увеличенная копия кэшируется: пересжатие не гоняет нейросеть заново
        cached = os.path.join(CACHE, "256", f)
        if os.path.exists(cached):
            img = Image.open(cached)
        else:
            if model is None:
                model = load_model()
            img = Image.open(os.path.join(CACHE, "wiki", f)).convert("RGBA")
            img = to_256(img, model, plain=f in PLAIN_RESIZE)
            img.save(cached)
        name = slug(f) + ".webp"
        # прозрачность с потерями (alpha_quality < 100) на глаз не отличить,
        # а набор выходит вдвое легче
        img.save(os.path.join(OUT_DIR, name), "WEBP", quality=quality,
                 alpha_quality=alpha_quality, method=6)
        names[f] = name
    for old in os.listdir(OUT_DIR):
        if old not in names.values():
            os.remove(os.path.join(OUT_DIR, old))

    os.makedirs(NAV_DIR, exist_ok=True)
    nav_names = {}
    for page, f in NAV_ICONS.items():
        name = slug(f) + ".webp"
        img = Image.open(os.path.join(CACHE, "wiki", f)).convert("RGBA")
        img.save(os.path.join(NAV_DIR, name), "WEBP", quality=quality, method=6)
        nav_names[page] = "nav/" + name
    for old in os.listdir(NAV_DIR):
        if "nav/" + old not in nav_names.values():
            os.remove(os.path.join(NAV_DIR, old))

    pages = json.load(open(PAGES_FILE, encoding="utf-8"))
    for p in pages["pages"]:
        if p["page"] in nav_names:
            p["navIcon"] = nav_names[p["page"]]
        for b in p["buttons"]:
            f = mapping.get(b["key"])
            if f:
                b["image"] = "items/" + names[f]
        # иконка вкладки, взятая с одной из кнопок, — из того же набора
        f = mapping.get(NAV_FROM_BUTTON.get(p["page"], ""))
        if f:
            p["navIcon"] = "items/" + names[f]
    with open(PAGES_FILE, "w", encoding="utf-8") as fh:
        json.dump(pages, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    size = sum(os.path.getsize(os.path.join(OUT_DIR, n)) for n in names.values())
    print(f"Готово: {len(names)} картинок 256x256, {size // 1024} КБ WebP")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resolve", action="store_true", help="дописать tools/quota_icons.json по вики")
    ap.add_argument("--quality", type=int, default=85)
    ap.add_argument("--alpha-quality", type=int, default=70)
    args = ap.parse_args()
    if args.resolve:
        resolve()
    else:
        build(args.quality, args.alpha_quality)


if __name__ == "__main__":
    main()
