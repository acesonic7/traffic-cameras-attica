# -*- coding: utf-8 -*-
"""Estimate individual camera positions at a junction from OSM traffic signals and road geometry.
A camera is placed at each signalised approach (the stop line), looking along the direction of travel
into the junction. These are estimates, not surveyed positions."""
import math, unicodedata

RANK = {"motorway": 0, "trunk": 0, "primary": 0, "secondary": 1, "tertiary": 2}
K = 111320.0


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().replace("ς", "σ")


def xy(p, c):
    return ((p[1] - c[1]) * K * math.cos(math.radians(c[0])), (p[0] - c[0]) * K)


def ll(v, c):
    return (c[0] + v[1] / K, c[1] + v[0] / (K * math.cos(math.radians(c[0]))))


def bearing(v):
    return (math.degrees(math.atan2(v[0], v[1])) + 360) % 360


def adiff(a, b):
    return abs((a - b + 180) % 360 - 180)


def approaches(c, local, radius=100):
    """c=(lat,lon); local={'signals':[], 'ways':[]} -> list of approach dicts (metric coords relative to c)."""
    ways = []
    for w in local["ways"]:
        pts = [(n[0], xy((n[1], n[2]), c)) for n in w["nodes"]]
        if len(pts) > 1:
            ways.append((w, pts))
    out = []

    def add(pos, vec, w, src):
        L = math.hypot(*vec)
        if L < 0.5:
            return
        h = bearing(vec)
        rank = RANK.get(w["hw"].replace("_link", ""), 3) + (0.5 if w["hw"].endswith("_link") else 0)
        for o in out:  # same approach already found
            if math.hypot(o["pos"][0] - pos[0], o["pos"][1] - pos[1]) < 12 and adiff(o["hdg"], h) < 35:
                if rank < o["rank"]:
                    o.update(rank=rank, name=w["name"] or o["name"])
                return
        try:
            lanes = int(w["lanes"])
        except ValueError:
            lanes = 0
        out.append(dict(pos=pos, hdg=h, name=w["name"], rank=rank, lanes=lanes, src=src))

    def travel_dirs(w):
        ow = w["oneway"]
        if ow in ("yes", "true", "1") or w["junction"] == "roundabout" or w["hw"].startswith("motorway"):
            return [1]
        if ow in ("-1", "reverse"):
            return [-1]
        return [1, -1]

    # 1) signals mapped on an approach: camera at the signal, looking the way traffic moves
    centre_signal = False
    for s in local["signals"]:
        sp = xy((s["lat"], s["lon"]), c)
        d = math.hypot(*sp)
        if d > radius:
            continue
        if d < 12:
            centre_signal = True
            continue
        for w, pts in ways:
            for i, (nid, p) in enumerate(pts):
                if nid != s["id"]:
                    continue
                dirs = travel_dirs(w)
                if s["dir"] == "forward" and 1 in dirs: dirs = [1]
                if s["dir"] == "backward" and -1 in dirs: dirs = [-1]
                for dr in dirs:
                    j = i + dr
                    if 0 <= j < len(pts):
                        vec = (pts[j][1][0] - p[0], pts[j][1][1] - p[1])
                    elif 0 <= i - dr < len(pts):
                        q = pts[i - dr][1]
                        vec = (p[0] - q[0], p[1] - q[1])
                    else:
                        continue
                    if vec[0] * -sp[0] + vec[1] * -sp[1] > 0:  # heading into the junction
                        add(sp, vec, w, "signal")
    signal_apps = _nearest_per_direction(out)
    # 2) inbound road arms: fill in approaches that have no signal mapped (25 m before the junction)
    arms = []
    out = arms_out = []

    def add_arm(pos, vec, w):
        L = math.hypot(*vec)
        if L < 0.5:
            return
        rank = RANK.get(w["hw"].replace("_link", ""), 3) + (0.5 if w["hw"].endswith("_link") else 0)
        try:
            lanes = int(w["lanes"])
        except ValueError:
            lanes = 0
        arms.append(dict(pos=pos, hdg=bearing(vec), name=w["name"], rank=rank, lanes=lanes,
                         src="signal" if centre_signal else "road"))

    for w, pts in ways:
        i = min(range(len(pts)), key=lambda k: math.hypot(*pts[k][1]))
        p = pts[i][1]
        if math.hypot(*p) > 48:
            continue
        for dr in travel_dirs(w):
            acc, k, prev = 0.0, i, p   # walk upstream (against travel) from the node nearest the centre
            while 0 <= k - dr < len(pts) and acc < 25:
                k -= dr
                q = pts[k][1]
                seg = math.hypot(q[0] - prev[0], q[1] - prev[1])
                if acc + seg >= 25 and seg > 0:
                    f = (25 - acc) / seg
                    q = (prev[0] + (q[0] - prev[0]) * f, prev[1] + (q[1] - prev[1]) * f)
                    acc = 25
                else:
                    acc += seg
                prev = q
            # a real inbound arm starts farther from the centre than where it arrives
            if acc >= 15 and math.hypot(*prev) > math.hypot(*p) + 8:
                add_arm(prev, (p[0] - prev[0], p[1] - prev[1]), w)
    arms = _nearest_per_direction(arms)
    res = list(signal_apps)
    for a in arms:
        if not any(adiff(a["hdg"], o["hdg"]) < 40 and _lateral(a, o) < 14 for o in res):
            res.append(a)
    return res


def _lateral(a, o):
    """Sideways distance between two approaches, measured across a's direction of travel."""
    h = math.radians(a["hdg"])
    dx, dy = o["pos"][0] - a["pos"][0], o["pos"][1] - a["pos"][1]
    return abs(dx * math.cos(h) - dy * math.sin(h))


def _nearest_per_direction(apps):
    """Along one carriageway keep only the approach nearest the centre (drops the next junction's signals)."""
    keep = []
    for a in sorted(apps, key=lambda a: (math.hypot(*a["pos"]), a["rank"])):
        if not any(adiff(a["hdg"], o["hdg"]) < 35 and _lateral(a, o) < 12 for o in keep):
            keep.append(a)
    return keep


# roads the table and OpenStreetMap call by different names
ALIAS = [("θησεωσ", "βενιζελου"), ("νατο", "ειρηνησ"), ("πατησιων", "οκτωβριου"), ("ομορφοκκλησιασ", "βεικου"),
         ("ομορφοκκλησιασ", "ομορφοκλησιασ"), ("τατοιου", "δεκελειασ"), ("ηρ. πολυτεχνειου", "ηρωων πολυτεχνειου")]


def _alias(text):
    for a, b in ALIAS:
        if a in text and b not in text: text += " " + b
        elif b in text and a not in text: text += " " + a
    return text


STOP = {"λεωφορος", "λεωφ", "οδος", "αγιου", "αγιας", "αγιων", "πλατεια"}


def _tokens(name):
    return [t[:6] for t in norm(name).replace(".", " ").replace("-", " ").split() if len(t) >= 4 and t not in STOP]


def _split_direction(text):
    """-> (text naming the road the cameras are ON, text naming where traffic is heading TO)"""
    words = norm(text).replace(",", " ").split()
    on, to, i = [], [], 0
    while i < len(words):
        if words[i] == "προσ":
            to += words[i + 1:i + 4]
            i += 4
        else:
            on.append(words[i])
            i += 1
    return " ".join(on), " ".join(to)


def place(c, local, n, direction="", location="", coverage="all"):
    """Return n camera dicts {lat, lon, hdg, road, src} or [] when nothing usable is mapped.
    Cameras are spread over the approaches the table's wording points to, at most 2-3 per approach."""
    apps = approaches(c, local)
    if not apps:
        return []
    on, to = _split_direction(direction)
    on, to = _alias(on), _alias(to)
    loc = _alias(norm(location))
    first = _alias(norm(location.split("–")[0]))
    for a in apps:
        toks = _tokens(a["name"])
        hit = lambda text: any(t in text for t in toks)
        if hit(on):
            a["tier"] = 0                       # the table says the cameras are on this road
        elif hit(to) and coverage == "one":
            a["tier"] = 4                       # this road is where traffic is heading, not where the camera stands
        elif hit(first):
            a["tier"] = 1
        elif hit(loc):
            a["tier"] = 2
        else:
            a["tier"] = 3 if a["rank"] < 3 else 5  # unnamed main road / side street
    named = [a for a in apps if a["tier"] == 0]
    junction = [a for a in apps if a["tier"] <= 2]
    if coverage != "all" and named:
        pool = named
    elif coverage == "all":
        pool = [a for a in apps if a["tier"] <= 3]   # every main-road arm of the junction
    elif junction:
        pool = junction
    else:
        pool = [a for a in apps if a["tier"] <= 4] or apps
    pool.sort(key=lambda a: (a["tier"], a["rank"], -a["lanes"], math.hypot(*a["pos"])))
    if not pool:
        pool = sorted(apps, key=lambda a: (a["tier"], a["rank"]))
    if coverage == "one" and n <= 2:
        pool = pool[:1]
    cap = lambda a: 3 if a["lanes"] >= 4 else 2
    # too many cameras for these approaches: bring in the junction's other main-road arms before doubling up
    spare = sorted((a for a in apps if a not in pool and a["tier"] <= 3), key=lambda a: (a["tier"], a["rank"]))
    while spare and sum(cap(a) for a in pool) < n and not (coverage == "one" and n <= 2):
        pool.append(spare.pop(0))
    counts = [0] * len(pool)
    left = n
    while left:
        progressed = False
        for i, a in enumerate(pool):
            if left and counts[i] < cap(a):
                counts[i] += 1; left -= 1; progressed = True
        if not progressed:                      # more cameras than the approaches plausibly hold: share the rest out
            for i in range(len(pool)):
                if left:
                    counts[i] += 1; left -= 1
    cams = []
    for a, k in zip(pool, counts):
        h = math.radians(a["hdg"])
        perp = (math.cos(h), -math.sin(h))
        for j in range(k):
            off = (j - (k - 1) / 2) * 3.5
            lat, lon = ll((a["pos"][0] + perp[0] * off, a["pos"][1] + perp[1] * off), c)
            cams.append(dict(lat=round(lat, 6), lon=round(lon, 6), hdg=round(a["hdg"]), road=a["name"], src=a["src"]))
    return cams
