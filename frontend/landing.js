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

/* The train, seen from above (a roof plan), nose to the right: three articulated cars (landing.css moves each
   one along the line separately, so they bend round corners), gangway connectors, darker centre roof strip,
   two AC units per car, pantograph on the middle car, long tapered Shinkansen-style nose with a windscreen
   band and a yellow headlight. Fixed colours (it is a drawing). Each symbol is centred on its car; the
   <use> x puts that centre on the path point, offset-rotate turns it along the line. */
const TRAIN_SYMBOL = `
<symbol id="lp-lead" viewBox="107 0 69 24">
  <g stroke="#121212" stroke-width="2.5" stroke-linejoin="round" fill="#fff"><path d="M109.5 5.5 Q109.5 1.5 113.5 1.5 H134 C152 1.5 167 6 173 10 Q175 12 173 14 C167 18 152 22.5 134 22.5 H113.5 Q109.5 22.5 109.5 18.5 Z"/></g>
  <rect x="114" y="8" width="28" height="8" fill="#c4cad3"/>
  <g fill="#fff" stroke="#121212" stroke-width="1.2"><rect x="117" y="9" width="9" height="6"/><rect x="129" y="9" width="9" height="6"/></g>
  <path d="M146 8 C155 8.5 161 10.5 165 12 C161 13.5 155 15.5 146 16 Q148 12 146 8 Z" fill="#121212"/>
  <g stroke="#0039a6" stroke-width="2" fill="none" stroke-linecap="round"><path d="M113 4.5 H134 C144 4.5 152 6 157 8"/><path d="M113 19.5 H134 C144 19.5 152 18 157 16"/></g>
  <circle cx="172.5" cy="12" r="2.2" fill="#fccc0a" stroke="#121212" stroke-width="1"/>
</symbol>
<symbol id="lp-mid" viewBox="54 0 57 24">
  <rect x="102" y="7" width="8" height="10" fill="#121212"/>
  <rect x="55.5" y="1.5" width="47" height="21" rx="5" fill="#fff" stroke="#121212" stroke-width="2.5" stroke-linejoin="round"/>
  <rect x="60" y="8" width="38" height="8" fill="#c4cad3"/>
  <g fill="#fff" stroke="#121212" stroke-width="1.2"><rect x="64" y="9" width="9" height="6"/><rect x="85" y="9" width="9" height="6"/></g>
  <path d="M74 12 L79 6 L84 12 L79 18 Z M74 12 H84" stroke="#121212" stroke-width="1.6" fill="none" stroke-linejoin="round"/>
  <path d="M59 4.5 H99 M59 19.5 H99" stroke="#0039a6" stroke-width="2" fill="none" stroke-linecap="round"/>
</symbol>
<symbol id="lp-tail" viewBox="0 0 57 24">
  <rect x="48" y="7" width="8" height="10" fill="#121212"/>
  <rect x="1.5" y="1.5" width="47" height="21" rx="5" fill="#fff" stroke="#121212" stroke-width="2.5" stroke-linejoin="round"/>
  <rect x="6" y="8" width="38" height="8" fill="#c4cad3"/>
  <g fill="#fff" stroke="#121212" stroke-width="1.2"><rect x="10" y="9" width="9" height="6"/><rect x="31" y="9" width="9" height="6"/></g>
  <path d="M5 4.5 H45 M5 19.5 H45" stroke="#0039a6" stroke-width="2" fill="none" stroke-linecap="round"/>
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
    <g class="lp-train">
      <g class="lp-car" style="--lag:113px"><use href="#lp-tail" x="-28.5" y="-12" width="57" height="24"/></g>
      <g class="lp-car" style="--lag:59px"><use href="#lp-mid" x="-28.5" y="-12" width="57" height="24"/></g>
      <g class="lp-car" style="--lag:0px"><use href="#lp-lead" x="-34.5" y="-12" width="69" height="24"/></g>
    </g>
  </svg>`;
}

function renderLanding() {
  const stops = LINE_STOPS.map((s, i) => `<li class="s${i + 1}"><b>${s.name}</b><p>${s.text}</p></li>`).join("");
  const html = `<div class="lp">
    <section class="lp-hero" aria-labelledby="lp-h1">
      <h1 id="lp-h1">From CV to hired, one stop at a time.</h1>
      <p class="lp-sub">A personal route from the skills you have to the job you want, with free resources where we have them.</p>
      <div class="lp-cta">
        <button class="btn btn--primary" type="button" data-global="start">Get started</button>
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
      <h2 class="sec" id="lp-board-h"><span>Departures: role demand <span class="synthetic real lp-chip">Real data</span></span> <small data-asof></small></h2>
      <p class="lp-note">Demand trend, last 12 months vs the 12 before</p>
      <div class="lp-rows" role="table" aria-label="Role demand trend">
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
  return { html, bind: (root) => {
    // Without @property the ride cannot interpolate: park everything instead of letting it jump.
    if (typeof CSSPropertyRule === "undefined") root.querySelector(".lp-map").classList.add("lp-static");
    return bindBoard(root);
  } };
}

/* "Departures: role demand": role demand trend from GET /api/roles/forecast. Stays hidden if it fails. */
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

/* The landing's How Varity works tab: the flow map (renamed) followed by the How page, ending on Get started. */
function renderHowTab() {
  const flow = renderFlow(), how = renderHow();
  const html = `${flow.html.replace("How Varity is used", "How Varity works")}${how.html.replace("<h1>How Varity works</h1>", "<h2 class=\"sec\">Under the hood</h2>")}
    <div class="hw-cta"><p>Sign in with Google, add your CV, and Varity plans your route.</p><button class="btn btn--primary" type="button" data-global="start">Get started</button></div>`;
  return { html, bind: (root) => { flow.bind(root); how.bind(root); } };
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
