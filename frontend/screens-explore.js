/* Screen renderers for Signals, Job forecast and the Flow map. Each returns { html, bind(root) }. */

/* ── Signals ───────────────────────────────────────────────────── */
const ROUTE_SKILLS = { "LLM application development": "var(--apps)", "AI security": "var(--guard)", "LLM serving and inference": "var(--serve)" };
const FILTERS = [
  { id: "all", label: "All", match: () => true },
  { id: "security", label: "Security", match: (s) => s.category === "Security incident" },
  { id: "research", label: "Research", match: (s) => s.category === "Research" },
  { id: "product", label: "Products", match: (s) => s.category === "Product feature" },
  { id: "policy", label: "APIs & policy", match: (s) => /API|Policy/.test(s.category) },
  { id: "models", label: "Model releases", match: (s) => s.category === "Model release" },
];

/* Story links come from crawled feeds: allow only http(s). */
const safeUrl = (u) => (/^https?:\/\//i.test(u) ? u : "#");

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
        <div class="notice__meta">${esc(s.category)} · ${s.sources.map(esc).join(" + ")} · first seen ${s.date}</div>
        <div class="notice__why">Ranks here because: ${s.why.map(esc).join(" · ")}</div>
      </div>
      <div class="notice__score">${s.score.toFixed(1)}<small>score</small><i style="width:${Math.round((s.score / max) * 100)}%"></i></div>
    </article>`).join("");
}

function renderSignals() {
  const skills = SKILLS.slice().sort((a, b) => b.momentum - a.momentum);
  const max = Math.max(...SKILLS.flatMap((s) => s.weekly));
  const rows = skills.map((s) => {
    const color = ROUTE_SKILLS[s.skill] || "#8a8b8e";
    const yours = ROUTE_SKILLS[s.skill] ? `<span class="yours">On your route</span>` : "";
    return `<tr><td>${esc(s.skill)}${yours}</td><td>${ridershipSVG(s.weekly, max, color)}</td><td class="num">${s.weekly[4]}</td><td class="num hide-sm">+${s.momentum.toFixed(1)}</td></tr>`;
  }).join("");

  const html = `
    ${head("Signals", "What moved in AI and dev tooling this week, ranked by a fixed formula from dated, named sources. Every rank shows its reasons.", real(`Real data · ${SIGNAL_RUN.storyCount} stories · ${SIGNAL_RUN.generatedAt}`))}
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
const AXIS = { min: -40, max: 60 };
const pos = (v) => ((Math.max(AXIS.min, Math.min(AXIS.max, v)) - AXIS.min) / (AXIS.max - AXIS.min)) * 100;
const signed = (v) => (v > 0 ? `+${v}%` : `${v}%`);

function placeRow(row, f) {
  const key = STATE.scenario;
  const other = key === "moderate" ? "fast" : "moderate";
  const v = f[key];
  const z = pos(0), p = pos(v);
  const bar = row.querySelector(".fc__bar");
  bar.style.left = `${Math.min(z, p)}%`;
  bar.style.width = `${Math.abs(p - z)}%`;
  bar.className = `fc__bar ${v >= 0 ? "up" : "down"}`;
  const band = row.querySelector(".fc__band");
  band.style.left = `${pos(v - f.band)}%`;
  band.style.width = `${pos(v + f.band) - pos(v - f.band)}%`;
  row.querySelector(".fc__other").style.left = `calc(${pos(f[other])}% - 1px)`;
  const val = row.querySelector(".fc__val");
  val.textContent = signed(v);
  val.className = `fc__val ${v >= 0 ? "up" : "down"}`;
  row.querySelector(".fc__track").setAttribute("aria-label", `${f.role}: ${signed(v)} under ${key} disruption, range ${signed(v - f.band)} to ${signed(v + f.band)}; ${signed(f[other])} under ${other} disruption`);
}

function renderForecast() {
  const ticks = [-40, -20, 0, 20, 40, 60];
  const isRoute = (f) => f.role === "LLM application engineer";
  const rowHTML = (f) => `<div class="fc__row${isRoute(f) ? " is-route" : ""}">
      <div class="fc__role">${esc(f.role)}${isRoute(f) ? "<small>Your route</small>" : ""}</div>
      <div class="fc__track" role="img"><span class="fc__zero" style="left:calc(${pos(0)}% - 1px)"></span><span class="fc__band"></span><span class="fc__bar"></span><span class="fc__other"></span></div>
      <div class="fc__val"></div>
      <div class="fc__drv">${f.real ? "<b>Signal</b> " : ""}${esc(f.driver)}</div>
    </div>`;

  const html = `
    ${head("Job forecast", "How demand for tech roles may change over the next 12 months, under a moderate and a fast AI-disruption scenario. Both are estimates.",
      `<div class="seg" role="group" aria-label="Scenario">
        <button data-scn="moderate" aria-pressed="${STATE.scenario === "moderate"}">Moderate disruption</button>
        <button data-scn="fast" aria-pressed="${STATE.scenario === "fast"}">Fast disruption</button>
      </div>`)}
    <div class="fc-bar-head">
      ${synth("Estimates · synthetic demo numbers")}
      <div class="fc-key">
        <span><i class="k-bar"></i>Selected scenario</span>
        <span><i class="k-tick"></i>Other scenario</span>
        <span><i class="k-band"></i>Uncertainty range</span>
      </div>
    </div>
    <section class="fc" aria-label="Projected change in job postings by role">
      <div class="fc__axis"><div>Role</div><div class="fc__ticks">${ticks.map((t) => `<span style="left:${pos(t)}%">${t === 0 ? "0" : signed(t)}</span>`).join("")}</div><div style="text-align:right">Change</div><div>Main driver</div></div>
      <div data-rows>${FORECAST.map(rowHTML).join("")}</div>
    </section>
    <div class="fc-note">
      <div><h3>What the numbers mean</h3><p>Projected change in job postings for each role over 12 months. In the real build they will be computed from dated job-posting data and the skill signals; here they are illustrative.</p></div>
      <div><h3>Where the drivers come from</h3><p>Rows marked Signal cite this week's real skill momentum. The others rest on stated assumptions, shown as such, so you can disagree with them.</p></div>
      <div><h3>Use it as one input</h3><p>The forecast shapes which routes Varity suggests. It does not decide for you: you pick the route.</p></div>
    </div>`;

  const bind = (root) => {
    const wrapEl = root.querySelector("[data-rows]");
    const rows = [...wrapEl.children];
    const apply = () => {
      FORECAST.forEach((f, i) => placeRow(rows[i], f));
      FORECAST.map((f, i) => ({ v: f[STATE.scenario], el: rows[i] }))
        .sort((a, b) => b.v - a.v)
        .forEach((r) => wrapEl.appendChild(r.el));
    };
    apply();
    root.querySelectorAll("[data-scn]").forEach((b) => b.addEventListener("click", () => {
      STATE.scenario = b.dataset.scn;
      root.querySelectorAll("[data-scn]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      apply();
    }));
  };
  return { html, bind };
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
    ${head("How Varity is used", "The user flow as a transit map: a first ride taken once, a daily loop ridden every morning, and two explore stops to visit any time. Select a station to see what the user does there.")}
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
