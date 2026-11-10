# -*- coding: utf-8 -*-
"""Geocode junctions by finding where two named OSM streets meet (Overpass API).
Usage: python3 geocode.py [aa ...]   -> writes/updates geocoded.json next to this file
"""
import json, math, os, sys, time, urllib.parse, urllib.request
from junctions import ROWS, AREAS

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "geocoded.json")
ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://overpass.private.coffee/api/interpreter"]
RADIUS = 9000  # metres around the area hint


def dist(a, b):
    k = 111320.0
    dy = (a[0] - b[0]) * k
    dx = (a[1] - b[1]) * k * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def overpass(q):
    data = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for attempt in range(6):
        url = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "junction-geocoder/1.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # rate limit / timeout: back off and retry
            last = e
            time.sleep(4 + 4 * attempt)
    raise last


def query_pair(a, b, hint, radius=RADIUS):
    lat, lon = hint
    q = f"""[out:json][timeout:60];
way[highway][name~"{a}",i](around:{radius},{lat},{lon})->.a;
way[highway][name~"{b}",i](around:{radius},{lat},{lon})->.b;
.a out geom qt; .b out geom qt;"""
    res = overpass(q)
    import re
    ra, rb = re.compile(a, re.I), re.compile(b, re.I)
    A, B = [], []
    for el in res.get("elements", []):
        name = el.get("tags", {}).get("name", "")
        pts = [(p["lat"], p["lon"]) for p in el.get("geometry", [])]
        if ra.search(name):
            A.append((name, pts))
        if rb.search(name):
            B.append((name, pts))
    return A, B


def locate(A, B, hint):
    """Return (lat, lon, quality, nameA, nameB) or None."""
    shared = []
    idx = {}
    for name, pts in A:
        for p in pts:
            idx.setdefault(p, name)
    for name, pts in B:
        for p in pts:
            if p in idx and idx[p] != name:
                shared.append((p, idx[p], name))
    if shared:
        shared.sort(key=lambda s: dist(s[0], hint))
        best = shared[0]
        cluster = [s[0] for s in shared if dist(s[0], best[0]) < 90]
        lat = sum(p[0] for p in cluster) / len(cluster)
        lon = sum(p[1] for p in cluster) / len(cluster)
        return lat, lon, "exact", best[1], best[2]
    # no shared node (flyover / slip roads): closest approach of the two streets
    best = None
    for na, pa in A:
        for nb, pb in B:
            if na == nb:
                continue
            for p in pa:
                for q in pb:
                    if abs(p[0] - q[0]) > 0.002 or abs(p[1] - q[1]) > 0.002:
                        continue
                    d = dist(p, q)
                    if d < 120:
                        score = d + dist(p, hint) / 50.0
                        if best is None or score < best[0]:
                            best = (score, p, q, na, nb, d)
    if best:
        _, p, q, na, nb, d = best
        return (p[0] + q[0]) / 2, (p[1] + q[1]) / 2, "near", na, nb
    return None


def main():
    only = set(int(x) for x in sys.argv[1:])
    done = {}
    if os.path.exists(OUT):
        done = {int(k): v for k, v in json.load(open(OUT, encoding="utf-8")).items()}
    cache = {}
    for aa, node, loc, direction, cams, area, pairs in ROWS:
        if only and aa not in only:
            continue
        if not only and aa in done and done[aa]["quality"] != "approx":
            continue
        hint = AREAS[area]
        found = None
        for a, b in pairs:
            key = (a, b, area)
            if key not in cache:
                try:
                    cache[key] = query_pair(a, b, hint)
                except Exception as e:
                    print(f"  ! {aa} query failed: {e}", flush=True)
                    cache[key] = ([], [])
                time.sleep(1.2)
            A, B = cache[key]
            found = locate(A, B, hint)
            if found:
                break
        if found:
            lat, lon, quality, na, nb = found
        else:
            lat, lon, quality, na, nb = hint[0], hint[1], "approx", "", ""
        done[aa] = dict(aa=aa, node=node, location=loc, direction=direction, cameras=cams,
                        area=area, lat=round(lat, 6), lon=round(lon, 6), quality=quality,
                        matched=f"{na} × {nb}" if na else "",
                        hint_km=round(dist((lat, lon), hint) / 1000, 2))
        print(f"{aa:3d} {quality:6s} {lat:.5f},{lon:.5f} {done[aa]['hint_km']:5.2f}km  {loc}  [{na} × {nb}]", flush=True)
        json.dump({str(k): done[k] for k in sorted(done)}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
