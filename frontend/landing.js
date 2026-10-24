/* Varity: the landing screen (#/ and #/home) and "How Varity works" (#/how).
   Static copy is plain text; everything fetched is written with textContent. No numbers are typed here:
   the only figures shown come from the API. The map geometry below is drawing, not data. */

/* Route map. Geometry is in the 1040 x 350 viewBox; the train's stop distances (px along LINE_PATH) are in
   landing.css (@keyframes lp-ride) and must be kept in step with it. Stations sit on the flat runs. */
const LINE_PATH = "M8 290 H360 L440 210 H640 L720 130 H985";
const LINE_STOPS = [
  { name: "Upload your CV", text: "We find each skill and show the line in your CV that proves it.", x: 125, y: 290, ly: 328 },
  { name: "See your match", text: "Your skills against what tech job posts ask for, as a match %.", x: 300, y: 290, ly: 328 },
  { name: "See your skills gap", text: "The exact gap between you and each role.", x: 560, y: 210, ly: 176 },
  { name: "Get your plan", text: "Short daily tasks with free resources, in the right order.", x: 840, y: 130, ly: 170 },
  { name: "Hired", text: "Your route ends at the job you chose.", x: 985, y: 130, ly: 198 },
];

/* The train. Side view, nose to the right: sloped wedge nose, headlight, windshield, windows, doors,
   three cars, pantograph, wheels, blue stripe. Fixed colours (it is a drawing). Never rotated. */
const TRAIN_SYMBOL = `<symbol id="lp-train" viewBox="0 -2 320 58">
  <g stroke="#121212" stroke-width="4" stroke-linejoin="round" fill="#fff">
    <rect x="4" y="8" width="92" height="36" rx="5"/><rect x="102" y="8" width="92" height="36" rx="5"/>
    <path d="M200 8 H262 L308 30 Q316 34 316 40 V44 H200 Z"/>
  </g>
  <g fill="#121212"><rect x="95" y="20" width="8" height="18"/><rect x="193" y="20" width="8" height="18"/></g>
  <g stroke="#121212" stroke-width="10" fill="none" stroke-dasharray="13 2"><path d="M10 21 H90"/><path d="M108 21 H188"/><path d="M206 21 H254"/></g>
  <g fill="#fff" stroke="#121212" stroke-width="2.5"><rect x="30" y="13" width="11" height="29" rx="1"/><rect x="60" y="13" width="11" height="29" rx="1"/><rect x="128" y="13" width="11" height="29" rx="1"/><rect x="158" y="13" width="11" height="29" rx="1"/><rect x="226" y="13" width="11" height="29" rx="1"/></g>
  <path d="M262 12 L295 27 H262 Z" fill="#121212"/>
  <circle cx="311" cy="37" r="3" fill="#fccc0a" stroke="#121212" stroke-width="1.5"/>
  <path d="M5 35 H95 M103 35 H193 M201 35 H310" stroke="#0039a6" stroke-width="5" fill="none"/>
  <path d="M132 8 L148 0 L164 8 M141 0 H155" stroke="#121212" stroke-width="3" fill="none" stroke-linejoin="round"/>
  <g fill="#121212"><rect x="12" y="44" width="28" height="3"/><rect x="62" y="44" width="28" height="3"/><rect x="110" y="44" width="28" height="3"/><rect x="160" y="44" width="28" height="3"/><rect x="208" y="44" width="28" height="3"/><rect x="274" y="44" width="28" height="3"/>
    <circle cx="19" cy="49" r="4"/><circle cx="33" cy="49" r="4"/><circle cx="69" cy="49" r="4"/><circle cx="83" cy="49" r="4"/><circle cx="117" cy="49" r="4"/><circle cx="131" cy="49" r="4"/><circle cx="167" cy="49" r="4"/><circle cx="181" cy="49" r="4"/><circle cx="215" cy="49" r="4"/><circle cx="229" cy="49" r="4"/><circle cx="281" cy="49" r="4"/><circle cx="295" cy="49" r="4"/></g>
</symbol>`;

function lineMapSvg() {
  const st = LINE_STOPS, last = st.length - 1;
  const halo = st.map((s, i) => (i === last
    ? `<rect class="lp-halo s${i + 1}" x="${s.x - 23}" y="${s.y - 44}" width="46" height="88" rx="23"/>`
    : `<circle class="lp-halo s${i + 1}" cx="${s.x}" cy="${s.y}" r="24"/>`)).join("");
  const dots = st.map((s, i) => (i === last
    ? `<rect class="lp-cap" x="${s.x - 11}" y="${s.y - 34}" width="22" height="68" rx="11"/>`
    : `<circle class="lp-dot" cx="${s.x}" cy="${s.y}" r="10"/>`)).join("");
  // Each label is drawn twice and cross-faded (opacity only) so the current stop reads bold without reflow.
  const labels = st.map((s, i) => `<text class="lp-lbl lp-lbl--n s${i + 1}" x="${s.x}" y="${s.ly}">${s.name}</text><text class="lp-lbl lp-lbl--b s${i + 1}" x="${s.x}" y="${s.ly}">${s.name}</text>`).join("");
  const b = st[2];  // the grey dotted branch leaves the third stop
  return `<svg viewBox="0 76 1040 274" aria-hidden="true" focusable="false">
    <defs>${TRAIN_SYMBOL}</defs>
    <path class="lp-branch" d="M${b.x} ${b.y} V${b.y + 30} L${b.x + 40} ${b.y + 70} H${b.x + 140}"/>
    <circle class="lp-dot" cx="${b.x + 140}" cy="${b.y + 70}" r="7" style="stroke-width:3"/>
    <text class="lp-lbl lp-lbl--soft" x="${b.x + 156}" y="${b.y + 75}">Other roles</text>
    <path class="lp-line" d="${LINE_PATH}"/>
    ${halo}${dots}${labels}
    <g class="lp-train"><use href="#lp-train" x="-100" y="-32.3" width="150" height="27.2"/></g>
  </svg>`;
}

function renderLanding() {
  const stops = LINE_STOPS.map((s, i) => `<li class="s${i + 1}"><b>${s.name}</b><p>${s.text}</p></li>`).join("");
  const html = `<div class="lp">
    <section class="lp-hero" aria-labelledby="lp-h1">
      <h1 id="lp-h1">From CV to hired, one stop at a time.</h1>
      <p class="lp-sub">A personal route from the skills you have to the job you want, with free resources at every stop.</p>
      <div class="lp-cta">
        <a class="btn btn--primary" href="#/profile">Find my jobs</a>
        <a class="lp-alt" href="#/profile">Not ready? Try an example</a>
      </div>
    </section>

    <section aria-labelledby="lp-route-h">
      <h2 class="sec lp-nobar" id="lp-route-h">Your route, five stops</h2>
      <div class="lp-map" role="region" aria-label="Route map" tabindex="0">${lineMapSvg()}</div>
      <p class="lp-hint">Swipe to follow the line.</p>
      <ol class="lp-stops">${stops}</ol>
    </section>

    <section aria-labelledby="lp-get-h">
      <h2 class="sec lp-nobar" id="lp-get-h">What you get</h2>
      <ul class="lp-get">
        <li><b>Your job matches, ranked</b></li>
        <li><b>Your exact skills gap</b></li>
        <li><b>A daily plan with free resources</b></li>
      </ul>
    </section>

    <section id="lp-board" aria-labelledby="lp-board-h" hidden>
      <h2 class="sec" id="lp-board-h"><span>Departures this month <span class="synthetic real lp-chip">Real data</span></span> <small data-asof></small></h2>
      <div class="lp-rows" role="table" aria-label="Role demand this month">
        <div class="lp-row lp-row--head" role="row"><span role="columnheader"></span><span role="columnheader">Role</span><span role="columnheader">Demand</span><span role="columnheader">As of</span></div>
      </div>
      <p class="lp-note">Share of Hacker News hiring posts; a sample of tech hiring, not a count of jobs.</p>
    </section>

    <section aria-labelledby="lp-more-h">
      <h2 class="sec lp-nobar" id="lp-more-h">How Varity works</h2>
      <div class="lp-more">
        <a href="#/how">Which skills are rising? <span aria-hidden="true">→</span></a>
        <a href="#/how">Can you trust the numbers? <span aria-hidden="true">→</span></a>
      </div>
    </section>

    <p class="lp-end"><strong>Supports your judgement; it does not replace it.</strong> <a href="#/how">How Varity works</a></p>
  </div>`;
  return { html, bind: bindBoard };
}

/* "Departures this month": role demand trend from GET /api/roles/forecast. Stays hidden if it fails. */
async function bindBoard(root) {
  try {
    const d = await api("/api/roles/forecast");
    if (!root.isConnected || !d || !d.roles) return;
    const rows = Object.values(d.roles).filter((r) => r && r.name && r.trend && r.trend.label);
    if (!rows.length) return;
    const [y, mo] = String(d.as_of || "").split("-").map(Number);
    const asOf = y && mo ? new Date(Date.UTC(y, mo - 1, 1)).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" }) : String(d.as_of || "");
    const host = root.querySelector(".lp-rows");
    for (const r of rows) {
      const row = document.createElement("div");
      row.className = "lp-row";
      row.setAttribute("role", "row");
      const bullet = document.createElement("span");
      bullet.className = "bullet bullet--sm";
      bullet.setAttribute("aria-hidden", "true");
      bullet.textContent = r.name.charAt(0);
      const name = document.createElement("span");
      name.className = "lp-role";
      name.textContent = r.name;
      const trend = document.createElement("span");
      trend.className = "lp-trend " + (r.trend.label === "Rising" || r.trend.label === "Falling" ? "lp-trend--" + r.trend.label : "lp-trend--flat");
      trend.textContent = r.trend.label;
      const when = document.createElement("span");
      when.className = "lp-when";
      when.textContent = asOf;
      for (const c of [bullet, name, trend, when]) { c.setAttribute("role", "cell"); row.appendChild(c); }
      host.appendChild(row);
    }
    root.querySelector("[data-asof]").textContent = asOf ? "As of " + asOf : "";
    root.querySelector("#lp-board").hidden = false;
  } catch (e) { /* the board stays hidden */ }
}

/* ── How Varity works ─────────────────────────────────────────── */
/* Plain words for the forecast model ids the evidence file may carry. */
const MODEL_WORDS = { naive3: "a 3-month average, carried forward", naive: "last month, carried forward" };

function renderHow() {
  const html = `<div class="hw">
    <h1>How Varity works</h1>
    <p class="hw-lede">Varity matches your CV to tech roles using real job posts, forecasts which skills and roles are rising, and builds you a learning route. Every number comes from a dated, public source.</p>

    <section aria-labelledby="hw-j">
      <h2 class="sec" id="hw-j">The journey</h2>
      <ol class="hw-journey">
        <li><h3>Your CV</h3><p>An AI points at each skill in your CV, and code checks that the quote is really there.</p></li>
        <li><h3>Your matches</h3><p>Your skills are compared with what job posts ask for, and weighed by how much each role is in demand.</p></li>
        <li><h3>Your skills gap</h3><p>The core skills for a role that you do not show yet.</p></li>
        <li><h3>Your plan</h3><p>Ordered stages, short daily tasks and free resources.</p></li>
      </ol>
    </section>

    <section aria-labelledby="hw-c">
      <h2 class="sec" id="hw-c"><span>Look under the hood</span> <span class="synthetic real lp-chip">Real data</span></h2>
      <div class="hw-cards">
        <article class="hw-card" aria-labelledby="hw-c1">
          <h3 id="hw-c1">Which skills are rising?</h3>
          <p>A map of the tech skills we track by how often job posts ask for them and how fast that is changing. A colour means a statistical test found a real change.</p>
          <a class="btn btn--primary" href="#/radar">Open the skills radar</a>
          <ul class="hw-live" data-radar aria-label="Skills with a tested change" hidden></ul>
        </article>
        <article class="hw-card" aria-labelledby="hw-c2">
          <h3 id="hw-c2">Can you trust the numbers?</h3>
          <p>We replayed past years to test the forecast, cross-checked AI-exposure data against outside sources, and list every source with its date.</p>
          <a class="btn" href="#/method">See the method</a>
          <p class="hw-fact" data-fact hidden></p>
        </article>
      </div>
    </section>

    <section aria-labelledby="hw-n">
      <h2 class="sec" id="hw-n">What Varity does not do</h2>
      <ul class="hw-not">
        <li>It does not guarantee a job.</li>
        <li>Its forecasts are estimates, and they come with ranges.</li>
        <li>In this prototype it reads only synthetic or public data.</li>
        <li>It supports your judgement and does not replace it.</li>
      </ul>
    </section>

    <p class="hw-back"><a href="#/">Back to the start</a></p>
  </div>`;
  return { html, bind: bindHow };
}

function bindHow(root) {
  api("/api/skills/radar").then((d) => {
    const pts = (d && d.points) || [];
    const movers = pts.filter((p) => p.trend_label === "Rising" || p.trend_label === "Falling").slice(0, 6);
    const ul = root.querySelector("[data-radar]");
    if (!movers.length || !root.isConnected) return;
    const head = document.createElement("li");
    head.textContent = `${pts.length} skills on the map. Tested movers:`;
    ul.appendChild(head);
    for (const p of movers) {
      const li = document.createElement("li"), n = document.createElement("span"), t = document.createElement("span");
      n.textContent = p.skill;
      t.textContent = p.trend_label;
      t.className = "hw-t " + (p.trend_label === "Rising" ? "hw-rise" : "hw-fall");
      li.append(n, t);
      ul.appendChild(li);
    }
    ul.hidden = false;
  }).catch(() => {});

  api("/api/evidence").then((d) => {
    const s = d && d.backtests && d.backtests.skills, c = s && s.coverage;
    if (!c || typeof c.test_h12 !== "number" || !root.isConnected) return;
    const model = MODEL_WORDS[s.chosenModel];
    const p = root.querySelector("[data-fact]");
    p.textContent = `In the replay, the ${c.label} held ${Math.round(c.test_h12 * 100)}% of real values 12 months ahead.`
      + (model ? ` Forecast model: ${model}.` : "") + (d.asOf ? ` As of ${d.asOf}.` : "");
    p.hidden = false;
  }).catch(() => {});
}
