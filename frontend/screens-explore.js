/* Screen renderers for Signals, Job forecast and the Flow map. Each returns { html, bind(root) }. */

/* ── Signals ───────────────────────────────────────────────────── */
const FILTERS = [
  { id: "all", label: "All", match: () => true },
  { id: "security", label: "Security", match: (s) => s.category === "Security incident" },
  { id: "research", label: "Research", match: (s) => s.category === "Research" },
  { id: "product", label: "Products", match: (s) => s.category === "Product feature" },
  { id: "policy", label: "APIs & policy", match: (s) => /API|Policy/.test(s.category) },
  { id: "models", label: "Model releases", match: (s) => s.category === "Model release" },
];

function noticesHTML() {
  const f = FILTERS.find((x) => x.id === STATE.filter);
  const list = STORIES.filter(f.match);
  if (!list.length) {
    return `<p class="empty">No ${f.label.toLowerCase()} in today's top 10. Lower-ranked stories are still tracked; this view only shows what is worth your time today.</p>`;
  }
  const max = STORIES[0].score;
  return list.map((s) => `<article class="notice">
      <div class="notice__rank">${s.rank}</div>
      <div>
        <div class="notice__title"><a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener">${esc(s.title)}</a></div>
        <div class="notice__meta">${esc(s.category)} · ${s.sources.map(esc).join(" + ")} · first seen ${esc(s.date)}</div>
        <div class="notice__why">Ranks here because: ${s.why.map(esc).join(" · ")}</div>
      </div>
      <div class="notice__score">${s.score.toFixed(1)}<small>score</small><i style="width:${Math.round((s.score / max) * 100)}%"></i></div>
    </article>`).join("");
}

function renderSignals() {
  const skills = SKILLS.slice().sort((a, b) => b.momentum - a.momentum);
  const max = Math.max(...SKILLS.flatMap((s) => s.weekly));
  const rows = skills.map((s) => {
    const color = "#8a8b8e";
    return `<tr><td>${esc(s.skill)}</td><td>${ridershipSVG(s.weekly, max, color)}</td><td class="num">${s.weekly[4]}</td><td class="num hide-sm">+${s.momentum.toFixed(1)}</td></tr>`;
  }).join("");

  const html = `
    ${head("Signals", "What moved in AI and dev tooling this week, ranked by a fixed formula from dated, named sources. Every rank shows its reasons.", (STATE.signalsLive ? real : snapshot)(`${STATE.signalsLive ? "Real data" : "Offline snapshot"} · ${SIGNAL_RUN.storyCount} stories · ${SIGNAL_RUN.generatedAt}`))}
    <div class="signals-grid">
      <section aria-labelledby="sm-h">
        <h2 class="sec" id="sm-h">Skill momentum <small>Mentions per week, last 5 weeks</small></h2>
        <table class="ridership">
          <thead><tr><th scope="col">Skill</th><th scope="col">5 weeks →</th><th scope="col" class="num">This week</th><th scope="col" class="num hide-sm">Momentum</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <p class="method">Line thickness is mentions per week, on one shared scale (thickest = ${max}). Momentum = (this week − the earlier weekly average) ÷ that average, with the average floored at 1.</p>
      </section>
      <section aria-labelledby="sn-h">
        <h2 class="sec" id="sn-h">Service notices <small>Top 10 of ${SIGNAL_RUN.storyCount}</small></h2>
        <div class="filters" role="group" aria-label="Filter notices">
          ${FILTERS.map((f) => `<button class="filter" data-filter="${f.id}" aria-pressed="${STATE.filter === f.id}">${f.label}</button>`).join("")}
        </div>
        <div data-notices>${noticesHTML()}</div>
      </section>
    </div>`;

  const bind = (root) => {
    root.querySelectorAll("[data-filter]").forEach((b) => b.addEventListener("click", () => {
      STATE.filter = b.dataset.filter;
      root.querySelectorAll("[data-filter]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      root.querySelector("[data-notices]").innerHTML = noticesHTML();
    }));
  };
  return { html, bind };
}

/* ── Job forecast ──────────────────────────────────────────────── */
/* Data: FORECAST = data/role_forecast.json (engine/role_forecast.py), live from GET /api/roles/forecast. */
const TREND_ORDER = { Rising: 0, "No clear change": 1, Falling: 2 };
const TREND_CLASS = { Rising: "up", Falling: "down" };
const pct = (v) => `${(v * 100).toFixed(1)}%`;

function renderForecast() {
  const roles = Object.values(FORECAST.roles || {});
  const ok = roles.filter((r) => r.status === "ok" && r.share_now && r.forecast_moderate && r.trend)
    .sort((a, b) => (TREND_ORDER[a.trend.label] ?? 1) - (TREND_ORDER[b.trend.label] ?? 1) || b.share_now.value - a.share_now.value);
  const skipped = [...roles.filter((r) => !ok.includes(r)).map((r) => ({ name: r.name, reason: r.note || "No forecast for this month" })),
    ...(FORECAST.excluded_roles || []).map((r) => ({ name: r.name, reason: r.reason }))];
  // One shared axis from 0 to just past the widest range, rounded up to a whole percent.
  const top = Math.ceil(Math.max(0.01, ...ok.map((r) => r.forecast_moderate.high)) * 100) / 100;
  const pos = (v) => (Math.max(0, Math.min(top, v)) / top) * 100;
  const step = top > 0.1 ? 0.05 : 0.02;
  const ticks = Array.from({ length: Math.floor(top / step + 1e-9) + 1 }, (_, i) => i * step);
  const band = FORECAST.interval ? FORECAST.interval.label : "range";
  const hnLinks = (r) => (r.sources || []).filter((s) => /^https?:\/\//i.test(s.url))
    .map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.date)}</a>`).join(" · ");

  const rowHTML = (r) => {
    const f = r.forecast_moderate, t = r.trend, cls = TREND_CLASS[t.label] || "";
    return `<div class="fc__row">
      <div class="fc__role">${esc(r.name)}<small class="trend ${cls}">${esc(t.label)}</small></div>
      <div class="fc__track" role="img" aria-label="${esc(r.name)}: ${pct(r.share_now.value)} of hiring posts now; in 12 months ${pct(f.value_12m)}, ${esc(band)} ${pct(f.low)} to ${pct(f.high)}; ${esc(t.label)}">
        <span class="fc__band" style="left:${pos(f.low)}%;width:${pos(f.high) - pos(f.low)}%"></span>
        <span class="fc__bar ${cls}" style="left:calc(${pos(f.value_12m)}% - 5px);width:10px"></span>
        <span class="fc__other" style="left:calc(${pos(r.share_now.value)}% - 1px)"></span>
      </div>
      <div class="fc__val ${cls}">${pct(r.share_now.value)}</div>
      <div class="fc__drv"><b>${t.mentions_last12}</b> posts in the last 12 months vs <b>${t.mentions_prev12}</b> the 12 before
        (${pct(t.share_last12)} vs ${pct(t.share_prev12)} of posts)<br><small>HN threads: ${hnLinks(r) || "none"}</small></div>
    </div>`;
  };

  const html = `
    ${head("Job forecast", "How demand for tech roles may change over the next 12 months, from the share of Hacker News “Who is hiring?” posts that name each role. Ranges are estimates, not counts. Two scenarios exist for routes: the forecast here is the moderate one; the fast AI scenario is shown on CV &amp; routes, also as an estimate.")}
    <div class="fc-bar-head">
      ${(STATE.forecastLive ? real : snapshot)(`${STATE.forecastLive ? "Real data" : "Offline snapshot"} · HN hiring posts · as of ${(FORECAST.as_of || "?") + (FORECAST.partial_month ? " (month in progress)" : "")}`)}
      <div class="fc-key">
        <span><i class="k-tick"></i>Share now</span>
        <span><i class="k-bar"></i>In 12 months</span>
        <span><i class="k-band"></i>${esc(band)}</span>
      </div>
    </div>
    <section class="fc" aria-label="Share of hiring posts by role, now and in 12 months">
      <div class="fc__axis"><div>Role</div><div class="fc__ticks">${ticks.map((v) => `<span style="left:${pos(v)}%">${Math.round(v * 100)}%</span>`).join("")}</div><div style="text-align:right">Now</div><div>Why</div></div>
      <div>${ok.map(rowHTML).join("") || `<p class="empty">No role forecast yet. Run engine/role_forecast.py.</p>`}</div>
    </section>
    ${skipped.length ? `<p class="method">Left out: ${skipped.map((s) => `${esc(s.name)} (${esc(s.reason)})`).join("; ")}.</p>` : ""}
    <div class="fc-note">
      <div><h3>What the numbers mean</h3><p>Share of monthly HN hiring posts that name the role (last 3 months), and where that share is expected to be in 12 months. HN is a sample of tech hiring, not a count of jobs.</p></div>
      <div><h3>Rising or falling</h3><p>The trend label compares the last 12 months with the 12 before. It is observed, not forecast. “No clear change” means the difference could be noise.</p></div>
      <div><h3>Use it as one input</h3><p>The forecast shapes which routes Varity suggests. It does not decide for you: you pick the route.</p></div>
    </div>`;

  return { html, bind: () => {} };
}

/* ── Flow map ──────────────────────────────────────────────────── */
const FLOW_LINES = {
  ride: { name: "First ride", note: "once", color: "var(--ride)" },
  loop: { name: "Daily loop", note: "every morning", color: "var(--loop)" },
  explore: { name: "Explore", note: "any time", color: "var(--explore)" },
};
const SCREEN_NAME = { profile: "CV & routes", today: "Today", pathway: "Pathway", signals: "Signals", forecast: "Job forecast" };

function stopCard(s) {
  const L = FLOW_LINES[s.line];
  const link = s.screen
    ? `<a class="btn btn--primary" href="#/${s.screen}">Open ${SCREEN_NAME[s.screen]} ${ICON.arrow}</a>`
    : `<p class="muted">Not drawn in this prototype; the five core screens are.</p>`;
  return `<h2><span class="stop-card__num" style="border-color:${L.color}">${s.n}</span>${esc(s.label)}</h2>
    <dl><div><dt>Line</dt><dd>${L.name}, ${L.note}</dd></div><div><dt>The user</dt><dd>${esc(s.does)}</dd></div><div><dt>They see</dt><dd>${esc(s.sees)}</dd></div></dl>
    ${link}`;
}

function renderFlow() {
  const sel = FLOW.stations.find((s) => s.id === STATE.flowSel);
  const group = (line) => FLOW.stations.filter((s) => s.line === line);
  const col = (line) => `<section><h2><i style="background:${FLOW_LINES[line].color}"></i>${FLOW_LINES[line].name}<small>${FLOW_LINES[line].note}</small></h2>
      <ol>${group(line).map((s) => `<li><button data-flowpick="${s.id}"><b>${s.n}</b><span><b>${esc(s.label)}</b><br><span class="step-does">${esc(s.does)}</span></span></button></li>`).join("")}</ol>
    </section>`;

  const html = `
    ${head("How Varity is used", "The planned user flow as a transit map: a first ride taken once, a daily loop ridden every morning, and two explore stops to visit any time. Select a station to see what the user does there. Google sign-in and Google Tasks (steps 2 and 8) are not built: Varity offers a plan download and a calendar file instead.")}
    <div class="flow">
      <div>
        <div class="diagram">${flowSVG()}</div>
        <p class="swipe-hint">Swipe the map sideways to see every station.</p>
        <div class="legend">
          ${Object.values(FLOW_LINES).map((l) => `<span><i class="sw-line" style="background:${l.color}"></i>${l.name} (${l.note})</span>`).join("")}
          <span><i class="sw-dot sw-ring"></i>Interchange: where lines meet</span>
        </div>
      </div>
    </div>
    <div class="flow-below">
      <aside class="stop-card" aria-live="polite" data-card>${stopCard(sel)}</aside>
      <div class="steps">${col("ride")}${col("loop")}${col("explore")}</div>
    </div>`;

  const bind = (root) => {
    const select = (id) => {
      STATE.flowSel = id;
      root.querySelector("[data-card]").innerHTML = stopCard(FLOW.stations.find((s) => s.id === id));
      root.querySelectorAll("[data-flowpick]").forEach((b) => b.classList.toggle("is-on", b.dataset.flowpick === id));
      root.querySelectorAll(".stn[data-flow]").forEach((g) => g.classList.toggle("is-sel", g.dataset.flow === id));
    };
    bindLineLighting(root.querySelector(".flow"));
    root.querySelectorAll(".stn[data-flow]").forEach((g) => {
      g.addEventListener("click", () => select(g.dataset.flow));
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(g.dataset.flow); } });
    });
    root.querySelectorAll("[data-flowpick]").forEach((b) => b.addEventListener("click", () => select(b.dataset.flowpick)));
    select(STATE.flowSel);
  };
  return { html, bind };
}
