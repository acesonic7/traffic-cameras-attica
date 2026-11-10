# -*- coding: utf-8 -*-
"""Derive every junction position from OpenStreetMap geometry.
For each row: take the OSM extract around the junction, find where the named streets meet, and use that OSM
point. Where the streets cannot be matched, snap to the nearest OSM node on one of the named streets and mark
the row approximate. Writes positions.json (the only position file the map is built from)."""
import json, math, os, re, sys, time, urllib.request
import geocode as g
from junctions import ROWS

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(HERE, "osm_local.json")
ROAD = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street"}


def fetch(lat, lon):
    dy, dx = 0.0027, 0.0027 / math.cos(math.radians(lat))
    url = f"https://api.openstreetmap.org/api/0.6/map.json?bbox={lon-dx:.6f},{lat-dy:.6f},{lon+dx:.6f},{lat+dy:.6f}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "junction-geocoder/1.0"}), timeout=40) as r:
        d = json.loads(r.read().decode())
    nodes = {e["id"]: e for e in d["elements"] if e["type"] == "node"}
    sig = [dict(id=n["id"], lat=n["lat"], lon=n["lon"], dir=n.get("tags", {}).get("traffic_signals:direction", ""))
           for n in nodes.values() if n.get("tags", {}).get("highway") == "traffic_signals"]
    ways = []
    for e in d["elements"]:
        t = e.get("tags", {})
        if e["type"] == "way" and t.get("highway", "").replace("_link", "") in ROAD:
            ways.append(dict(id=e["id"], hw=t["highway"], name=t.get("name", ""), oneway=t.get("oneway", ""),
                             lanes=t.get("lanes", ""), junction=t.get("junction", ""),
                             nodes=[[n, nodes[n]["lat"], nodes[n]["lon"]] for n in e["nodes"] if n in nodes]))
    time.sleep(0.4)
    return dict(signals=sig, ways=ways)


def locate(L, pairs, hint):
    """-> (lat, lon, quality) from OSM geometry only."""
    named = lambda rx: [(w["name"], [(n[1], n[2]) for n in w["nodes"]]) for w in L["ways"] if rx.search(w["name"])]
    for a, b in pairs:
        res = g.locate(named(re.compile(a, re.I)), named(re.compile(b, re.I)), hint)
        if res and g.dist((res[0], res[1]), hint) < 320:
            return round(res[0], 6), round(res[1], 6), "exact"
    for a, b in pairs:                       # no crossing found: nearest node on one of the named streets
        for rx in (re.compile(a, re.I), re.compile(b, re.I)):
            pts = [p for _, ps in named(rx) for p in ps]
            if pts:
                p = min(pts, key=lambda p: g.dist(p, hint))
                return round(p[0], 6), round(p[1], 6), "approx"
    pts = [(n[1], n[2]) for w in L["ways"] for n in w["nodes"]]
    p = min(pts, key=lambda p: g.dist(p, hint))
    return round(p[0], 6), round(p[1], 6), "approx"
