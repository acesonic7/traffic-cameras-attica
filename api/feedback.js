// Vercel serverless function: turns a feedback form submission into a GitHub issue.
// Needs the environment variable GITHUB_TOKEN (a fine-grained token with "Issues: read and write" on the
// repository). GITHUB_REPO is optional and defaults to the map's own repository.
// Visitors need no account. Nothing is stored here; the issue on GitHub is the record.

const REPO = process.env.GITHUB_REPO || "acesonic7/traffic-cameras-attica";
const ATTICA = { latMin: 37.5, latMax: 38.5, lonMin: 23.0, lonMax: 24.3 };
const ISSUE_KINDS = { position: "Λάθος θέση", missing: "Δεν υπάρχει κάμερα εδώ", details: "Λάθος στοιχεία (αριθμός, κατεύθυνση)", other: "Άλλο" };
const hits = new Map();   // best-effort per-instance throttle; instances are short-lived, so this only stops bursts

const clean = (s, max) => String(s == null ? "" : s).replace(/[\u0000-\u0008\u000b-\u001f]/g, "").trim().slice(0, max);
// user text goes into a public issue: neutralise mentions, issue references and HTML so it cannot ping people or inject markup
const quote = s => s.replace(/@/g, "@​").replace(/#(?=\d)/g, "#​").replace(/</g, "&lt;").split("\n").map(l => "> " + l).join("\n");
const coord = v => (typeof v === "number" && Number.isFinite(v) ? v : null);
const inAttica = (lat, lon) => lat != null && lon != null && lat >= ATTICA.latMin && lat <= ATTICA.latMax && lon >= ATTICA.lonMin && lon <= ATTICA.lonMax;
const osm = (lat, lon) => `[${lat.toFixed(6)}, ${lon.toFixed(6)}](https://www.openstreetmap.org/?mlat=${lat.toFixed(6)}&mlon=${lon.toFixed(6)}#map=19/${lat.toFixed(6)}/${lon.toFixed(6)})`;
function metres(a, b) {
  const k = 111320, dy = (a[0] - b[0]) * k, dx = (a[1] - b[1]) * k * Math.cos(a[0] * Math.PI / 180);
  return Math.round(Math.hypot(dx, dy));
}

function build(body) {
  const type = body.type === "point" ? "point" : "general";
  const message = clean(body.message, 2000);
  if (clean(body.website, 50)) return { skip: true };            // honeypot field: bots fill it, people never see it
  if (type === "general") {
    if (message.length < 5) return { error: "empty" };
    return { title: "[Σχόλιο] " + message.replace(/\s+/g, " ").slice(0, 70), labels: ["feedback"],
             text: `**Γενικό σχόλιο από τον χάρτη**\n\n${quote(message)}\n` };
  }
  const label = clean(body.label, 160), ref = clean(body.ref, 60), kind = ISSUE_KINDS[body.issue] ? body.issue : "other";
  const lat = coord(body.lat), lon = coord(body.lon), sLat = coord(body.suggestLat), sLon = coord(body.suggestLon);
  if (!label || !inAttica(lat, lon)) return { error: "target" };
  const hasSuggestion = sLat != null && sLon != null;
  if (hasSuggestion && !inAttica(sLat, sLon)) return { error: "suggestion" };
  if (!hasSuggestion && message.length < 5 && kind !== "missing") return { error: "empty" };
  let text = `**Αναφορά λάθους από τον χάρτη**\n\n| | |\n|---|---|\n| Σημείο | ${label.replace(/\|/g, "/")} |\n| Αναφορά | \`${ref.replace(/`/g, "")}\` |\n| Πρόβλημα | ${ISSUE_KINDS[kind]} |\n| Θέση στον χάρτη | ${osm(lat, lon)} |\n`;
  if (hasSuggestion) text += `| Προτεινόμενη θέση | ${osm(sLat, sLon)} (${metres([lat, lon], [sLat, sLon])} m από την τρέχουσα) |\n`;
  if (message) text += `\n${quote(message)}\n`;
  return { title: `[Αναφορά] ${label.slice(0, 90)} · ${ISSUE_KINDS[kind]}`, labels: ["position-report"], text };
}

async function createIssue(payload, token) {
  const call = body => fetch(`https://api.github.com/repos/${REPO}/issues`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "Content-Type": "application/json", "User-Agent": "traffic-cameras-attica-feedback" },
    body: JSON.stringify(body)
  });
  let r = await call({ title: payload.title, body: payload.text, labels: payload.labels });
  if (r.status === 422 || r.status === 403) r = await call({ title: payload.title, body: payload.text });  // labels may not be permitted
  return r;
}

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") return res.status(405).json({ ok: false, error: "method" });
  // same-site only: the form posts from the map's own pages
  const origin = req.headers.origin || "", host = req.headers.host || "";
  if (origin && host && new URL(origin).host !== host) return res.status(403).json({ ok: false, error: "origin" });
  const ip = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim() || "?";
  const now = Date.now(), recent = (hits.get(ip) || []).filter(t => now - t < 600000);
  if (recent.length >= 5) return res.status(429).json({ ok: false, error: "rate" });
  let body = req.body;
  if (typeof body === "string") { try { body = JSON.parse(body); } catch (e) { body = null; } }
  if (!body || typeof body !== "object" || JSON.stringify(body).length > 6000) return res.status(400).json({ ok: false, error: "body" });
  const payload = build(body);
  if (payload.skip) return res.status(200).json({ ok: true });
  if (payload.error) return res.status(400).json({ ok: false, error: payload.error });
  const token = process.env.GITHUB_TOKEN;
  if (!token) return res.status(503).json({ ok: false, error: "not_configured" });
  payload.text += `\n<sub>Στάλθηκε από τη φόρμα του χάρτη · ${new Date().toISOString().slice(0, 16).replace("T", " ")} UTC · γλώσσα: ${clean(body.lang, 5) || "el"}</sub>\n`;
  try {
    const r = await createIssue(payload, token);
    if (!r.ok) { console.error("GitHub issue failed", r.status, (await r.text()).slice(0, 300)); return res.status(502).json({ ok: false, error: "github" }); }
    recent.push(now); hits.set(ip, recent);
    return res.status(200).json({ ok: true });
  } catch (e) {
    console.error("GitHub request error", e && e.message);
    return res.status(502).json({ ok: false, error: "github" });
  }
};
module.exports.build = build;   // exported for tests
