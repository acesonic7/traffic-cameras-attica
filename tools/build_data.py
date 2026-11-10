# -*- coding: utf-8 -*-
"""junctions.py (source table) + positions.json (OSM-derived positions) -> ../data.js and ../cameras.csv
Rows that share a node number are merged into one map point."""
import csv, json, os
import cameras as cm
from junctions import ROWS

HERE = os.path.dirname(os.path.abspath(__file__))
pos = json.load(open(os.path.join(HERE, "positions.json"), encoding="utf-8"))
local = json.load(open(os.path.join(HERE, "osm_local.json"), encoding="utf-8"))

rows = []
for aa, node, location, direction, cams, _area, _pairs in ROWS:
    p = pos[str(aa)]
    rows.append(dict(aa=aa, node=node, location=location, direction=direction, cameras=cams,
                     area=p["area"], lat=p["lat"], lon=p["lon"], quality=p["quality"]))

out, by_node = [], {}
for r in rows:
    j = by_node.get(r["node"])
    if j is None:
        j = dict(id=len(out) + 1, node=r["node"], location=r["location"], area=r["area"], lat=r["lat"], lon=r["lon"],
                 approx=r["quality"] == "approx", aa=[], flows=[], cameras=0)
        by_node[r["node"]] = j
        out.append(j)
    j["aa"].append(r["aa"])
    j["flows"].append(dict(direction=r["direction"], cameras=r["cameras"]))
    j["cameras"] += r["cameras"]

# individual cameras, estimated from OSM traffic signals / road arms around each junction
for j in out:
    d = " ".join(f["direction"] for f in j["flows"])
    j["coverage"] = "all" if "Όλες" in d else "both" if ("δύο" in d or " και " in d or len(j["flows"]) > 1) else "one"
    key = f"{j['lat']},{j['lon']}"
    j["cams"] = [] if j["approx"] or key not in local else cm.place((j["lat"], j["lon"]), local[key], j["cameras"], d, j["location"], j["coverage"])
print(sum(bool(j["cams"]) for j in out), "junctions with camera estimates,", sum(len(j["cams"]) for j in out), "cameras placed")

# Ministry of Digital Governance pilot "AI cameras": eight locations as reported in the press (no official list
# published); positions from OSM street crossings (ai_positions.json)
AI_AREAS = [
    ("Πανεπιστημίου – Λ. Βασ. Σοφίας", "Αθήνα"),
    ("Λ. Μεσογείων – Χαλανδρίου", "Αγία Παρασκευή"),
    ("Λ. Μαραθώνος – Αλ. Φλέμινγκ", "Ραφήνα"),
    ("Λ. Συγγρού – Αγίας Φωτεινής", "Καλλιθέα / Νέα Σμύρνη"),
    ("Λ. Ποσειδώνος – Ερμού", "Βουλιαγμένη"),
    ("Λ. Ποσειδώνος – Αλίμου", "Άλιμος"),
    ("Λ. Βουλιαγμένης – Τήνου", "Αργυρούπολη"),
    ("Λ. Κηφισίας – Εθν. Αντιστάσεως", "Νέο Ψυχικό"),
]
ai_pos = json.load(open(os.path.join(HERE, "ai_positions.json"), encoding="utf-8"))
ai = [dict(id=9000 + i, location=n, area=a, lat=ai_pos[n][0], lon=ai_pos[n][1], approx=ai_pos[n][2] == "approx")
      for i, (n, a) in enumerate(AI_AREAS, 1)]

with open(os.path.join(HERE, "..", "data.js"), "w", encoding="utf-8") as f:
    f.write("// Positions and camera estimates derived from OpenStreetMap data, (c) OpenStreetMap contributors, ODbL 1.0\n")
    f.write("const JUNCTIONS = " + json.dumps(out, ensure_ascii=False, indent=1) + ";\n")
    f.write("const AI_SITES = " + json.dumps(ai, ensure_ascii=False, indent=1) + ";\n")
with open(os.path.join(HERE, "..", "cameras.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["system", "aa", "node", "location", "direction", "cameras", "area", "lat", "lon", "position"])
    for r in rows:
        w.writerow(["red-light", r["aa"], r["node"], r["location"], r["direction"], r["cameras"], r["area"], r["lat"], r["lon"],
                    "approximate" if r["quality"] == "approx" else "junction"])
    for a in ai:
        w.writerow(["ai", "", "", a["location"], "", "", a["area"], a["lat"], a["lon"], "approximate" if a["approx"] else "junction"])
print(len(out), "points,", sum(j["cameras"] for j in out), "cameras,", sum(j["approx"] for j in out), "approximate")
