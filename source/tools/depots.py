#!/usr/bin/env python3
"""
Склады по регионам для «Таймеров складов» -> src/data/depots.json.

Источник — официальный War API игры (https://github.com/clapfoot/warapi):
список регионов текущей войны, у каждого — сооружения с резервными складами
(iconType 33 Storage Depot, 52 Seaport, 88 Aircraft Depot) и подписи
городов. Склад называется по ближайшему крупному городу, как в игре.
Названия регионов — как на foxhole.wiki.gg (с апострофами, «The ...»).

Карта меняется от войны к войне — тогда скрипт нужно запустить заново:
  python tools/depots.py
"""
import json
import os
import re
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "src", "data", "depots.json")
API = "https://war-service-live.foxholeservices.com/api/worldconquest"
WIKI = "https://foxhole.wiki.gg/api.php"
UA = {"User-Agent": "logiplan-tools/1.0"}

# iconType War API -> ключ типа (подписи — src/core/i18nExtra.ts, wt_depot_*)
DEPOT_TYPES = {33: "storage", 52: "seaport", 88: "aircraft"}
# Имена, которые не получаются из кода региона разбиением по словам
NAME_OVERRIDES = {
    "MorgensCrossingHex": "Morgen's Crossing",
    "LinnMercyHex": "The Linn of Mercy",
    "FishermansRowHex": "Fisherman's Row",
    "CallahansPassageHex": "Callahan's Passage",
    "KingsCageHex": "King's Cage",
    "DeadLandsHex": "Deadlands",
    "AllodsBightHex": "Allod's Bight",
    "CallumsCapeHex": "Callum's Cape",
}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def region_names(hexes):
    """Код региона -> название (страница вики после редиректов)."""
    guess = {h: NAME_OVERRIDES.get(h) or re.sub(r"(?<=[a-z])(?=[A-Z])", " ", re.sub(r"Hex$", "", h)) for h in hexes}
    names = {}
    titles = list(guess.values())
    for i in range(0, len(titles), 40):
        q = get(WIKI + "?" + urllib.parse.urlencode(
            {"action": "query", "titles": "|".join(titles[i:i + 40]), "redirects": 1, "format": "json"}))["query"]
        alias = {r["from"]: r["to"] for r in q.get("normalized", []) + q.get("redirects", [])}
        missing = {p["title"] for p in q["pages"].values() if "missing" in p}
        for t in titles[i:i + 40]:
            while t in alias:
                t = alias[t]
            names[t] = t not in missing
    out = {}
    for h, t in guess.items():
        canon = t
        while canon in alias:
            canon = alias[canon]
        if not names.get(canon, True):
            raise SystemExit(f"нет страницы региона на вики: {h} -> {t}; добавьте в NAME_OVERRIDES")
        out[h] = canon
    return out


def main():
    hexes = get(f"{API}/maps")
    names = region_names(hexes)
    regions = []
    for h in hexes:
        static = get(f"{API}/maps/{h}/static")
        dynamic = get(f"{API}/maps/{h}/dynamic/public")
        towns = [t for t in static["mapTextItems"] if t["mapMarkerType"] == "Major"]
        depots = set()
        for it in dynamic["mapItems"]:
            kind = DEPOT_TYPES.get(it["iconType"])
            if not kind or not towns:
                continue
            town = min(towns, key=lambda t: (t["x"] - it["x"]) ** 2 + (t["y"] - it["y"]) ** 2)["text"]
            depots.add((kind, town))
        order = list(DEPOT_TYPES.values())
        regions.append({
            "region": names[h],
            "depots": [list(d) for d in sorted(depots, key=lambda d: (order.index(d[0]), d[1]))],
        })
    regions.sort(key=lambda r: re.sub(r"^The ", "", r["region"]))
    with open(OUT, "w", encoding="utf-8") as f:  # по региону на строку
        rows = ",\n  ".join(json.dumps(r, ensure_ascii=False) for r in regions)
        f.write(f'{{"regions": [\n  {rows}\n]}}\n')
    print(f"{OUT}: {len(regions)} регионов, {sum(len(r['depots']) for r in regions)} складов")


if __name__ == "__main__":
    main()
