/* Screen renderers for Today, CV & routes, and Pathway. Each returns { html, bind(root) }. State lives in app.js (STATE). */

const ICON = {
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  out: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
  file: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7z"/><path d="M14 3v4h4M9 13h6M9 17h6"/></svg>',
  up: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M5 20h14"/></svg>',
  arrow: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
};

const bullet = (line, sm) => `<span class="bullet bullet--${line}${sm ? " bullet--sm" : ""}" title="${esc(LINES[line].name)}">${esc(LINES[line].letter)}</span>`;
const ext = (url, text) => `<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener">${esc(text)} ${ICON.out}</a>`;
const head = (title, lede, aside = "") => `<div class="screen-head"><div><h1>${title}</h1><p>${lede}</p></div>${aside}</div>`;
const real = (text) => `<span class="synthetic real">${esc(text)}</span>`;
const snapshot = (text) => `<span class="synthetic">${esc(text)}</span>`;

/* What a screen shows instead of the plan: loading, an error with a retry, or the empty state. "" = show the plan. */
function gate(kind) {
  const retry = `<button class="btn" type="button" data-global="retry">Try again</button>`;
  const problem = (msg) => `<p class="err" role="alert">${esc(msg)}</p><p>${retry}</p>`;
  if (STATE.loading) return `<p class="empty" role="status" aria-busy="true">Loading your profile and plan…</p>`;
  if (STATE.profileError) return problem(STATE.profileError);
  if (!STATE.saved) {
    return `<div class="empty"><h2>No profile yet</h2><p>Upload a CV or try an example profile.</p>
      <p><a class="btn btn--primary" href="#/profile">Go to CV &amp; routes</a></p></div>`;
  }
  if (STATE.suggestError) return problem(STATE.suggestError);
  if (STATE.planError) return problem(STATE.planError);
  if (!STATE.plan) {
    return `<div class="empty"><h2>No route yet</h2><p>${STATE.suggest && STATE.suggest.roles.length ? "Pick a route on" : "No role fits your saved skills well yet. Add skills on"} <a href="#/profile">CV &amp; routes</a>.</p></div>`;
  }
  return "";
}

const GOALS = [["climate_energy", "Climate and clean energy"], ["health", "Health and life sciences"], ["education", "Education"],
  ["financial_inclusion", "Financial inclusion"], ["agriculture_food", "Agriculture and food"], ["government_civic", "Government and civic tech"],
  ["accessibility", "Accessibility and disability inclusion"], ["cities_mobility", "Sustainable cities and mobility"]];
const goalPicker = () => `<p class="route-note"><label>I care about: <select data-goal aria-label="SDG goal">
  <option value="">Any goal</option>${GOALS.map(([id, n]) => `<option value="${id}"${STATE.goal === id ? " selected" : ""}>${esc(n)}</option>`).join("")}</select></label></p>`;
const scenarioToggle = () => `<div class="filters" role="group" aria-label="AI scenario">
    ${[["moderate", "Expected (estimate)"], ["fast", "If AI speeds up (estimate)"]].map(([v, label]) =>
      `<button class="filter" type="button" data-global="scenario" data-value="${v}" aria-pressed="${STATE.scenario === v}">${label}</button>`).join("")}
  </div>
  <p class="route-note">Expected = our forecast from job posts. If AI speeds up = what changes if AI takes over tasks faster. Both are estimates.</p>`;

const sdgAll = (tags) => tags.map((t) => `SDG ${t.target}: ${t.label}`).join(", ");
const sdgTag = (t) => `<span class="tag" title="Source: ${esc(t.source)}">SDG ${esc(t.target)}: ${esc(t.label)}</span>`;

/* Compact marker row for a card: first SDG target (+N) and a MyCOL flag. Details live in sdgTable at the page bottom. */
function marksHTML(tags, hasMycol) {
  if (!tags.length && !hasMycol) return "";
  const t = tags[0];
  return `<div class="route__tags">${t ? `<span class="tag" title="${esc(tags.length > 1 ? sdgAll(tags) : `Source: ${t.source}`)}">SDG ${esc(t.target)}${tags.length > 1 ? ` +${tags.length - 1}` : ""}</span>` : ""}${hasMycol ? `<span class="tag tag--mycol">MyCOL</span>` : ""}</div>`;
}

/* "TalentCorp MyCOL 2024/2025": occupations on Malaysia's shortage list that match the role (direct matches first). */
const mycolLinks = (items) => items.map((m) => {
  const text = `${m.occupation} (MASCO ${m.mascoCode}, ${m.year})`;
  const name = m.url ? `<a href="${esc(safeUrl(m.url))}" target="_blank" rel="noopener" title="Source: ${esc(m.label)} ${esc(m.year)}">${esc(text)}</a>` : esc(text);
  return `<p>${name} <span class="tag tag--mycol">${esc(m.strength)}</span> <span class="sdgt__note">(team judgement)</span></p>`;
}).join("") || `<span class="sdgt__note">None listed</span>`;

function sectorLines(sdg) {
  return sdg.sectors.map((x) => `<p>${esc(x.name)}: ${esc(x.sharePct)}% of this role's posts vs ${esc(x.baselinePct)}% of all posts (${esc(x.count)} of ${esc(x.posts)}, last ${esc(x.months)} months, as of ${esc(x.asOf)}) <span class="sdgt__note">source: data/role_sdg.json</span> ${x.tags.map(sdgTag).join(" ")}</p>`).join("")
    || `<span class="sdgt__note">No sector stands out</span>`;
}

/* One table: a row per role. rows = [{name, sdg: {tags, sectors}, mycol}] */
function sdgTable(rows) {
  const body = rows.map((r) => {
    const seen = new Set();
    const tags = [...r.sdg.tags, ...r.sdg.sectors.flatMap((x) => x.tags)].filter((t) => !seen.has(t.target) && seen.add(t.target));
    return `<tr><th scope="row" data-label="Role">${esc(r.name)}</th>
      <td data-label="SDG targets">${tags.map(sdgTag).join(" ") || `<span class="sdgt__note">None</span>`}</td>
      <td data-label="Sector evidence">${sectorLines(r.sdg)}</td>
      <td data-label="Malaysia (MyCOL 2024/2025)">${mycolLinks(r.mycol)}</td></tr>`;
  }).join("");
  return `<table class="sdgt"><caption>SDG targets and Malaysia shortage-list links for each role</caption>
    <thead><tr><th scope="col">Role</th><th scope="col">SDG targets</th><th scope="col">Sector evidence</th><th scope="col">Malaysia (MyCOL 2024/2025)</th></tr></thead>
    <tbody>${body}</tbody></table>`;
}

/* ── Today ─────────────────────────────────────────────────────── */
function stopRow(t) {
  const done = STATE.done.has(t.id);
  const locked = !canToggle(t.raw);
  const hint = locked ? (done ? "Untick the later weeks first" : `Finish week ${t.week - 1} first`) : "";
  return `<div class="stop${done ? " is-done" : ""}${locked && !done ? " is-locked" : ""}">
    ${bullet(t.line)}
    <div class="stop__mins">${Number(t.mins)}<small>min</small></div>
    <div class="stop__body">
      <div class="stop__title">${esc(t.title)}</div>
      <div class="stop__res">${ext(t.url, t.resource)}</div>
      <div class="stop__why"><b>Why today</b>${esc(t.why)} · ${esc(t.source)}</div>
      ${hint ? `<div class="stop__lock">${esc(hint)}</div>` : ""}
    </div>
    <button class="tick" data-act="tick" data-id="${esc(t.id)}" aria-pressed="${done}"${locked ? ` disabled title="${esc(hint)}"` : ""} aria-label="${done ? "Mark not done" : "Mark done"}: ${esc(t.title)}">${ICON.check}</button>
  </div>`;
}

/* Every task, grouped by week then day; the first unfinished day is marked "Up next". */
function allTasksHTML() {
  const fmt = (d) => new Date(`${d}T00:00:00`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
  const weeks = [...new Set(TODAY.all.map((t) => t.week))];
  return weeks.map((w) => {
    const inWeek = TODAY.all.filter((t) => t.week === w);
    const left = inWeek.filter((t) => !STATE.done.has(t.id)).length;
    const days = [...new Set(inWeek.map((t) => t.date))].map((d) => {
      const rows = inWeek.filter((t) => t.date === d);
      const mins = rows.reduce((n, t) => n + t.mins, 0);
      const tag = d === TODAY.day ? ` <span class="here-tag">Up next</span>` : "";
      return `<div class="tday${d === TODAY.day ? " is-next" : ""}"><h4>${esc(fmt(d))} <span>· ${mins} min</span>${tag}</h4>${rows.map(stopRow).join("")}</div>`;
    }).join("");
    return `<section class="tweek"><h3>Week ${Number(w)} <span>· ${left ? `${left} of ${inWeek.length} left` : "done"}</span></h3>${days}</section>`;
  }).join("");
}

/* What changed since the user accepted the plan, or one new skill the trend layer and job posts both rate as rising. */
/* The service-change band (DESIGN.md): plan changes, trend offers and the Project/Cert re-plan offers share it. */
const serviceBand = (sign, body, acts) => `<div class="service" role="status"><span class="service__sign">${sign}</span><div>${body}</div><div class="service__acts">${acts}</div></div>`;
/* A credit as text: 0.5 -> "½". Other values as a percentage of full credit. */
const creditText = (c) => ({ 0.5: "½", 0.25: "¼", 0.75: "¾" })[c] || `${Math.round(Number(c) * 100)}%`;
function planBand() {
  const { change, offer, outlookChange: oc } = STATE.plan;
  const band = serviceBand;
  // The target role's forecast moved since the plan was accepted (forecast ledger); shown above any other band.
  const outlook = oc ? band("Outlook changed", `<p>${esc(STATE.plan.targetRole)}: ${esc(oc.labelThen || "no label")} on ${esc(oc.since)}, now ${esc(oc.labelNow || "no label")}. Share of hiring posts ${(oc.shareThen * 100).toFixed(1)}% → ${(oc.shareNow * 100).toFixed(1)}%.</p><p><small>Source: ${esc(oc.source)}, ${esc(oc.date)}. Your plan is rebuilt from the new data; check the steps below.</small></p>`, "") : "";
  return outlook + planBandInner(change, offer, band);
}
function planBandInner(change, offer, band) {
  if (change) {
    const rows = [...change.added.map((a) => `<li><b>+ ${esc(a.skill)}</b> ${esc(a.reason)}</li>`),
      ...change.removed.map((r) => `<li><b>− ${esc(r.skill)}</b> ${esc(r.reason)}</li>`)].join("");
    return band("Plan changed", `<p>Job data or signals moved since you accepted this plan. Your ticks are kept.</p><ul class="plan-change">${rows}</ul>`,
      `<button class="btn" type="button" data-act="plan-keep">Keep change</button><button class="btn" type="button" data-act="plan-revert">Revert</button>`);
  }
  if (offer) {
    const skill = esc(offer.skill);
    return band("New skill", `<p><b>${skill}</b> is rising in AI news and in job posts.</p><ul class="plan-change"><li>${esc(offer.news)}</li><li>${esc(offer.jobs)}</li></ul>`,
      `<button class="btn" type="button" data-act="offer-add" data-skill="${skill}">Add to plan</button><button class="btn" type="button" data-act="offer-later" data-skill="${skill}">Not now</button>`);
  }
  return "";
}

const stepDone = (s) => s.taskIds.length > 0 && s.taskIds.every((id) => STATE.done.has(id));

function renderToday() {
  const blocked = gate("plan");
  if (blocked) return { html: head("Today", "Your next stops, taken from your pathway.") + blocked, bind: () => {} };

  const tasks = TODAY.tasks;
  const mins = tasks.reduce((n, t) => n + t.mins, 0);
  const doneStops = PATHWAY.filter((p) => p.status === "done").length;
  const allTasks = STATE.plan.tasks, tasksDone = allTasks.filter((t) => STATE.done.has(t.id)).length;
  const pct = allTasks.length ? Math.round((tasksDone / allTasks.length) * 100) : 100;  // a stop spans several days, so the bar counts tasks
  const used = ["apps", "guard", "serve"].filter((l) => PATHWAY.some((p) => p.line === l));
  const coming = PATHWAY.filter((p) => p.status === "next" && !tasks.some((t) => t.station === p.id)).slice(0, 4);
  const title = !TODAY.day ? "Today" : TODAY.day === todayIso() ? `Today, ${TODAY.date}` : `Next stop, ${TODAY.date}`;
  const lede = TODAY.day
    ? `${tasks.length} stop${tasks.length === 1 ? "" : "s"}, ${mins} minutes, from your pathway. Each one says why it is on your list.`
    : "You have ticked every task in this plan.";

  const finished = STATE.plan.steps.filter(stepDone);
  const html = `
    ${head(esc(title), esc(lede), real("Your plan · computed from your profile"))}
    <p class="route-note">${LEARNING_NOTE}</p>
    ${planBand()}
    <section class="route-strip" aria-label="Your route">
      <div class="route-strip__head">
        <h2><span class="bullets">${used.map((l) => bullet(l)).join("")}</span>To ${esc(TARGET.role)}</h2>
        <div class="progress">${doneStops} of ${PATHWAY.length} starter courses done · ${tasksDone} of ${allTasks.length} tasks ticked <span class="progress__bar"><i style="width:${pct}%"></i></span>${Number(STATE.plan.matchPct)}% match now</div>
      </div>
      <p class="route-key">${used.map((l) => `<b>${esc(LINES[l].letter)}</b> ${esc(LINES[l].name)}: ${esc(LINES[l].skill)}`).join(" · ")}</p>
      <div class="diagram" data-strip>${stripSVG()}</div>
    </section>
    <div class="today-grid">
      <section class="timetable" aria-labelledby="tt-h">
        <div class="timetable__head"><h2 id="tt-h">All tasks <span>· next day ${mins} min</span></h2></div>
        ${tasks.length ? "" : `<p class="empty">Nothing left to do in this plan.</p>`}
        ${allTasksHTML()}
      </section>
      <aside class="side">
        ${todayProofPanel()}
        ${finished.length ? `<section class="panel"><h2>Starter courses done</h2>
          <p>Mark a skill as learned only when you can use it on real work. It then joins your profile and leaves your plan. It counts only part of its weight in your match until a passed project or a verified cert proves it.</p>
          <ul class="next-list">${finished.map((s) => `<li><span>${esc(s.skill)}</span><button class="btn" type="button" data-act="learned" data-skill="${esc(s.skill)}">Mark as learned</button></li>`).join("")}</ul></section>` : ""}
        <section class="panel"><h2>Take it with you</h2>
          <p>Download the plan or add its tasks to your calendar. Nothing is sent anywhere.</p>
          <p><button class="btn" type="button" data-global="download-md">Download plan (.md)</button>
          <button class="btn" type="button" data-global="download-ics">Add to calendar (.ics)</button></p>
      <p><a class="btn btn--primary" href="#/cv">Open CV builder</a></p></section>
        <section class="panel"><h2>Coming up</h2>
          <ul class="next-list">${coming.map((p) => `<li>${bullet(p.line, true)}<span>${esc(p.title)}</span><span>Wk ${esc(p.week)}</span></li>`).join("")}</ul>
          <p style="margin-top:10px"><a href="#/pathway">See the whole route</a></p>
        </section>
      </aside>
    </div>`;

  const bind = (root) => {
    bindTodayProof(root);
    const strip = root.querySelector("[data-strip]");
    if (strip && strip.scrollWidth > strip.clientWidth) {
      const idx = PATHWAY.findIndex((p) => p.status === "current");
      strip.scrollLeft = Math.max(0, (idx / PATHWAY.length) * strip.scrollWidth - 60);
    }
    root.addEventListener("click", (e) => {
      const act = e.target.closest("[data-act]");
      if (!act) return;
      const { skill } = act.dataset;
      if (act.dataset.act === "learned") return markLearned(skill);
      if (act.dataset.act.startsWith("plan-")) return planDecision(act.dataset.act.slice(5));
      if (act.dataset.act.startsWith("offer-")) return planDecision(act.dataset.act.slice(6), skill);
      if (act.dataset.act !== "tick") return;
      const id = act.dataset.id;
      const task = STATE.plan.tasks.find((t) => t.id === id);
      if (!task || !canToggle(task)) return;  // later weeks stay locked until earlier ones are done
      if (STATE.done.has(id)) STATE.done.delete(id); else STATE.done.add(id);
      saveDone();
      refreshStatus();
      rerender(`[data-id="${id}"]`);
      const step = STATE.plan.steps.find((s) => s.taskIds.includes(id));
      if (step && STATE.done.has(id) && stepDone(step)) toast(`Starter course for ${step.skill} done.`, "Mark as learned", () => markLearned(step.skill));
    });
  };
  return { html, bind };
}

/* ── CV & routes ───────────────────────────────────────────────── */
/* The backend reads the CV (POST /api/cv/extract), the user ticks what is right, and Save keeps the
   profile on the server (POST /api/profile/apply). STATE.saved is that profile. An example profile
   (POST /api/profile/example) is saved the same way. */
const BASIS = { stated: "In your CV", implied: "Implied", suggested: "Suggested", self_reported: "Added by you" };
const QUOTE_DROPS = new Set(["QUOTE_NOT_FOUND", "PHRASE_NOT_IN_QUOTE"]);
const yearsText = (y) => (y == null ? "–" : `${y} yr`);
const isExample = (s) => s.evidence.some((e) => /^Synthetic example/.test(e.note || ""));

function llmLine(status) {
  if (status === "llm") return `Read by ${STATE.review.model}. Every quote was checked against your CV.`;
  if (status === "cached") return "A saved AI reading of this sample CV (no API key needed). Every quote was checked again.";
  return `The AI reading was not used (${status.replace("off:", "")}). These are keyword matches: tick the ones that are right.`;
}

const exampleButtons = () => STATE.examples.length
  ? `<p class="examples"><b>Try an example</b> (synthetic, no CV needed): ${STATE.examples.map((e) =>
      `<button class="btn btn--quiet" type="button" data-global="example" data-id="${esc(e.id)}" title="${esc(e.headline)}: ${esc(e.skills.join(", "))}">${esc(e.name)}</button>`).join("")}</p>`
  : "";

function cvPanel() {
  if (STATE.cv === "review") {
    return `<div class="cvfile">
      <div class="cvfile__name">${ICON.file}${esc(STATE.cvFile)}</div>
      <p>${esc(llmLine(STATE.review.llm_status))}</p>
      ${STATE.review.injection_hint ? `<p class="err" role="alert">Some lines look like instructions to an AI. They were read as CV text only, and skills on them are not ticked.</p>` : ""}
      <p>Untick anything that is wrong, then save. Nothing is stored until you do.</p>
      ${destinationField()}
      ${STATE.confirmSave && STATE.saved ? `<p role="alert"><b>You already have a saved profile.</b> Add these skills to it, or replace it?</p>
      <button class="btn btn--primary" data-act="cv-save" data-mode="add">Add ${STATE.keep.size} skills</button>
      <button class="btn" data-act="cv-save" data-mode="replace">Replace my profile</button>`
        : `<button class="btn btn--primary" data-act="cv-save">Save ${STATE.keep.size} skills</button>`}
      <button class="btn btn--quiet" data-act="cv-replace">Cancel</button>
    </div>`;
  }
  if (STATE.cv === "parsed" && STATE.saved) {
    return `<div class="cvfile">
      <div class="cvfile__name">${ICON.file}Your saved profile</div>
      <p>${STATE.saved.skills.length} skills · updated ${esc(STATE.saved.updated_at.slice(0, 10))}. ${STATE.saved.account ? "Kept on Varity's server under your account." : "Kept on Varity's server. Only this browser holds the key, so clearing your browser data loses it."}</p>
      ${typeof accountChip === "function" ? accountChip() : ""}
      <a class="btn" href="#/cv">Generate my CV</a>
      <button class="btn" data-act="cv-replace">Read another CV</button>
      <button class="btn btn--quiet" data-act="profile-delete">Delete my profile</button>
      ${exampleButtons()}
    </div>`;
  }
  if (STATE.cv === "parsing") {
    return `<div class="cvfile" aria-busy="true"><div class="cvfile__name">${ICON.file}${esc(STATE.cvFile)}</div><p>Reading your CV and quoting the evidence for each skill…</p><div class="skel" style="margin-top:14px;width:80%"></div></div>`;
  }
  const err = STATE.cv === "error" ? `<p class="err" role="alert">${esc(STATE.cvError)}</p>` : "";
  return `<div class="drop" data-drop>
      ${ICON.up}
      <strong>Drop your CV here</strong>
      <p>PDF, Word (.docx), OpenDocument (.odt), RTF, HTML or text, up to 5 MB and 4 pages. Use a public or synthetic CV. The file is read, not stored; only the skills you save are kept.</p>
      ${err}
      <label class="consent"><input type="checkbox" data-consent> I use a sample CV, not a real person's. The text goes to Anthropic for reading. <a href="privacy.html" target="_blank" rel="noopener">Privacy notice</a></label>
      <input type="file" accept=".pdf,.docx,.odt,.rtf,.html,.htm,.txt,.md" hidden data-file>
      <button class="btn" type="button" data-act="cv-choose">Choose a file</button>
      <button class="btn btn--quiet" type="button" data-act="cv-sample">Use the synthetic sample CV</button>
    </div>
    ${exampleButtons()}`;
}

/* The roles the forecast knows (live or snapshot): the only destinations that can get a route. */
function destinationField() {
  const roles = Object.entries(FORECAST.roles || {}).sort((a, b) => a[1].name.localeCompare(b[1].name));
  if (!roles.length) return "";
  const opts = roles.map(([id, r]) => `<option value="${esc(id)}"${STATE.destination === id ? " selected" : ""}>${esc(r.name)}</option>`).join("");
  return `<label class="dest"><span class="dest__label">Destination (optional)</span>
      <select class="dest__select" data-dest><option value="">Not sure yet</option>${opts}</select>
      <span class="dest__hint">Pick the role you want. We'll still show other routes.</span></label>`;
}

function reviewTable() {
  const r = STATE.review;
  const rows = r.rows.map((row) => `<tr>
      <td><input type="checkbox" class="keep" data-keep="${esc(row.skill_id)}" aria-label="Keep ${esc(row.name)}"${STATE.keep.has(row.skill_id) ? " checked" : ""}></td>
      <td>${esc(row.name)}</td><td><span class="lvl">${esc(BASIS[row.basis])}</span></td>
      <td class="q">${row.quote ? `“${esc(row.why)}”` : esc(row.why)}${row.note ? `<br><span class="err">${esc(row.note)}</span>` : ""}</td>
      <td>${esc(yearsText(row.years))}</td></tr>`).join("");
  const dropped = r.dropped.filter((d) => QUOTE_DROPS.has(d.reason));
  return `<table class="skills"><thead><tr><th scope="col">Keep</th><th scope="col">Skill</th><th scope="col">Basis</th><th scope="col">Why</th><th scope="col">Years</th></tr></thead><tbody>${rows}</tbody></table>
    ${r.interests.length ? `<p class="empty"><b>Learning, not counted as skills:</b> ${r.interests.map((i) => esc(i.name)).join(", ")}</p>` : ""}
    ${dropped.length ? `<p class="empty"><b>Dropped because the quote is not in your CV:</b> ${dropped.map((d) => esc(d.phrase)).join(", ")}</p>` : ""}`;
}

function savedTable() {
  const why = (s) => (s.evidence_quote ? `“${esc(s.evidence_quote)}”`
    : esc((s.evidence.find((e) => e.rule) || s.evidence.find((e) => e.note) || {}).rule || (s.evidence.find((e) => e.note) || {}).note || "Added by you"));
  const basis = (s) => (isExample(s) ? "Synthetic example" : BASIS[s.basis]);
  return `<table class="skills"><thead><tr><th scope="col">Skill and Experience</th><th scope="col">Basis</th><th scope="col">Why</th><th scope="col">Years</th><th scope="col">Edit</th></tr></thead>
    <tbody>${STATE.saved.skills.map((s) => `<tr><td>${esc(s.name)}</td><td><span class="lvl">${esc(basis(s))}</span></td><td class="q">${why(s)}</td><td>${esc(yearsText(s.years))}</td>
      <td><button class="btn btn--quiet" data-act="skill-remove" data-id="${esc(s.skill_id)}" aria-label="Remove ${esc(s.name)}">Remove</button></td></tr>`).join("")}</tbody></table>`;
}

function skillsTable() {
  if (STATE.cv === "review") return reviewTable();
  if (STATE.cv === "parsed" && STATE.saved) return savedTable();
  if (STATE.cv === "parsing") {
    const row = `<tr><td><div class="skel" style="width:120px"></div></td><td><div class="skel" style="width:60px"></div></td><td><div class="skel"></div></td></tr>`;
    return `<table class="skills"><tbody>${row.repeat(4)}</tbody></table>`;
  }
  return `<p class="empty">Upload a CV or try an example profile. Your skills appear here, each with the sentence from your CV that proves it.</p>`;
}

/* Live route from GET /api/roles/suggestions. Every reason chip was written by code from a dated source;
   the AI (when used) only chose which chips to show and wrote the one-line summary. */
const CHIP_ICON = { skill_fit: "🧩", small_gap: "🎯", demand_rising: "📈", ai_boost: "⚡", watch_out: "⚠️", pays_more: "💰",
  closes_gap: "🧩", skill_rising: "📈", no_regret: "🎯" };
const SOURCE_TEXT = { profile: "your saved profile", role_forecast: "job forecast", signals: "AI signals run", resources: "verified resources",
  role_profiles: "role profiles", skill_scores: "skill scores" };
const reasonChip = (c, cls = "") => `<span class="chip reason${cls}" title="Source: ${esc(SOURCE_TEXT[c.source] || c.source)}${c.asOf ? `, ${esc(c.asOf)}` : ""}"><span aria-hidden="true">${CHIP_ICON[c.type] || "•"}</span> ${esc(c.text)}</span>`;

/* "Why NN%?": the score's parts and what each top gap skill would add. Numbers come from engine/roles.score_breakdown. */
function whyPanel(r) {
  const b = r.breakdown;
  if (!b) return "";
  const pct = (x) => `${(Number(x) * 100).toFixed(1)}%`;
  const raise = b.raise.map((x) => `<li>${x.kind === "prove" ? `Prove ${esc(x.skill)} with a project or cert` : esc(x.skill)} → ${Number(x.newRank).toFixed(3)}${x.resource && /^https?:\/\//.test(x.resource.url) ? ` (<a href="${esc(x.resource.url)}" target="_blank" rel="noopener">${esc(x.resource.title)}</a>)` : ""}</li>`).join("");
  return `<details class="route__calc"><summary>Why ${Number(r.matchPct)}%?</summary>
    <p>${Number(b.matchWeight)} × match ${pct(b.match)} + ${Number(b.outlookWeight)} × outlook ${Number(b.outlook).toFixed(1)} (${esc(r.trendLabel || "unknown")}) = ${Number(b.rank).toFixed(3)}</p>
    ${(b.levels || []).length ? `<p>Skills you have, by proof:</p><ul>${b.levels.map((x) => `<li>${esc(x.skill)} · ${esc(x.level)} · ${x.credit < 1 ? creditText(x.credit) : "full"} credit</li>`).join("")}</ul>` : ""}
    ${raise ? `<p>What would raise it:</p><ul>${raise}</ul>` : ""}
    <p class="route-note">The ${Number(b.matchWeight)} / ${Number(b.outlookWeight)} weights are team judgement, not fitted.</p></details>`;
}

/* The goal line of a route card: counts from the API; it says so when the sample is too small to re-rank. */
function goalLine(r) {
  const g = r.goal;
  if (!g) return "";
  if (g.share == null) return `<p class="route-note">Goal: too few posts to measure this sector for this role.</p>`;
  const rank = g.goalRank ? ` Goal fit rank: #${Number(g.goalRank)}.` : "";
  return `<p class="route-note">Goal: ${Number(g.count)} of ${Number(g.n)} posts (${(g.share * 100).toFixed(1)}%) came from this sector, against ${(g.baselineShare * 100).toFixed(1)}% of all posts.${g.reliable ? "" : ` Too few posts to re-rank (n = ${Number(g.count)}).`}${rank}</p>`;
}

function liveRouteRow(r, pinned = false) {
  const cur = STATE.routeId === r.roleId;
  const low = r.rank == null;  // a low-match destination: pinned for the user, never ranked
  const action = cur
    ? `<span class="current-tag"><i></i>Your current route</span>`
    : `<button class="btn" data-act="route" data-id="${esc(r.roleId)}">Switch to this route</button>`;
  const fast = STATE.scenario === "fast" && r.fastShift != null
    ? `<p class="route-note">If AI speeds up (estimate): about ${r.fastShift >= 0 ? "+" : ""}${(r.fastShift * 100).toFixed(1)}% role demand vs expected. Does not change the ranking.</p>` : "";
  return `<div class="route${cur ? " is-current" : ""}">
    <div class="route__row">
      <div class="route__match${low ? " route__match--low" : ""}">${Number(r.matchPct)}%<small>match now</small></div>
      <div><div class="route__role">${low ? "" : `#${Number(r.rank)} `}${esc(r.name)}${pinned ? ` <span class="plate">Destination</span>` : ""}</div>
        <div class="route__role-sub"><b>${esc(r.fitLabel)}</b></div>
        ${low ? `<p class="route-note">Long ride: this role needs most of its skills still. Other routes below are closer.</p>` : ""}</div>
      ${action}
    </div>
    <div class="route__gap">
      <div><h3>You already have</h3><div class="chips">${r.have.map((h) => { const lv = ((r.breakdown && r.breakdown.levels) || []).find((x) => x.skill === h); const part = lv && lv.credit < 1;
        return `<span class="chip"${part ? ` title="Learned on your pathway: ${creditText(lv.credit)} credit until a project or cert proves it"` : ""}>${esc(h)}${part ? ` ${creditText(lv.credit)}` : ""}</span>`; }).join("") || "<span>None yet</span>"}</div>${proofCounts(r)}</div>
      <div><h3>Skills to learn</h3><div class="chips">${r.gap.map((g) => `<span class="chip chip--gap">${esc(g)}</span>`).join("") || "<span>No gap</span>"}</div></div>
    </div>
    <details class="route__more"><summary>Details</summary>
      ${r.summary ? `<p class="route__summary">${esc(r.summary)}</p>` : ""}
      <p class="route-note">${r.have.length} of ${r.have.length + r.gap.length} core skills held (match is weighted). ${r.gap.length} to learn.</p>
      ${r.sdgReason ? `<p class="route-note">${esc(r.sdgReason)}</p>` : ""}${goalLine(r)}
      <div class="route__why"><div class="chips">${r.reasons.map((c) => reasonChip(c)).join("")}${r.watchOut ? reasonChip(r.watchOut, " reason--watch") : ""}</div>
        ${fast}${marksHTML(r.sdg.tags, r.mycol.length > 0)}</div>
      ${whyPanel(r)}
    </details>
  </div>`;
}

/* DOSM official online vacancies: the Malaysian check beside the HN sample. Sector level only (DOSM has no job-title split). */
const dosmQuarter = (q) => String(q).replace(/^(\d{4})-(Q\d)$/, "$2 $1");
const dosmPct = (p) => (p === null || p === undefined ? "" : ` (${p >= 0 ? "+" : ""}${p}% on a year ago)`);
function malaysiaLine() {
  const m = STATE.malaysia;
  if (!m || !m.ict) return "";
  return `<p class="route-note">Malaysia check (DOSM, official online vacancies): ${esc(m.ict.label)} sector ${Number(m.ict.vacancies).toLocaleString("en-GB")} in ${esc(dosmQuarter(m.ict.quarter))}${esc(dosmPct(m.ict.vsYearAgoPct))}. ${esc(m.note)} HN = global tech hiring sample. <a href="${esc(m.sourceUrl)}" target="_blank" rel="noopener">Data source: Department of Statistics Malaysia</a></p>`;
}

function liveRoutes() {
  const s = STATE.suggest;
  const w = s.formulaWeights;
  const formula = `match ${Math.round(w.match * 100)}% + demand ${Math.round(w.future * 100)}%`;
  const by = s.rankedBy === "llm" ? "Ranked by AI within limits, checked against the data" : `Ranked by the formula (${formula})`;
  // The destination is pinned first; this changes display order only, the ranks shown stay the formula's.
  const goal = s.targetRoleId;
  const dest = s.roles.find((r) => r.roleId === goal) || (s.lowMatchTarget && s.lowMatchTarget.roleId === goal ? s.lowMatchTarget : null);
  const pos = (r) => (s.goalOrder ? s.goalOrder.indexOf(r.roleId) : 0);
  const others = s.roles.filter((r) => r.roleId !== goal).sort((a, b) => pos(a) - pos(b));
  const lowOthers = s.lowMatch.filter((r) => r.roleId !== goal);
  const low = lowOthers.length ? `<p class="empty"><b>Low match, not ranked:</b> ${lowOthers.map((r) => `${esc(r.name)} (${Number(r.matchPct)}%)`).join(", ")}</p>` : "";
  const ranked = [dest, ...others].filter(Boolean);
  const goalNote = s.goalNote ? `<p class="route-note">${esc(s.goalNote)}</p>` : "";
  const unmapped = s.unmappedSkills.length ? `<p class="empty"><b>Not in the job data yet, so not counted:</b> ${s.unmappedSkills.map(esc).join(", ")}</p>` : "";
  const list = others.length ? others.map((r) => liveRouteRow(r)).join("")
    : dest ? "" : `<p class="empty">No role matches your saved skills well yet. Add skills from another CV.</p>`;
  return `${goalPicker()}${goalNote}<p class="route-note">${esc(by)}. Skills as of ${esc(s.inputs.skillsAsOf || "–")}, job forecast as of ${esc(s.inputs.forecastAsOf || "–")}. Salary data is not available yet.</p>${malaysiaLine()}
    ${dest ? `${liveRouteRow(dest, true)}${others.length ? `<h3 class="routes-sub">Other routes</h3>` : ""}` : ""}${list}${low}${unmapped}
    ${ranked.length ? `<section class="sdgsec" aria-labelledby="sdg-h"><h2 class="sec" id="sdg-h">Why these jobs matter: SDG and Malaysia links</h2>
      <p class="route-note">Each role is tied to the UN Sustainable Development Goals (SDG) and to Malaysia's list of occupations in short supply (MyCOL). Hover a target to see its source.</p>
      ${sdgTable(ranked)}</section>` : ""}`;
}

function plannerHTML() {
  const problem = (msg) => `<p class="err" role="alert">${esc(msg)}</p><p><button class="btn" type="button" data-global="retry">Try again</button></p>`;
  if (STATE.loading) return `<p class="empty" role="status" aria-busy="true">Loading your routes…</p>`;
  if (STATE.profileError) return problem(STATE.profileError);
  if (!STATE.saved) return `<p class="empty">Upload a CV or try an example profile. Routes appear after that.</p>`;
  if (STATE.suggestError) return problem(STATE.suggestError);
  if (!STATE.suggest) return "";
  return `<div class="planner__from"><b>From</b> ${esc(STATE.saved.name || "your saved profile")} ${ICON.arrow} <b>To</b> ${esc((FORECAST.roles[STATE.saved.target_role || STATE.destination] || {}).name || "the roles your skills fit best")}</div>${scenarioToggle()}${liveRoutes()}`;
}

function stationText() {
  if (STATE.cv === "parsed" && STATE.saved) return [STATE.saved.name || "Your profile", `${STATE.saved.skills.length} skills, each with its evidence`];
  if (STATE.cv === "review") return ["Check your skills", `${STATE.review.rows.length} found in ${STATE.cvFile}`];
  return ["Origin station", "Waiting for a CV or an example profile"];
}

function renderProfile() {
  const parsed = STATE.cv === "parsed";
  const [station, stationSub] = stationText();
  const html = `
    ${head("Your CV and routes", "Varity reads your CV, shows the sentence behind every skill it finds, then plans routes to roles, with each role's demand trend.", STATE.suggest ? real("Match scores computed from your skills") : "")}
    ${typeof replayLabel === "function" && replayLabel() ? `<p class="method" role="status"><b>${esc(replayLabel())}</b></p>` : ""}
    <div class="origin">
      <div>${cvPanel()}</div>
      <section aria-labelledby="org-h">
        <div class="origin-stn"><span class="origin-stn__ring" aria-hidden="true"></span><div><h2 id="org-h">${esc(station)}</h2><p>${esc(stationSub)}</p></div></div>
        ${skillsTable()}
      </section>
    </div>
    <section aria-labelledby="jp-h">
      <h2 class="sec" id="jp-h">Journey planner <small>Match = weighted share of the role's core skills you hold (weights from job posts)</small></h2>
      ${parsed || STATE.loading ? plannerHTML() : `<p class="empty">Upload a CV or try an example profile. Routes appear after that.</p>`}
    </section>`;

  const bind = (root) => {
    if (location.hash.includes("examples=1")) { STATE.focusEx = true; setTimeout(() => { STATE.focusEx = false; }, 3000); history.replaceState(null, "", "#/profile"); }  // from the landing's "Try an example"
    const ex = STATE.focusEx && root.querySelector(".examples");  // later redraws (profile load) replace main, so keep trying for 3s
    if (ex) { ex.scrollIntoView({ block: "center" }); ex.querySelector("button").focus({ preventScroll: true }); }
    const fileInput = root.querySelector("[data-file]");
    const drop = root.querySelector("[data-drop]");
    const fail = (message) => { STATE.cv = "error"; STATE.cvError = message; rerender(); };
    const read = async (name, body) => {
      STATE.cv = "parsing";
      STATE.cvFile = name;
      rerender();
      try {
        STATE.review = await api("/api/cv/extract", { method: "POST", body: JSON.stringify(body) });
      } catch (err) {
        fail(errText(err));
        return;
      }
      STATE.keep = new Set(STATE.review.rows.filter((r) => r.default_keep).map((r) => r.skill_id));
      STATE.cv = "review";
      rerender();
      toast("CV read. Check each skill against its quote.");
    };
    const consented = () => {
      const ok = !root.querySelector("[data-consent]") || root.querySelector("[data-consent]").checked;
      if (!ok) toast("Tick the box first: use a sample CV, not a real person's.");
      return ok;
    };
    const accept = (file) => {
      if (!consented()) return;
      if (!/\.(pdf|docx|odt|rtf|html?|txt|md)$/i.test(file.name)) return fail(`“${file.name}” is not a supported file type. Export your CV as a PDF and try again.`);
      if (file.size > 5 * 1024 * 1024) return fail(`“${file.name}” is larger than 5 MB.`);
      const reader = new FileReader();
      reader.onload = () => read(file.name, { file_name: file.name, file_b64: String(reader.result).split(",")[1] || "" });
      reader.onerror = () => fail(`“${file.name}” could not be opened.`);
      reader.readAsDataURL(file);
    };
    const call = async (path, options, done) => {
      try {
        done(await api(path, options));
      } catch (err) {
        if (err.status === 410) {  // review expired or already saved: start again rather than leave a dead Save button
          STATE.cv = "empty";
          STATE.review = null;
          rerender();
        }
        toast(errText(err));
      }
    };
    root.addEventListener("change", (e) => {
      const dest = e.target.closest("[data-dest]");
      if (dest) { STATE.destination = dest.value; return; }
      const box = e.target.closest("[data-keep]");
      if (!box) return;
      if (box.checked) STATE.keep.add(box.dataset.keep);
      else STATE.keep.delete(box.dataset.keep);
      const save = root.querySelector('[data-act="cv-save"]');
      if (save) save.textContent = `Save ${STATE.keep.size} skills`;
    });
    if (fileInput) fileInput.addEventListener("change", () => fileInput.files[0] && accept(fileInput.files[0]));
    if (drop) {
      drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("is-over"); });
      drop.addEventListener("dragleave", () => drop.classList.remove("is-over"));
      drop.addEventListener("drop", (e) => {
        e.preventDefault();
        drop.classList.remove("is-over");
        if (e.dataTransfer.files[0]) accept(e.dataTransfer.files[0]);
      });
    }
    root.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-act]");
      if (!b) return;
      const act = b.dataset.act;
      if (act === "cv-replace") { STATE.cv = "empty"; STATE.review = null; STATE.confirmSave = false; rerender(); }
      else if (act === "cv-choose") { if (consented()) fileInput.click(); }
      else if (act === "cv-sample") read("aina.txt (synthetic sample)", { sample: "aina" });
      else if (act === "cv-save") {
        if (STATE.saved && !b.dataset.mode) { STATE.confirmSave = true; rerender('[data-mode="add"]'); return; }
        const before = new Set(STATE.saved ? STATE.saved.skills.map((s) => s.skill_id) : []);
        const replace = b.dataset.mode === "replace";
        STATE.confirmSave = false;
        if (replace) {
          try { await api("/api/profile", { method: "DELETE" }); } catch (err) { toast(errText(err)); return; }
          before.clear();
        }
        call("/api/profile/apply", { method: "POST", body: JSON.stringify({ review_id: STATE.review.review_id, kept_ids: [...STATE.keep] }) }, async (data) => {
          setProfileToken(data.token);
          STATE.saved = data.profile;
          STATE.review = null;
          STATE.cv = "parsed";
          STATE.suggest = null;  // routes belong to the old profile: hide them until the new ones load
          resetCvBuilder();  // a new CV was read: the builder loads the draft again
          const added = data.profile.skills.filter((s) => !before.has(s.skill_id)).length;
          let note = before.size ? `Added ${added} new skills to your profile (${data.profile.skills.length - added} already there).` : `Saved ${data.profile.skills.length} skills to your profile.`;
          // Set separately: apply uses up the review, so a refused destination there would lose the user's ticks.
          const dest = STATE.destination && FORECAST.roles[STATE.destination];
          if (dest) {
            try {
              STATE.saved = (await api("/api/profile/target-role", { method: "POST", body: JSON.stringify({ roleId: STATE.destination }) })).profile;
              note += ` Destination set: ${dest.name}.`;
            } catch (err) {
              note += ` ${dest.name} has no route for them yet.`;
            }
          }
          rerender();
          toast(note);
          refreshRoutes();
        });
      }
      else if (act === "skill-remove") {
        call("/api/profile/remove", { method: "POST", body: JSON.stringify({ skill_id: b.dataset.id }) }, (data) => {
          STATE.saved = data.profile;
          rerender();
          toast("Removed. It stays removed when you read another CV.");
          refreshRoutes();
        });
      }
      else if (act === "profile-delete") {
        if (!confirm("Delete your saved profile from Varity's server? This cannot be undone.")) return;
        call("/api/profile", { method: "DELETE" }, () => {
          setProfileToken(null);
          STATE.saved = null;
          STATE.suggest = null;
          STATE.routeId = null;
          applyPlan(null);
          STATE.cv = "empty";
          resetCvBuilder();  // the server deleted the draft and notes with the profile
          rerender();
          toast("Your profile was deleted.");
        });
      }
      else if (act === "route") {
        call("/api/profile/target-role", { method: "POST", body: JSON.stringify({ roleId: b.dataset.id }) }, async (data) => {
          STATE.saved = data.profile;
          STATE.routeId = data.profile.target_role;
          STATE.done = new Set();
          await loadPlan();
          STATE.loading = "";
          location.hash = "#/pathway";
          rerender();
          toast(STATE.plan ? `Route switched. Your pathway now leads to ${STATE.plan.targetRole}.` : "Route saved, but the pathway could not be built.");
        });
      }
    });
  };
  return { html, bind };
}

/* ── Pathway ───────────────────────────────────────────────────── */
/* "all with free resources" only when every chosen resource is free. */
function costText(steps) {
  const costs = steps.filter((s) => s.resource).map((s) => s.resource.cost);
  if (!costs.length) return "";
  const paid = costs.filter((c) => c !== "free");
  if (!paid.length) return "all with free resources";
  return `${costs.length - paid.length} of ${costs.length} resources are free; the others are ${[...new Set(paid)].join(" or ")}`;
}

/* The HRD Corp option under the free resource (data/hrd_programmes.json, checked by hand). */
function employerLine(e) {
  if (!e || !/^https?:\/\//.test(e.url)) return "";
  return `<p class="pstop__why">Employer-funded option (HRD Corp): <a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title)}</a> by ${esc(e.provider)}, ${Number(e.days)} days, RM ${Number(e.feeMyr).toLocaleString("en-MY")}. ${esc(e.hrdStatus)} Checked ${esc(e.checkedOn || "–")}. Your employer must apply before the course starts.</p>`;
}

function renderPathway() {
  const blocked = gate("plan");
  if (blocked) return { html: head("Pathway", "The ordered stops from your skills to your route.") + blocked, bind: () => {} };

  // Weeks with a stop or a task: a stop's later parts can fall in a week where no stop starts.
  const weeks = [...new Set([...PATHWAY.map((p) => p.week), ...TODAY.all.map((t) => t.week)])].sort((a, b) => a - b);
  const statusText = { done: "Starter course done", current: "You are here", next: "Upcoming" };
  const stopHTML = (p) => `<div class="pstop is-${p.status}" data-stop="${esc(p.id)}">
      ${bullet(p.line, true)}
      <div><div class="pstop__t">${esc(p.title)}<span>${Number(p.mins)} min</span></div>
        <div class="pstop__r">${p.url ? ext(p.url, p.resource) : esc(p.resource)}</div>${employerLine(p.employer)}
        <div class="pstop__m">${p.status === "current" ? `<span class="here-tag">You are here</span>` : `<span>${statusText[p.status]}</span>`}${p.progress > 0 && p.progress < 1 ? `<span class="tag">${Math.round(p.progress * 100)}% done</span>` : ""}<span class="tag">${esc(p.cost)}</span>${p.goalLinked ? `<span class="tag">SDG goal</span>` : ""}${p.sdgTags.length ? `<span class="tag" title="${esc(p.sdgTags.length > 1 ? sdgAll(p.sdgTags) : `Source: ${p.sdgTags[0].source}`)}">SDG ${esc(p.sdgTags[0].target)}${p.sdgTags.length > 1 ? ` +${p.sdgTags.length - 1}` : ""}</span>` : ""}</div>
        ${p.sdgReason ? `<p class="pstop__why">${esc(p.sdgReason)}</p>` : ""}
        ${p.why ? `<p class="pstop__why">${esc(p.why)}</p>` : ""}
        ${p.reasons ? `<div class="chips">${p.reasons.map((c) => reasonChip(c)).join("")}</div>` : ""}</div>
    </div>`;
  const fmtDay = (d) => new Date(`${d}T00:00:00`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
  // The current week is the first one with an unticked task; later weeks are shown but locked until it is done.
  const open = TODAY.all.find((t) => !STATE.done.has(t.id));
  const nowWeek = open ? open.week : Infinity;
  const weekHTML = (w) => {
    const stops = PATHWAY.filter((p) => p.week === w);
    const tasks = TODAY.all.filter((t) => t.week === w);
    const hrs = Math.round((tasks.reduce((n, t) => n + t.mins, 0) / 60) * 10) / 10;
    const done = tasks.filter((t) => STATE.done.has(t.id)).length;
    const state = w < nowWeek ? "done" : w === nowWeek ? "now" : "locked";
    const label = { done: "Done", now: "This week", locked: `Opens after week ${w - 1}` }[state];
    const dates = tasks.length ? `${fmtDay(tasks[0].date)} – ${fmtDay(tasks[tasks.length - 1].date)}` : "";
    const list = tasks.map((t) => `<li class="${STATE.done.has(t.id) ? "is-done" : ""}"><span>${STATE.done.has(t.id) ? "✓" : "○"}</span>${esc(fmtDay(t.date))} · ${esc(t.title)} <small>${Number(t.mins)} min</small></li>`).join("");
    return `<section class="week is-${state}"${state === "locked" ? ` inert aria-label="Week ${esc(w)}, locked: ${esc(label)}"` : ""}>
      <div class="week__head"><h3>Week ${esc(w)}</h3><span class="week__state">${state === "locked" ? "🔒 " : state === "done" ? "✓ " : ""}${esc(label)}</span>
        <p>${esc(dates)}</p><p>${hrs} h · ${tasks.length} tasks${done ? ` · ${done} done` : ""}</p></div>
      <div class="week__stops">${stops.map(stopHTML).join("") || `<p class="week__cont">Continues the courses from the week before.</p>`}</div>
      ${list ? `<div class="week__tasks"><ul class="wtasks" aria-label="Tasks in week ${esc(w)}">${list}</ul>${state === "now" ? `<p><a href="#/today">Tick tasks on Today</a></p>` : ""}</div>` : ""}</section>`;
  };

  const plan = STATE.plan;
  const badge = real(plan.personalisedBy === "llm" ? "Personalised by AI, checked against the data" : "Built by the formula from your profile");
  const lede = !PATHWAY.length
    ? `You already have every core skill of ${esc(TARGET.role)}, so there is no gap to plan.`
    : `${PATHWAY.length} stops over ${weeks.length} weeks, about ${Number(plan.totals.hours)} hours (estimate)${costText(plan.steps) ? `, ${esc(costText(plan.steps))}` : ""}. Hover a station to light its line.`;
  const used = ["apps", "guard", "serve"].filter((l) => PATHWAY.some((p) => p.line === l));
  const sdg = plan.sdgSummary;

  const html = `
    ${head(`Pathway to ${esc(TARGET.role)}`, lede, badge)}
    <p class="route-note">${LEARNING_NOTE}</p>
    <p class="route-note">${esc(plan.scenarioLabel)}: ${Number(plan.hoursPerWeek)} h a week from ${esc(plan.startDate)}${plan.finishDate ? ` to ${esc(plan.finishDate)}` : ""}. Skills as of ${esc(plan.skillsAsOf || "–")}. ${esc(plan.notes[0] || "")} <a href="#/profile">Change route</a></p>
    ${scenarioToggle()}${goalPicker()}
    <section class="pathmap" aria-label="Route map">
      <div class="diagram">${pathwaySVG()}</div>
      <p class="swipe-hint" style="padding:0 12px">Swipe the map sideways to see every station.</p>
      <div class="legend">
        ${used.map((l) => `<span><i class="sw-line" style="background:var(--${l})"></i>${esc(LINES[l].name)} · ${esc(LINES[l].skill)}</span>`).join("")}
        <span><i class="sw-dot sw-done"></i>Starter course done</span>
        <span><i class="sw-dot sw-here"></i>You are here</span>
        <span><i class="sw-x"></i>Interchange: one stop on two lines</span>
      </div>
    </section>
    ${proofSection()}
    <div class="weeks-head"><h2 class="sec">Your weeks</h2><a class="btn btn--primary" href="#/cv">Open CV builder</a></div>
    <div class="weeks">${weeks.map(weekHTML).join("")}</div>
    <section class="sdgsec" aria-labelledby="sdg-h"><h2 class="sec" id="sdg-h">Why this job matters: SDG and Malaysia links</h2>
      ${sdg.lines.map((l) => `<p class="route-note">${esc(l)}</p>`).join("")}
      <p class="route-note">${esc(sdg.line)}</p>
      ${sdgTable([{ name: TARGET.role, sdg: plan.roleSdg, mycol: plan.mycol }])}</section>`;

  const bind = (root) => {
    bindProof(root);
    const map = root.querySelector(".pathmap");
    bindLineLighting(map, (g, on) => {
      const row = g.dataset.stop && root.querySelector(`.pstop[data-stop="${g.dataset.stop}"]`);
      if (row) row.classList.toggle("is-lit", on);
    });
    root.querySelectorAll(".pstop").forEach((row) => {
      const g = map.querySelector(`.stn[data-stop="${row.dataset.stop}"]`);
      if (!g) return;
      row.addEventListener("mouseenter", () => g.dispatchEvent(new Event("mouseenter")));
      row.addEventListener("mouseleave", () => g.dispatchEvent(new Event("mouseleave")));
    });
  };
  return { html, bind };
}
