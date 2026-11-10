# -*- coding: utf-8 -*-
"""For junctions whose cross street has no name match in OSM, look for bus stops and other named features
nearby (Athens bus stops are usually named after the cross street). Downloads a grid of small OSM extracts
around each junction, caches them in landmarks_raw.json, and prints candidates. Changes no positions."""
import json, math, os, re, time, urllib.request
import geocode as g

T = {  # aa: (name regex, grid half-size in cells)
    23: ("Φιξ|ΦΙΞ|FIX", 2), 47: ("ΜΑΚ|Αλεξ.νδρου|ΑΛΕΞΑΝΔΡΟΥ", 2), 49: ("Αναγενν|ΑΝΑΓΕΝΝ|μορφοκκ?λησι|ΜΟΡΦΟΚΚ?ΛΗΣΙ", 2),
    59: ("Αεροδρ|ΑΕΡΟΔΡ|Σπ.των|ΣΠΑΤΩΝ", 2), 67: ("Ηρακλ.ους|ΗΡΑΚΛΕΟΥΣ", 2), 68: ("Νυμφα|ΝΥΜΦΑ", 2),
    70: ("Μεγαρ.δ|ΜΕΓΑΡΙΔ", 2), 71: ("Τραπεζο|ΤΡΑΠΕΖΟ", 2), 93: ("Σαλαμ.ν|ΣΑΛΑΜΙΝ", 2),
}
CELL = 0.007
pos = json.load(open("positions.json", encoding="utf-8"))
cache = json.load(open("landmarks_raw.json", encoding="utf-8")) if os.path.exists("landmarks_raw.json") else {}


def named(lat0, lon0):
    key = f"{lat0:.4f},{lon0:.4f}"
    if key in cache: return cache[key]
    url = f"https://api.openstreetmap.org/api/0.6/map.json?bbox={lon0:.5f},{lat0:.5f},{lon0+CELL:.5f},{lat0+CELL:.5f}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "junction-geocoder/1.0"}), timeout=60) as r:
            d = json.loads(r.read().decode())
    except Exception as e:
        print("  fetch failed", key, e); return []
    nodes = {e["id"]: (e["lat"], e["lon"]) for e in d["elements"] if e["type"] == "node"}
    out = []
    for e in d["elements"]:
        t = e.get("tags") or {}
        n = t.get("name")
        if not n: continue
        if e["type"] == "node": p = (e["lat"], e["lon"])
        elif e["type"] == "way":
            ps = [nodes[i] for i in e["nodes"] if i in nodes]
            if not ps: continue
            p = (sum(x[0] for x in ps) / len(ps), sum(x[1] for x in ps) / len(ps))
        else: continue
        kind = t.get("highway") or t.get("public_transport") or t.get("amenity") or t.get("shop") or t.get("railway") or t.get("building") or t.get("landuse") or t.get("office") or "?"
        out.append([e["type"], kind, n, round(p[0], 6), round(p[1], 6)])
    cache[key] = out
    json.dump(cache, open("landmarks_raw.json", "w", encoding="utf-8"), ensure_ascii=False)
    time.sleep(0.35)
    return out


for aa, (rx, half) in T.items():
    p = pos[str(aa)]; c = (p["lat"], p["lon"]); R = re.compile(rx)
    seen, rows = set(), []
    for i in range(-half, half + 1):
        for j in range(-half, half + 1):
            lat0 = math.floor(c[0] / CELL) * CELL + i * CELL; lon0 = math.floor(c[1] / CELL) * CELL + j * CELL
            for typ, kind, n, lat, lon in named(lat0, lon0):
                if R.search(n) and (typ, n, lat, lon) not in seen:
                    seen.add((typ, n, lat, lon)); rows.append((round(g.dist((lat, lon), c)), typ, kind, n, lat, lon))
    print(f"\n== {aa}: {len(rows)} candidates", flush=True)
    for x in sorted(rows)[:16]: print("  ", x)
