/* Evidence screens: Skills radar and Method. Each returns { html, bind(root) } like the other screens.
   Needs esc, head, real (screens.js, diagram.js) and api (app.js). Every number comes from the API, which reads data/. */

const EV = { radar: null, evidence: null, sel: null };
const evN = (v, d = 1) => (typeof v === "number" && isFinite(v) ? v.toFixed(d) : "n/a");
const evPct = (v, d = 1) => (typeof v === "number" && isFinite(v) ? `${(v * 100).toFixed(d)}%` : "n/a");
const evSigned = (v) => (typeof v === "number" && isFinite(v) ? `${v >= 0 ? "+" : ""}${(v * 100).toFixed(0)}%` : "n/a");
const evSafeUrl = (u) => (/^https?:\/\//i.test(u) ? u : "#");
const evAsOf = (d) => `${d.asOf || "?"}${d.partialMonth ? " (month in progress)" : ""}`;

/* Colour slots: AI stance for a tested Rising or Falling skill; grey for the rest. */
const EV_GROUPS = [
  ["AI-complement", "var(--ev-complement)", "AI-complement"],
  ["AI-substitutable", "var(--ev-substitutable)", "AI-substitutable"],
  ["neutral", "var(--ev-neutral)", "AI-neutral"],
  ["No clear change", "var(--ev-grey)", "No clear change"],
];
const evColor = (p) => (EV_GROUPS.find((g) => g[0] === p.group) || EV_GROUPS[3])[1];

function evState(kind, d) {
  if (d.error) return `<p class="empty" role="alert">${esc(d.error)}</p>`;
  return `<p class="empty" role="status">${kind}</p>`;
}

/* ── Radar ─────────────────────────────────────────────────────── */
function radarSVG(d) {
  const W = 760, H = 460, L = 58, R = 18, T = 18, B = 50;
  const pts = d.points;
  const xs = pts.map((p) => p.share), ys = pts.map((p) => p.change);
  const x0 = Math.log(Math.min(...xs) * 0.8), x1 = Math.log(Math.max(...xs) * 1.25);
  const y0 = Math.min(...ys, 0) - 0.06, y1 = Math.max(...ys, 0) + 0.06;
  const X = (v) => L + ((Math.log(v) - x0) / (x1 - x0)) * (W - L - R);
  const Y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  const xticks = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2].filter((v) => Math.log(v) > x0 && Math.log(v) < x1);
  const yticks = [];
  for (let v = Math.ceil(y0 * 4) / 4; v <= y1; v += 0.25) yticks.push(v);
  const grid = xticks.map((v) => `<line class="ev-grid" x1="${X(v)}" x2="${X(v)}" y1="${T}" y2="${H - B}"/><text class="ev-tick" x="${X(v)}" y="${H - B + 16}" text-anchor="middle">${evPct(v, v < 0.01 ? 1 : 0)}</text>`).join("")
    + yticks.map((v) => `<line class="ev-grid" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ev-tick" x="${L - 8}" y="${Y(v) + 4}" text-anchor="end">${evSigned(v)}</text>`).join("");
  const cut = d.shareCut ? `<line class="ev-cut" x1="${X(d.shareCut)}" x2="${X(d.shareCut)}" y1="${T}" y2="${H - B}"/>` : "";
  const quad = [
    ["Small, share up", L + 8, T + 14, "start"], ["Common, share up", W - R - 8, T + 14, "end"],
    ["Small, share down", L + 8, H - B - 8, "start"], ["Common, share down", W - R - 8, H - B - 8, "end"],
  ].map(([t, x, y, a]) => `<text class="ev-quad" x="${x}" y="${y}" text-anchor="${a}">${t}</text>`).join("");
  const dots = pts.slice().sort((a, b) => a.mine - b.mine).map((p) => {
    const c = evColor(p), grey = p.mark === "grey";
    const fill = p.mark === "hollow" ? "var(--paper)" : c;
    const label = `${p.skill}: ${evPct(p.share)} of posts, share change ${evSigned(p.change)}, ${p.trend_label}${p.contested ? ", AI stance contested" : ""}${p.mine ? ", one of your skills" : ""}`;
    return `<g class="ev-dot${EV.sel === p.skill ? " is-sel" : ""}" data-skill="${esc(p.skill)}" tabindex="0" role="button" aria-label="${esc(label)}">
      ${p.mine ? `<circle cx="${X(p.share)}" cy="${Y(p.change)}" r="10" class="ev-ring"/>` : ""}
      <circle cx="${X(p.share)}" cy="${Y(p.change)}" r="${grey ? 5 : 6.5}" fill="${fill}" stroke="${c}" stroke-width="2"/>
      ${p.mine ? `<text class="ev-name" x="${X(p.share) + 13}" y="${Y(p.change) + 4}">${esc(p.skill)}</text>` : ""}</g>`;
  }).join("");
  return `<svg class="ev-svg" viewBox="0 0 ${W} ${H}" role="group" aria-label="Skills by share of job posts and change in that share. The table below has the same data.">
    ${grid}<line class="ev-zero" x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}"/>${cut}${quad}
    <text class="ev-axis" x="${(L + W - R) / 2}" y="${H - 8}" text-anchor="middle">Share of job posts that mention the skill (log scale) →</text>
    <text class="ev-axis" transform="translate(14 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle">Change in share, last 12 months vs the 12 before →</text>${dots}</svg>`;
}

function radarLegend() {
  const items = EV_GROUPS.map((g) => `<span><i class="ev-sw" style="background:${g[1]}"></i>${g[2]}</span>`).join("");
  return `<div class="ev-legend" aria-label="Legend">${items}
    <span><i class="ev-sw ev-sw--hollow"></i>Hollow: AI stance contested</span>
    <span><i class="ev-sw ev-sw--mine"></i>Your skill</span></div>`;
}

function forecastText(p, band) {
  const f = p.forecast && p.forecast.moderate;
  if (!f) return "no forecast";
  return `${evPct(f.value_12m)} (${esc(band)} ${evPct(f.low)} to ${evPct(f.high)})`;
}

function detailHTML(d) {
  const p = d.points.find((x) => x.skill === EV.sel);
  if (!p) return `<p class="ev-hint">Select a dot or a row to see the skill in detail.</p>`;
  const f = p.forecast || {}, band = d.band.label || "range";
  const scen = (name, label) => (f[name]
    ? `<dt>${label}</dt><dd>${evPct(f[name].value_12m)}, ${esc(band)} ${evPct(f[name].low)} to ${evPct(f[name].high)}</dd>` : "");
  return `<div class="ev-detail" aria-live="polite">
    <h3>${esc(p.skill)}${p.mine ? " <small>your skill</small>" : ""}</h3>
    <dl>
      <dt>Share of posts now</dt><dd>${evPct(p.share)}</dd>
      <dt>Change in share</dt><dd>${evSigned(p.change)} (last 12 months vs the 12 before)</dd>
      <dt>Trend label</dt><dd>${esc(p.trend_label)}${p.trend_p === null ? "" : `, p = ${evN(p.trend_p, 3)}`}</dd>
      <dt>AI stance</dt><dd>${esc(p.stance)}${p.contested ? " (contested across indices)" : ""}</dd>
      ${scen("moderate", "12-month forecast, estimate")}${scen("fast", "Fast scenario, estimate")}
    </dl>
    <p class="ev-note">Estimate for ${esc(d.asOf || "?")} plus 12 months. The ${esc(band)} is a target, not a promise.</p></div>`;
}

function radarTable(d) {
  const band = d.band.label || "range";
  const rows = d.points.slice().sort((a, b) => b.share - a.share).map((p) => `<tr data-skill="${esc(p.skill)}" tabindex="0">
    <th scope="row">${esc(p.skill)}${p.mine ? ` <span class="yours">Yours</span>` : ""}</th>
    <td class="num">${evPct(p.share)}</td><td class="num">${evSigned(p.change)}</td>
    <td>${esc(p.trend_label)}${p.trend_p === null ? "" : ` <small>p = ${evN(p.trend_p, 3)}</small>`}</td>
    <td>${esc(p.stance)}${p.contested ? " <small>(contested)</small>" : ""}</td>
    <td class="num">${forecastText(p, band)}</td></tr>`).join("");
  return `<table class="ev-table"><caption>All ${d.points.length} skills. Forecast is an estimate for ${esc(d.asOf || "?")} plus 12 months.</caption>
    <thead><tr><th scope="col">Skill</th><th scope="col" class="num">Share now</th><th scope="col" class="num">Change</th><th scope="col">Trend label</th><th scope="col">AI stance</th><th scope="col" class="num">12-month forecast (estimate)</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function radarBody(d) {
  if (!d.points.length) return `<p class="empty">No skill has enough job posts to place on the radar.</p>`;
  const miss = d.unmapped.length ? `<p class="method">Not on the chart (no matching skill in the data): ${d.unmapped.map(esc).join(", ")}.</p>` : "";
  const noHeld = d.held.length ? "" : `<p class="method">Save a CV to mark your own skills on the chart.</p>`;
  return `<div class="ev-grid2">
    <section aria-labelledby="ev-chart-h"><h2 class="sec" id="ev-chart-h">Demand and change <small>Hacker News hiring posts</small></h2>
      ${radarSVG(d)}${radarLegend()}</section>
    <aside id="ev-detail" aria-label="Skill detail">${detailHTML(d)}</aside></div>
    <div class="ev-sentences">${d.sentences.map((s) => `<p>${esc(s)}</p>`).join("")}</div>${noHeld}${miss}
    <p class="method">${esc(d.howToRead)}</p>
    ${d.contestedKnown ? "" : `<p class="method" role="note">The AI-stance cross-check file is missing, so no mark is hollow.</p>`}
    <h2 class="sec">All skills <small>Same data as the chart</small></h2>${radarTable(d)}
    <p class="method">Source: ${esc(d.source.file)} (${esc(d.source.text)}); stance cross-check: ${esc(d.source.robustness)}. As of ${esc(evAsOf(d))}, generated ${esc(d.generatedAt || "?")}.</p>`;
}

function renderRadar() {
  const html = `${head("Skills radar", "Which skills employers ask for, and which are moving. Only a tested change gets a colour.", `<span id="ev-badge"></span>`)}
    <div id="ev-body" class="ev">${evState(EV.radar ? "" : "Loading the radar…", {})}</div>`;
  const bind = (root) => {
    const body = root.querySelector("#ev-body");
    const draw = (d) => {
      root.querySelector("#ev-badge").innerHTML = real(`Real data · HN hiring posts · as of ${esc(evAsOf(d))}`);
      body.innerHTML = radarBody(d);
      const pick = (skill) => {
        EV.sel = skill;
        body.querySelector("#ev-detail").innerHTML = detailHTML(d);
        body.querySelectorAll(".ev-dot").forEach((g) => g.classList.toggle("is-sel", g.dataset.skill === skill));
      };
      body.addEventListener("click", (e) => { const t = e.target.closest("[data-skill]"); if (t) pick(t.dataset.skill); });
      body.addEventListener("keydown", (e) => {
        const t = e.target.closest("[data-skill]");
        if (t && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); pick(t.dataset.skill); }
      });
    };
    api("/api/skills/radar").then((d) => { EV.radar = d; draw(d); })
      .catch((e) => { body.innerHTML = evState("", { error: e instanceof TypeError ? "The server cannot be reached." : e.message }); });
  };
  return { html, bind };
}

/* ── Method ────────────────────────────────────────────────────── */
function maeTable(bt, unit) {
  const cell = (o, h) => evN(o && o[h], 2);
  const rows = bt.models.map((m) => {
    const g = m.gainVsNaive, ci = g && (g.ci95_skill_bootstrap || g.ci95_role_bootstrap);
    return `<tr><th scope="row">${esc(m.model)}${m.inProduction ? " <small>in use</small>" : ""}</th>
      ${["h1", "h6", "h12"].map((h) => `<td class="num">${cell(m.early, h)}</td>`).join("")}
      ${["h1", "h6", "h12"].map((h) => `<td class="num">${cell(m.test, h)}</td>`).join("")}
      <td class="num">${g ? `${evN(g.test_h12_mae_gain_pp, 2)}${ci ? ` <small>(95% CI ${evN(ci[0], 2)} to ${evN(ci[1], 2)})</small>` : ""}` : "baseline"}</td></tr>`;
  }).join("");
  return `<table class="ev-table"><caption>Mean absolute error of the share, in percentage points. Lower is better. h = months ahead. Gain: test h=12 error of "naive" minus this model.</caption>
    <thead><tr><th scope="col">Model</th><th scope="col" class="num">Early h=1</th><th scope="col" class="num">Early h=6</th><th scope="col" class="num">Early h=12</th><th scope="col" class="num">Test h=1</th><th scope="col" class="num">Test h=6</th><th scope="col" class="num">Test h=12</th><th scope="col" class="num">Gain vs naive (pp)</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function backtestSection(bt, title) {
  if (!bt) return "";
  const o = bt.origins || {}, c = bt.coverage || {}, t = bt.trendLabel || {};
  const groups = Object.entries(c.by_share_group || {}).map(([k, g]) => `<tr><th scope="row">${esc(k.replace(/_/g, " "))}</th>
    <td class="num">${g.n_skill_origins ?? g.n_role_origins ?? "n/a"}</td><td class="num">${evPct(g.h12)}</td><td class="num">${evN(g.mean_band_width_h12_pp, 1)}</td></tr>`).join("");
  return `<section class="ev-sec" aria-labelledby="bt-${esc(bt.kind)}"><h2 class="sec" id="bt-${esc(bt.kind)}">${esc(title)} <small>Backtest, data ${esc((bt.dataWindow || {}).from || "?")} to ${esc((bt.dataWindow || {}).to || "?")}, run ${esc((bt.generatedAt || "?").slice(0, 10))}</small></h2>
    <p>We replayed history: at each origin month we forecast 1 to 12 months ahead and compared with what happened. Early origins ${esc((o.early || ["?", "?"]).join(" to "))} (${o.n_early ?? "?"}); test origins ${esc((o.test || ["?", "?"]).join(" to "))} (${o.n_test ?? "?"}).</p>
    ${maeTable(bt)}
    <p><b>Chosen model: ${esc(bt.chosenModel || "n/a")}.</b> ${esc(bt.chosenBecause || "")} ${esc(bt.verdict || "")}</p>
    <h3>Band coverage</h3>
    <p>The ${esc(c.label || "band")} covered <b>${evPct(c.test_h12)}</b> of real values at h=12 on the test origins (target ${evPct(c.nominal, 0)}), mean band width ${evN(c.test_mean_band_width_h12_pp, 1)} pp. A coverage above the target means the band is wide, not tight.${bt.interval ? ` Band type: ${esc(bt.interval)}.` : ""}</p>
    ${groups ? `<table class="ev-table"><caption>Coverage by share group. ${esc(c.share_group_definition || "")}</caption><thead><tr><th scope="col">Share group</th><th scope="col" class="num">Origins</th><th scope="col" class="num">Coverage at h=12</th><th scope="col" class="num">Mean band width (pp)</th></tr></thead><tbody>${groups}</tbody></table>` : ""}
    <h3>Trend label hit rate</h3>
    <p>A Rising or Falling label pointed the right way for the next 12 months <b>${evPct(t.trend_label_hit_rate)}</b> of the time (n = ${t.n ?? "n/a"}). Rising: ${evPct(t.hit_rate_rising)} (n = ${t.n_rising ?? "n/a"}). Falling: ${evPct(t.hit_rate_falling)} (n = ${t.n_falling ?? "n/a"}).</p>
    <p class="method">${esc(t.definition || "")} ${esc(t.caveat || "")}</p>
    ${bt.sampleNote ? `<p class="method">${esc(bt.sampleNote)}</p>` : ""}
    <ul class="ev-list">${bt.caveats.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></section>`;
}

function exposureSection(x, k) {
  if (!x) return "";
  const occ = x.occupations.map((o) => `<tr><th scope="row">${esc(o.title)}</th><td>${esc(o.category)}</td><td class="num">${evN(o.automationPct, 1)}%</td></tr>`).join("");
  const cc = x.crossCheck || [];
  const cols = cc.length ? Object.keys(cc[0]) : [];
  const ccTable = cc.length ? `<table class="ev-table"><caption>Each source cell: the category's z-score (0 = average of the 40 skills) and the stance that source would give.</caption>
    <thead><tr>${cols.map((c) => `<th scope="col">${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${cc.map((r) => `<tr>${cols.map((c, i) => (i === 0 ? `<th scope="row">${esc(r[c])}</th>` : `<td>${esc(r[c])}</td>`)).join("")}</tr>`).join("")}</tbody></table>` : "";
  const kHTML = k ? `<h3>The size of the AI effect (k)</h3><p><span class="ev-tag">assumption</span> ${esc(k.line)}</p><p class="method">${esc(k.caption)} Generated ${esc((k.generatedAt || "?").slice(0, 10))}.</p>` : "";
  return `<section class="ev-sec" aria-labelledby="ex-h"><h2 class="sec" id="ex-h">AI exposure <small>Anthropic Economic Index and three other sources</small></h2>
    <p>The AI stance of a skill comes from the share of work in its occupations that people hand over to AI in Claude.ai usage (Anthropic Economic Index, automation share). The category-to-occupation map is a team judgement.</p>
    <table class="ev-table"><caption>Automation share by occupation</caption><thead><tr><th scope="col">Occupation</th><th scope="col">Skill category</th><th scope="col" class="num">Automation share</th></tr></thead><tbody>${occ}</tbody></table>
    ${cc.length ? `<h3>Cross-check: which stances are robust, which are contested</h3>${ccTable}
      <p>${esc(x.correlation || "")}</p><p>${esc(x.agreementText || "")}</p>
      <p class="method">${(x.caveats || []).map(esc).join(" ")}</p>` : `<p class="method">The cross-check file (exposure_agreement.json) is missing.</p>`}
    ${kHTML}</section>`;
}

function methodBody(d) {
  const miss = d.missing.length ? `<p class="method" role="note">Not shown, file missing: ${d.missing.map(esc).join(", ")}.</p>` : "";
  const src = d.sources.map((s) => `<li><a href="${esc(evSafeUrl(s.url))}" target="_blank" rel="noopener">${esc(s.title)}</a></li>`).join("");
  return `${backtestSection(d.backtests.skills, "How good is the skill forecast?")}
    ${backtestSection(d.backtests.roles, "How good is the role forecast?")}
    ${exposureSection(d.exposure, d.k)}
    ${src ? `<section class="ev-sec" aria-labelledby="src-h"><h2 class="sec" id="src-h">Data sources <small>${d.sourcesChecked ? `Checked ${esc(d.sourcesChecked)}` : "Full list in data/SOURCES.md"}</small></h2><ul class="ev-list">${src}</ul>
      <p class="method">Full list with dates and licences: data/SOURCES.md.</p></section>` : ""}${miss}`;
}

function renderMethod() {
  const html = `${head("Method", "How the forecast and the AI stance were tested, and where every number comes from. Each figure is read from a file in data/.", `<span id="ev-badge"></span>`)}
    <div id="ev-body" class="ev">${evState("Loading the evidence…", {})}</div>`;
  const bind = (root) => {
    const body = root.querySelector("#ev-body");
    api("/api/evidence").then((d) => {
      EV.evidence = d;
      root.querySelector("#ev-badge").innerHTML = real(`Real data · backtests · as of ${esc(d.asOf || "?")}`);
      body.innerHTML = methodBody(d);
    }).catch((e) => { body.innerHTML = evState("", { error: e instanceof TypeError ? "The server cannot be reached." : e.message }); });
  };
  return { html, bind };
}
