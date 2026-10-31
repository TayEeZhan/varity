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

/* Story type → line letter and colour (styles.css .cat--*). The key sits above the board so the letters are explained first. */
const CATS = [{ k: "S", name: "Security", match: (c) => c === "Security incident" }, { k: "R", name: "Research", match: (c) => c === "Research" },
  { k: "P", name: "Products", match: (c) => c === "Product feature" }, { k: "M", name: "Model releases", match: (c) => c === "Model release" },
  { k: "A", name: "APIs & policy", match: (c) => /API|Policy/.test(c) }];
const catOf = (c) => (CATS.find((x) => x.match(c)) || CATS[1]).k;
const catBullet = (c) => `<i class="cat cat--${catOf(c)}" aria-hidden="true">${catOf(c)}</i>`;

/* Highest score first; the rank is the place in that order, kept when a filter hides some stories. */
const rankedStories = () => STORIES.slice().sort((a, b) => b.score - a.score).map((s, i) => ({ ...s, place: i + 1 }));

function noticesHTML() {
  const f = FILTERS.find((x) => x.id === STATE.filter);
  const list = rankedStories().filter(f.match);
  if (!list.length) {
    return `<p class="empty">No ${f.label.toLowerCase()} in today's top 10. Lower-ranked stories are still tracked; this view only shows what is worth your time today.</p>`;
  }
  return list.map((s) => `<article class="brow">
      <div class="rank">${s.place}</div>
      <div>${catBullet(s.category)}</div>
      <div>
        <div class="t"><a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener">${esc(s.title)}</a></div>
        <div class="m">${esc(s.category)} · ${s.sources.map(esc).join(" + ")} · first seen ${esc(s.date)}</div>
        <div class="m"><b>Ranks here because:</b> ${s.why.map(esc).join(" · ")}</div>
      </div>
      <div class="score r">${s.score.toFixed(1)}<small>score</small></div>
    </article>`).join("");
}

function renderSignals() {
  const skills = SKILLS.slice().sort((a, b) => b.momentum - a.momentum);
  // momentum = (this week − usual) ÷ usual, with usual floored at 1; under 1 mention a week a % would mislead, so say "New".
  const change = (s, usual) => usual < 1 ? (s.weekly[4] ? "New" : "–")
    : `${s.momentum >= 0 ? "+" : "−"}${Math.round(Math.abs(s.momentum) * 100).toLocaleString()}%`;
  // Green = more than usual, red = fewer; "New" counts as up.
  const dir = (s, usual) => (usual < 1 ? s.weekly[4] > 0 : s.momentum > 0) ? "up" : usual >= 1 && s.momentum < 0 ? "down" : "flat";
  const rows = skills.map((s) => {
    const usual = s.weekly.slice(0, 4).reduce((a, b) => a + b, 0) / 4;
    return `<div class="brow" role="row"><div class="t" role="cell">${esc(s.skill)}</div><div class="num" role="cell">${s.weekly[4]}</div><div class="num usual" role="cell">${usual.toFixed(1)}</div><div role="cell"><span class="flap flap--${dir(s, usual)}">${change(s, usual)}</span></div></div>`;
  }).join("");

  const html = `
    ${head("Signals", "What moved in AI and dev tooling this week, ranked by a fixed formula from dated, named sources. Every rank shows its reasons.", (STATE.signalsLive ? real : snapshot)(`${STATE.signalsLive ? "Real data" : "Offline snapshot"} · ${SIGNAL_RUN.storyCount} stories · ${SIGNAL_RUN.generatedAt}`))}
    <div class="signals-grid">
      <section>
        <div class="board board--skills" role="table" aria-labelledby="sm-h">
          <div class="board__title"><h2 id="sm-h">Skills in the news</h2><small>this week vs a usual week</small></div>
          <div class="brow brow--head" role="row"><span role="columnheader">Skill</span><span role="columnheader">Now</span><span class="usual" role="columnheader">Usual</span><span role="columnheader">Change</span></div>
          ${rows}
        </div>
        <p class="board-foot">Counts are news mentions. "Usual" is the average of the 4 weeks before this one. "Change" compares this week with that average: green is up, red is down. "New" means the skill had under 1 mention a week before, so a percentage would mislead.</p>
      </section>
      <section aria-labelledby="sn-h">
        <p class="cat-key"><b>Story type:</b>${CATS.map((c) => `<span><i class="cat cat--${c.k}" aria-hidden="true">${c.k}</i>${esc(c.name)}</span>`).join("")}</p>
        <div class="filters" role="group" aria-label="Filter stories">
          ${FILTERS.map((f) => `<button class="filter" data-filter="${f.id}" aria-pressed="${STATE.filter === f.id}">${f.label}</button>`).join("")}
        </div>
        <div class="board board--news">
          <div class="board__title"><h2 id="sn-h">Top AI news</h2><small>top ${STORIES.length} of ${SIGNAL_RUN.storyCount} · highest score first</small></div>
          <div class="brow brow--head"><span>#</span><span></span><span>Story</span><span class="r">Score</span></div>
          <div data-notices>${noticesHTML()}</div>
        </div>
        <p class="board-foot">Each score comes from the trend layer's fixed formula; "Ranks here because" lists what raised it. Ranked by ${esc(SIGNAL_RUN.rankedBy || "deterministic formula")}.</p>
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
const pct = (v) => `${(v * 100).toFixed(1)}%`;
// " · updated <date> · <n> posts so far" when the backend served the daily-refresh snapshot.
const refreshedText = () => {
  const m = STATE.forecastMeta || {};
  if (m.source !== "daily refresh" || !m.fetched_at) return "";
  return ` · updated ${String(m.fetched_at).slice(0, 10)}${m.posts_after ? ` · ${m.posts_after} posts so far this month` : ""}`;
};

// Track record and the open-month weight from the daily job (engine/ledger.py, engine/forecast.nowcast_y).
const trackText = (tr) => {
  if (!tr || !tr.runs) return "Not recorded yet: the daily job writes every forecast to a ledger from its first run.";
  const graded = tr.forecasts_graded
    ? `${tr.forecasts_in_band} of ${tr.forecasts_graded} past forecasts landed in the range.`
    : `None can be checked yet: the first one is due in ${esc(tr.next_grading_month || "12 months")}.`;
  return `${tr.runs} daily runs recorded since ${esc(tr.first_run)}. ${graded}`;
};
const nowcastText = (nc) => !nc || !nc.posts_this_month ? "This month is complete."
  : nc.weight == null ? `This month has ${nc.posts_this_month} posts so far. After about two weeks a thread is nearly complete, so it counts in full.`
  : `This month has ${nc.posts_this_month} posts so far, so it counts ${Math.round(nc.weight * 100)}% and last month the rest. The weight is chosen by a backtest on past threads cut at day 1, 3, 7 and 14.`;

// Claude labels first; the title rules are the backup (engine/llm_labels.py). Every Claude label has a checked quote.
const labellerText = (fc) => {
  const lab = String(fc.labeller || "title regex"), chk = fc.label_check || {};
  if (!/^(claude|krackeddevs\/)/.test(lab)) {
    const why = lab.includes("drifted") ? " Claude's labels drifted from the usual today, so the rules counted this month."
      : chk.error ? " Claude could not be reached today, so the rules counted this month." : "";
    return `Fixed title rules decide which roles a post names.${why} Code does every count and forecast.`;
  }
  const backup = chk.regex_posts ? ` The title rules covered ${chk.regex_posts} posts Claude did not label; Claude tries them again tomorrow.` : "";
  const who = lab.startsWith("krackeddevs/") ? `The AI model ${esc(lab.split(",")[0])}` : "Claude";
  return `${who} reads each post and names its roles, quoting the words that show it; code checks each quote is really in the post.${backup} Code does every count and forecast.`;
};
const newRolesText = (nr, excluded) => {
  const auto = (excluded || []).filter((r) => /Found automatically/.test(r.reason || ""));
  const added = auto.length ? `Found automatically and tracked: ${auto.map((r) => esc(r.name)).join(", ")}. ` : "";
  if (!nr) return added + "Each day the job looks for job titles no role covers yet.";
  const waiting = nr.waiting_for_review ? `${nr.waiting_for_review} titles are waiting for Claude's review.` : "No new titles are waiting.";
  return `${added}${waiting} Claude adds a role only with three quotes from real posts.`;
};

function renderForecast() {
  const changes = (FORECAST.track_record || {}).changes_since_last_run || {};
  const roles = Object.entries(FORECAST.roles || {}).map(([id, r]) => ({ id, ...r }));
  const ok = roles.filter((r) => r.status === "ok" && r.share_now && r.forecast_moderate && r.trend)
    .sort((a, b) => (TREND_ORDER[a.trend.label] ?? 1) - (TREND_ORDER[b.trend.label] ?? 1) || b.share_now.value - a.share_now.value);
  const skipped = [...roles.filter((r) => !ok.includes(r)).map((r) => ({ name: r.name, reason: r.note || "No forecast for this month" })),
    ...(FORECAST.excluded_roles || []).map((r) => ({ name: r.name, reason: r.reason }))];
  const band = FORECAST.interval ? FORECAST.interval.label : "range";
  const hnLinks = (r) => (r.sources || []).filter((s) => /^https?:\/\//i.test(s.url))
    .map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.date)}</a>`).join(" · ");
  const PLATE = { Rising: ["up", "Growing"], Falling: ["down", "Shrinking"] };

  // One departure-board row per role: the evidence line under the name keeps every number the old chart showed.
  const rowHTML = (r) => {
    const f = r.forecast_moderate, t = r.trend, [cls, word] = PLATE[t.label] || ["flat", "Steady"];
    const fast = r.forecast_fast && r.forecast_fast.value_12m != null ? r.forecast_fast.value_12m : null;
    const ch = changes[r.id];
    return `<div class="brow">
      <div><div class="t">${esc(r.name)}</div>
        <div class="m"><b>${t.mentions_last12}</b> posts in the last 12 months vs <b>${t.mentions_prev12}</b> the 12 before (${pct(t.share_last12)} vs ${pct(t.share_prev12)} of posts).${r.declining ? " <b>Declining in this sample:</b> falling, and most of its skill weight is in falling skills." : ""}${fast != null ? ` If AI speeds up, in 12 months: ${pct(fast)} (estimate).` : ""}${ch ? ` Since ${esc(ch.since)}: ${pct(ch.share_now_from)} → ${pct(ch.share_now_to)}.` : ""} HN threads: ${hnLinks(r) || "none"}</div></div>
      <div class="num t">${pct(r.share_now.value)}</div>
      <div class="num hide-sm"><span class="t">${pct(f.value_12m)}</span><div class="m">${pct(f.low)}–${pct(f.high)}</div></div>
      <div><span class="plate plate--${cls}" title="${esc(t.label)}: last 12 months against the 12 before">${word}</span></div>
    </div>`;
  };

  const html = `
    ${head("Job forecast", "How demand for tech roles may change over the next 12 months, from the share of Hacker News “Who is hiring?” posts that name each role. Ranges are estimates, not counts. Two scenarios exist for routes: the forecast here is the expected one; the “If AI speeds up” scenario is shown on CV &amp; routes, also as an estimate.")}
    <div class="fc-bar-head">
      ${(STATE.forecastLive ? real : snapshot)(`${STATE.forecastLive ? "Real data" : "Offline snapshot"} · HN hiring posts · as of ${(FORECAST.as_of || "?") + (FORECAST.partial_month ? " (month in progress)" : "")}${refreshedText()}`)}
    </div>
    <section class="board board--roles" aria-labelledby="fc-h">
      <div class="board__title"><h2 id="fc-h">Jobs: the next 12 months</h2><small>share of hiring posts · estimate with an ${esc(band)}</small></div>
      <div class="brow brow--head"><span>Job</span><span>Now</span><span class="hide-sm">In 12 months</span><span>Trend</span></div>
      ${ok.map(rowHTML).join("") || `<p class="empty">No role forecast yet. Run engine/role_forecast.py.</p>`}
    </section>
    <p class="board-foot">Now = share of the last 3 months of posts. In 12 months = the expected value, with the ${esc(band)} below it. Growing / Steady / Shrinking = the last 12 months against the 12 before; Steady means the difference could be noise.</p>
    ${skipped.length ? `<p class="method">Left out: ${skipped.map((s) => `${esc(s.name)} (${esc(s.reason)})`).join("; ")}.</p>` : ""}
    <div class="fc-note">
      <div><h3>What the numbers mean</h3><p>Share of monthly HN hiring posts that name the role (last 3 months), and where that share is expected to be in 12 months. HN is a sample of tech hiring, not a count of jobs.</p></div>
      <div><h3>Rising or falling</h3><p>The trend label compares the last 12 months with the 12 before. It is observed, not forecast. “No clear change” means the difference could be noise.</p></div>
      <div><h3>Use it as one input</h3><p>The forecast shapes which routes Varity suggests. It does not decide for you: you pick the route.</p></div>
      <div><h3>The month in progress</h3><p>${nowcastText(FORECAST.nowcast)}</p></div>
      <div><h3>Track record</h3><p>${trackText(FORECAST.track_record)}</p></div>
      <div><h3>Who reads the posts</h3><p>${labellerText(FORECAST)}</p></div>
      <div><h3>New roles</h3><p>${newRolesText(FORECAST.new_roles, FORECAST.excluded_roles)}</p></div>
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
    : `<p class="muted">Not drawn in this prototype. Varity has eight pages, listed in the top bar.</p>`;
  return `<h2><span class="stop-card__num" style="border-color:${L.color}">${s.n}</span>${esc(s.label)}</h2>
    <dl><div><dt>Line</dt><dd>${L.name}, ${L.note}</dd></div><div><dt>The user</dt><dd>${esc(s.does)}</dd></div><div><dt>They see</dt><dd>${esc(s.sees)}</dd></div></dl>
    ${s.built === false ? `<p class="muted">Not built yet.</p>` : ""}
    ${link}`;
}

function renderFlow() {
  const sel = FLOW.stations.find((s) => s.id === STATE.flowSel);
  const group = (line) => FLOW.stations.filter((s) => s.line === line);
  const col = (line) => `<section><h2><i style="background:${FLOW_LINES[line].color}"></i>${FLOW_LINES[line].name}<small>${FLOW_LINES[line].note}</small></h2>
      <ol>${group(line).map((s) => `<li><button data-flowpick="${s.id}"><b>${s.n}</b><span><b>${esc(s.label)}</b><br><span class="step-does">${esc(s.does)}</span></span></button></li>`).join("")}</ol>
    </section>`;

  const html = `
    ${head("How Varity is used", "The planned user flow as a transit map: a first ride taken once, a daily loop ridden every morning, and two explore stops to visit any time. Select a station to see what the user does there. Not built yet: Google sign-in (step 2), syncing ticks back from Google Tasks (step 10), reordering or skipping stops (step 6) and the service-change band (step 12). Varity offers a plan download and a calendar file instead.")}
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
