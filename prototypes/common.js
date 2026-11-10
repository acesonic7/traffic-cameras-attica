// Shared plumbing for the look-and-feel prototypes. Reads ../data.js (JUNCTIONS, AI_SITES); the main app is untouched.
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const M = 111320;
function offset(lat, lon, hdg, dist) {
  const r = hdg * Math.PI / 180;
  return [lon + Math.sin(r) * dist / (M * Math.cos(lat * Math.PI / 180)), lat + Math.cos(r) * dist / M];
}
function cone(c, reach = 32, fov = 40) {
  const ring = [[c.lon, c.lat]];
  for (let i = 0; i <= 10; i++) ring.push(offset(c.lat, c.lon, c.hdg - fov / 2 + fov * i / 10, reach));
  ring.push([c.lon, c.lat]);
  return ring;
}
const COVER = { all: "Όλες οι κατευθύνσεις", both: "Δύο ρεύματα", one: "Ένα ρεύμα" };
const TOTAL = JUNCTIONS.reduce((s, j) => s + j.cameras, 0);

const fc = features => ({ type: "FeatureCollection", features });
const geo = {
  junctions: () => fc(JUNCTIONS.map(j => ({ type: "Feature", id: j.id, geometry: { type: "Point", coordinates: [j.lon, j.lat] },
    properties: { id: j.id, n: j.cameras, node: String(j.node), name: j.location, cover: j.coverage, approx: j.approx, has: j.cams.length > 0,
                  tag: "Κ" + j.node + " · " + j.cameras } }))),
  cams: () => fc(JUNCTIONS.flatMap(j => j.cams.map((c, i) => ({ type: "Feature", geometry: { type: "Point", coordinates: [c.lon, c.lat] },
    properties: { j: j.id, hdg: c.hdg, cover: j.coverage } })))),
  cones: () => fc(JUNCTIONS.flatMap(j => j.cams.map(c => ({ type: "Feature", geometry: { type: "Polygon", coordinates: [cone(c)] },
    properties: { j: j.id, cover: j.coverage } })))),
  ai: () => fc(AI_SITES.map(a => ({ type: "Feature", id: a.id, geometry: { type: "Point", coordinates: [a.lon, a.lat] },
    properties: { id: a.id, name: a.location } })))
};

// Re-colour an OpenFreeMap style from a small palette. `hide` is a list of regexes for layer ids to drop.
async function themedStyle(base, p, hide = []) {
  const s = await (await fetch("https://tiles.openfreemap.org/styles/" + base)).json();
  const P = (l, k, v) => { l.paint = l.paint || {}; l.paint[k] = v; };
  s.layers = s.layers.filter(l => !hide.some(rx => rx.test(l.id)));
  s.layers.forEach(l => {
    const id = l.id, sl = l["source-layer"];
    if (l.type === "background") P(l, "background-color", p.land);
    else if (l.type === "fill") {
      if (sl === "water") P(l, "fill-color", p.water);
      else if (sl === "building") { P(l, "fill-color", p.building); P(l, "fill-outline-color", p.buildingLine || p.building); }
      else if (sl === "park" || /wood/.test(id)) { P(l, "fill-color", p.green); P(l, "fill-opacity", p.greenOpacity ?? 1); }
      else P(l, "fill-color", p.land2 || p.land);
    } else if (l.type === "line") {
      if (sl === "waterway") P(l, "line-color", p.water);
      else if (sl === "boundary") P(l, "line-color", p.boundary || p.minor);
      else if (/casing/.test(id)) P(l, "line-color", p.casing);
      else if (/motorway/.test(id)) P(l, "line-color", p.motorway);
      else if (/major/.test(id)) P(l, "line-color", p.major);
      else if (/rail/.test(id)) P(l, "line-color", p.rail || p.minor);
      else P(l, "line-color", p.minor);
    } else if (l.type === "symbol" && l.layout && l.layout["text-field"]) {
      P(l, "text-color", sl === "place" ? p.place : /water/.test(sl || "") ? p.waterLabel || p.label : p.label);
      P(l, "text-halo-color", p.halo); P(l, "text-halo-width", 1.2);
      if (p.font && sl === "place") l.layout["text-font"] = [p.font];
    }
  });
  return s;
}

async function makeMap(style, opts = {}) {
  const map = new maplibregl.Map({ container: "map", style, center: [23.72, 37.98], zoom: 10.2, maxPitch: 60, attributionControl: { compact: true }, ...opts });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  await new Promise(r => map.on("load", r));
  ["junctions", "cams", "cones", "ai"].forEach(k => map.addSource(k, { type: "geojson", data: geo[k]() }));
  return map;
}
function fit(map, pad = 60) {
  const b = new maplibregl.LngLatBounds();
  JUNCTIONS.forEach(j => b.extend([j.lon, j.lat]));
  map.fitBounds(b, { padding: pad, duration: 0 });
}
function popupHtml(j) {
  const flows = j.flows.map(f => `${esc(f.direction)}${j.flows.length > 1 ? " (" + f.cameras + ")" : ""}`).join("<br>");
  return `<div class="pop"><div class="k">Κόμβος ${j.node} · κάμερες παραβίασης ερυθρού σηματοδότη</div><h3>${esc(j.location)}</h3>
    <div class="row"><b>${j.cameras}</b> κάμερες · ${esc(j.area)}</div><div class="flows">${flows}</div></div>`;
}
function aiHtml(a) {
  return `<div class="pop"><div class="k">Κάμερα Τεχνητής Νοημοσύνης · πιλοτικό σύστημα</div><h3>${esc(a.location)}</h3>
    <div class="row">${esc(a.area)}</div><div class="flows">Ερυθρό, ταχύτητα, λεωφορειολωρίδες, ζώνη ή κράνος, κινητό</div></div>`;
}
function wireClicks(map, popup, junctionLayer, aiLayer) {
  map.on("click", e => {
    const h = map.queryRenderedFeatures(e.point, { layers: [aiLayer, junctionLayer] })[0];
    if (!h) return;
    const j = h.layer.id === aiLayer ? AI_SITES.find(a => a.id === h.properties.id) : JUNCTIONS.find(x => x.id === h.properties.id);
    popup.setLngLat([j.lon, j.lat]).setHTML(h.layer.id === aiLayer ? aiHtml(j) : popupHtml(j)).addTo(map);
  });
  [junctionLayer, aiLayer].forEach(id => {
    map.on("mouseenter", id, () => map.getCanvas().style.cursor = "pointer");
    map.on("mouseleave", id, () => map.getCanvas().style.cursor = "");
  });
}
function flyToJunction(map, popup, id) {
  const j = JUNCTIONS.find(x => x.id == id);
  popup.remove();
  map.flyTo({ center: [j.lon, j.lat], zoom: j.cams.length ? 17.4 : 16, speed: 1.6 });
  if (!j.cams.length) map.once("moveend", () => popup.setLngLat([j.lon, j.lat]).setHTML(popupHtml(j)).addTo(map));
}
