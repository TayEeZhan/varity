/* SVG line diagrams: pathway map, today's route strip, user-flow map, ridership bands. */

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

/* Links come from crawled feeds or the API: allow only http(s). */
const safeUrl = (u) => (/^https?:\/\//i.test(u) ? u : "#");

/* Split a label into lines of roughly `max` characters on word boundaries. */
function wrap(text, max) {
  const lines = [];
  let cur = "";
  for (const word of text.split(" ")) {
    if (cur && (cur + " " + word).length > max) { lines.push(cur); cur = word; }
    else cur = cur ? cur + " " + word : word;
  }
  if (cur) lines.push(cur);
  return lines;
}

function textBlock(x, y, lines, { anchor = "middle", cls = "stn__label", lh = 15 } = {}) {
  return lines.map((l, i) => `<text class="${cls}" x="${x}" y="${y + i * lh}" text-anchor="${anchor}">${esc(l)}</text>`).join("");
}

function stationMark(x, y, status) {
  if (status === "done") return `<circle class="stn__dot" cx="${x}" cy="${y}" r="9" fill="#121212" stroke="#121212" stroke-width="3"/>`;
  if (status === "current") {
    return `<circle class="here" cx="${x}" cy="${y}" r="13" fill="none" stroke="#121212" stroke-width="2"/>`
      + `<circle cx="${x}" cy="${y}" r="17" fill="#fccc0a"/>`
      + `<circle class="stn__dot" cx="${x}" cy="${y}" r="10" fill="#fff" stroke="#121212" stroke-width="4"/>`;
  }
  return `<circle class="stn__dot" cx="${x}" cy="${y}" r="8" fill="#fff" stroke="#121212" stroke-width="3"/>`;
}

/* ── Pathway route map ─────────────────────────────────────────── */
function pathwaySVG() {
  const T = 1110; // terminus x
  const y = (line) => LINES[line].y;
  // Each line starts just before its first station; a line with no station is not drawn.
  const lines = ["guard", "apps", "serve"].map((l) => {
    const xs = PATHWAY.filter((s) => s.line === l || s.interchange === l).map((s) => s.x);
    return xs.length ? `<path class="ln ln--${l}" data-line="${l}" d="M ${Math.min(...xs) - 20} ${y(l)} H ${T}"/>` : "";
  }).join("");

  const stations = PATHWAY.map((s) => {
    const sy = y(s.line);
    const below = s.line !== "guard";
    const words = wrap(s.title, 16);
    const base = s.interchange ? Math.max(sy, y(s.interchange)) : sy; // label under the lower line of an interchange
    const labelY = below ? base + 34 : sy - 38 - (words.length - 1) * 15;
    const label = textBlock(s.x, labelY, words);
    const subY = below ? labelY + words.length * 15 : sy - 22;
    const minutes = `<text class="stn__sub" x="${s.x}" y="${subY}" text-anchor="middle">Wk ${s.week} · ${s.mins} min</text>`;
    let mark = stationMark(s.x, sy, s.status);
    if (s.interchange) {
      const oy = y(s.interchange);
      const top = Math.min(sy, oy) - 10;
      mark = `<rect class="stn__dot" x="${s.x - 10}" y="${top}" width="20" height="${Math.abs(sy - oy) + 20}" rx="10" fill="#fff" stroke="#121212" stroke-width="3"/>`;
    }
    const lit = s.interchange ? `${s.line} ${s.interchange}` : s.line;
    const state = s.status === "done" ? "done" : s.status === "current" ? "you are here" : "upcoming";
    return `<g class="stn" tabindex="0" data-stop="${s.id}" data-line="${lit}" aria-label="${esc(s.title)}, week ${s.week}, ${s.mins} minutes, ${state}">${mark}${label}${minutes}</g>`;
  }).join("");

  const terminus = `<g class="stn" data-line="apps guard serve">
      <rect x="${T - 11}" y="56" width="22" height="248" rx="11" fill="#fff" stroke="#121212" stroke-width="4"/>
      ${textBlock(T + 26, 172, wrap(TARGET.role, 16), { anchor: "start", lh: 20 }).replace(/class="stn__label"/g, 'class="stn__label" style="font-size:17px;font-weight:800"')}
      <text class="stn__sub" x="${T + 26}" y="${172 + wrap(TARGET.role, 16).length * 20}">Target role</text>
    </g>`;

  const names = [...new Set(PATHWAY.map((s) => LINES[s.line].name))].join(", ");
  return `<svg viewBox="0 0 1280 360" role="img" aria-labelledby="pm-title"><title id="pm-title">Route map: ${esc(names)} converging on ${esc(TARGET.role)}</title>${lines}${stations}${terminus}</svg>`;
}

/* ── Today's route strip: the whole pathway as one ride ────────── */
function stripSVG() {
  if (!PATHWAY.length) return "";
  const W = 1060, Y = 128, x0 = 40, x1 = 840;
  const step = (x1 - x0) / Math.max(PATHWAY.length - 1, 1);
  const pts = PATHWAY.map((s, i) => ({ ...s, sx: x0 + i * step }));
  const segs = pts.slice(1).map((p, i) => `<line x1="${pts[i].sx}" y1="${Y}" x2="${p.sx}" y2="${Y}" stroke="var(--${p.line})" stroke-width="10" stroke-linecap="round"/>`).join("")
    + `<line x1="${pts[pts.length - 1].sx}" y1="${Y}" x2="${W - 166}" y2="${Y}" stroke="var(--apps)" stroke-width="10" stroke-linecap="round"/>`;
  const stns = pts.map((p) => {
    const weight = p.status === "current" ? 800 : 600;
    const lbl = `<text class="stn__label" transform="translate(${p.sx + 6} ${Y - 24}) rotate(-35)" style="font-size:12px;font-weight:${weight}">${esc(p.title)}</text>`;
    return `<g>${stationMark(p.sx, Y, p.status)}${lbl}</g>`;
  }).join("");
  const cur = pts.find((p) => p.status === "current") || pts[pts.length - 1];
  const here = `<rect x="${cur.sx - 46}" y="${Y + 24}" width="92" height="22" rx="3" fill="#fccc0a"/><text x="${cur.sx}" y="${Y + 39}" text-anchor="middle" style="font-size:12px;font-weight:800">You are here</text>`;
  const term = `<rect x="${W - 172}" y="${Y - 18}" width="18" height="36" rx="9" fill="#fff" stroke="#121212" stroke-width="4"/>`
    + `<text class="stn__label" transform="translate(${W - 158} ${Y - 28}) rotate(-35)" style="font-size:13px;font-weight:800">${esc(TARGET.role)}</text>`;
  const n = pts.indexOf(cur) + 1;
  return `<svg viewBox="0 0 ${W} 172" role="img" aria-label="Your route: ${PATHWAY.length} stops to ${esc(TARGET.role)}. You are at stop ${n}.">${segs}${stns}${here}${term}</svg>`;
}

/* ── User-flow map ─────────────────────────────────────────────── */
const FLOW_LABEL = {
  f1: { dx: 0, dy: 38, a: "middle" }, f2: { dx: 0, dy: 38, a: "middle" }, f3: { dx: 0, dy: 38, a: "middle" },
  f4: { dx: 0, dy: 38, a: "middle" }, f5: { dx: 0, dy: 40, a: "middle" }, f6: { dx: -6, dy: 38, a: "end" },
  f7: { dx: 22, dy: -20, a: "start" }, f8: { dx: 0, dy: -24, a: "middle" }, f9: { dx: 24, dy: 5, a: "start" },
  f10: { dx: 0, dy: -26, a: "middle" }, f11: { dx: 0, dy: -30, a: "middle" }, f12: { dx: -22, dy: -18, a: "end" },
  f13: { dx: 24, dy: 5, a: "start" }, f14: { dx: 0, dy: 38, a: "middle" },
};

function flowSVG() {
  const p = FLOW.paths;
  const lines = `<path class="ln ln--loop" data-line="loop" d="${p.loop}"/>`
    + `<path class="ln ln--explore" data-line="explore" d="${p.explore1}"/>`
    + `<path class="ln ln--explore" data-line="explore" d="${p.explore2}"/>`
    + `<path class="ln ln--ride" data-line="ride" d="${p.ride}"/>`;
  const stns = FLOW.stations.map((s) => {
    const L = FLOW_LABEL[s.id];
    const ring = s.interchange ? `<circle cx="${s.x}" cy="${s.y}" r="18" fill="#fff" stroke="#121212" stroke-width="3"/>` : "";
    const dot = `<circle class="stn__dot" cx="${s.x}" cy="${s.y}" r="12" fill="#fff" stroke="#121212" stroke-width="3"/>`;
    const num = `<text x="${s.x}" y="${s.y + 4}" text-anchor="middle" style="font-size:11px;font-weight:800">${s.n}</text>`;
    const words = wrap(s.label, 11);
    const label = textBlock(s.x + L.dx, s.y + L.dy - (L.dy < 0 ? (words.length - 1) * 15 : 0), words, { anchor: L.a });
    const lit = s.interchange ? `${s.line} explore` : s.line;
    return `<g class="stn" tabindex="0" role="button" data-flow="${s.id}" data-line="${lit}" aria-label="Step ${s.n}: ${esc(s.label)}">${ring}${dot}${num}${label}</g>`;
  }).join("");
  return `<svg viewBox="0 0 1200 480" role="img" aria-labelledby="fm-title"><title id="fm-title">User flow drawn as a transit map: first ride, daily loop and explore lines</title>${lines}${stns}</svg>`;
}

/* ── Ridership band: thickness = weekly mentions, one shared scale for every skill ── */
function ridershipSVG(weekly, max, color) {
  const xs = [6, 33, 60, 87, 114];
  const half = (v) => Math.max(0.75, (v / max) * 15);
  const top = xs.map((x, i) => `${x},${17 - half(weekly[i])}`).join(" ");
  const bot = xs.map((x, i) => `${x},${17 + half(weekly[i])}`).reverse().join(" ");
  return `<svg viewBox="0 0 120 34" preserveAspectRatio="none" aria-hidden="true"><polygon points="${top} ${bot}" fill="${color}"/></svg>`;
}

/* Hovering or focusing a station lights its line(s) and dims the rest. */
function bindLineLighting(root, onStop) {
  const svg = root.querySelector("svg");
  if (!svg) return;
  const light = (g) => {
    const ids = (g.dataset.line || "").split(" ");
    svg.classList.add("dim");
    svg.querySelectorAll(".ln, .stn").forEach((n) => {
      const nl = (n.dataset.line || "").split(" ");
      n.classList.toggle("is-lit", nl.some((l) => ids.includes(l)));
    });
    if (onStop) onStop(g, true);
  };
  const clear = (g) => {
    svg.classList.remove("dim");
    svg.querySelectorAll(".is-lit").forEach((n) => n.classList.remove("is-lit"));
    if (onStop) onStop(g, false);
  };
  svg.querySelectorAll(".stn").forEach((g) => {
    g.addEventListener("mouseenter", () => light(g));
    g.addEventListener("mouseleave", () => clear(g));
    g.addEventListener("focus", () => light(g));
    g.addEventListener("blur", () => clear(g));
  });
}
