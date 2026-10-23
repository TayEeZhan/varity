/* Screen renderers for Today, CV & routes, and Pathway. Each returns { html, bind(root) }. State lives in app.js (STATE). */

const ICON = {
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  out: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
  push: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h10M4 12h7M4 18h7"/><path d="M15 15l3 3 4-6"/></svg>',
  file: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7z"/><path d="M14 3v4h4M9 13h6M9 17h6"/></svg>',
  up: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M5 20h14"/></svg>',
  arrow: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
};

const bullet = (line, sm) => `<span class="bullet bullet--${line}${sm ? " bullet--sm" : ""}" title="${LINES[line].name}">${LINES[line].letter}</span>`;
const ext = (url, text) => `<a href="${url}" target="_blank" rel="noopener">${esc(text)} ${ICON.out}</a>`;
const head = (title, lede, aside = "") => `<div class="screen-head"><div><h1>${title}</h1><p>${lede}</p></div>${aside}</div>`;
const synth = (text) => `<span class="synthetic">${text}</span>`;
const real = (text) => `<span class="synthetic real">${text}</span>`;

/* ── Today ─────────────────────────────────────────────────────── */
function activeTasks() {
  const tasks = TODAY.tasks.slice();
  if (STATE.replan === "reverted") {
    tasks.push(...TODAY.cancelled.map((c) => ({ ...c, resource: "GitHub Copilot docs", url: "https://docs.github.com/copilot", why: "Yesterday's plan, restored by you", source: "Manual" })));
  }
  return tasks;
}

function serviceBand() {
  if (!TODAY.replan) return "";
  if (STATE.replan === "kept") {
    return `<div class="service is-kept" role="status"><span class="service__sign">Service change kept</span><p>${esc(TODAY.replan.text)}</p></div>`;
  }
  if (STATE.replan === "reverted") {
    return `<div class="service" role="status"><span class="service__sign">Change reverted</span><p>Yesterday's plan is back, including the Copilot stop. The models it compares are retired, so it may be out of date.</p><div class="service__acts"><button class="btn" data-act="replan-keep">Apply the change again</button></div></div>`;
  }
  return `<div class="service" role="status"><span class="service__sign">Service change</span><p><b>${TODAY.replan.when}.</b> ${esc(TODAY.replan.text)}</p><div class="service__acts"><button class="btn" data-act="replan-keep">Keep change</button><button class="btn" data-act="replan-revert">Revert</button></div></div>`;
}

function stopRow(t) {
  const done = STATE.done.has(t.id);
  return `<div class="stop${done ? " is-done" : ""}">
    ${bullet(t.line)}
    <div class="stop__mins">${t.mins}<small>min</small></div>
    <div class="stop__body">
      <div class="stop__title">${esc(t.title)}</div>
      <div class="stop__res">${ext(t.url, t.resource)}</div>
      <div class="stop__why"><b>Why today</b>${esc(t.why)} · ${esc(t.source)}</div>
    </div>
    <button class="tick" data-act="tick" data-id="${t.id}" aria-pressed="${done}" aria-label="${done ? "Mark not done" : "Mark done"}: ${esc(t.title)}">${ICON.check}</button>
  </div>`;
}

function cancelledRow(c) {
  return `<div class="stop stop--cancelled">
    ${bullet(c.line)}
    <div class="stop__mins">${c.mins}<small>min</small></div>
    <div class="stop__body">
      <div class="stop__title">${esc(c.title)}</div>
      <div class="stop__why"><span class="stamp">Cancelled</span>${esc(c.reason)}</div>
    </div>
  </div>`;
}

function googlePanel(open) {
  if (STATE.push === "sent") {
    return `<section class="panel"><h2>Google Tasks</h2>
      <div class="gt-status is-sent"><i></i>Sent to “Varity · Thu 23 Oct”</div>
      <ul class="sent-list">${STATE.sent.map((t) => `<li>${bullet(t.line, true)}<span>${esc(t.title)}</span></li>`).join("")}</ul>
      <p>Due today. Ticking a task in Google Tasks ticks it here too.</p>
      <button class="btn btn--quiet" data-act="unpush" style="margin:8px 0 0 -10px">Undo send</button>
      <p style="margin-top:8px">Simulated in this prototype: no Google account is contacted.</p></section>`;
  }
  return `<section class="panel"><h2>Google Tasks</h2>
    <div class="gt-status"><i></i>Not sent yet today</div>
    <p>One click creates a dated list with today's ${open.length} open stop${open.length === 1 ? "" : "s"}, each linking back to its resource.</p></section>`;
}

function pushButton(open) {
  if (STATE.push === "pushing") return `<button class="btn btn--primary pushing" disabled aria-busy="true">${ICON.push}Sending to Google Tasks…</button>`;
  if (STATE.push === "sent") return `<button class="btn" disabled>${ICON.check}Sent to Google Tasks</button>`;
  const n = open.length;
  return `<button class="btn btn--primary" data-act="push" ${n ? "" : "disabled"}>${ICON.push}Push ${n} stop${n === 1 ? "" : "s"} to Google Tasks</button>`;
}

function renderToday() {
  const tasks = activeTasks();
  const open = tasks.filter((t) => !STATE.done.has(t.id));
  const mins = tasks.reduce((n, t) => n + t.mins, 0);
  const doneStops = PATHWAY.filter((p) => p.status === "done").length;
  const pct = PATHWAY.length ? Math.round((doneStops / PATHWAY.length) * 100) : 100;
  const coming = PATHWAY.filter((p) => p.status === "next" && !tasks.some((t) => t.station === p.id)).slice(0, 4);
  const used = ["apps", "guard", "serve"].filter((l) => PATHWAY.some((p) => p.line === l));
  const lede = TARGET.live
    ? `${tasks.length} stops, ${mins} minutes, from your pathway. Each one says why it is on your list.`
    : `${tasks.length} stops, ${mins} minutes. Each one is on your list because of a dated signal.`;

  const html = `
    ${head(`Today, ${TODAY.date}`, lede, TARGET.live ? real("Your plan · real data") : synth("Synthetic plan · real signals"))}
    <section class="route-strip" aria-label="Your route">
      <div class="route-strip__head">
        <h2><span class="bullets">${used.map((l) => bullet(l)).join("")}</span>To ${esc(TARGET.role)}</h2>
        <div class="progress">${doneStops} of ${PATHWAY.length} stops done <span class="progress__bar"><i style="width:${pct}%"></i></span>${esc(TARGET.match)}</div>
      </div>
      <p class="route-key">${used.map((l) => `<b>${LINES[l].letter}</b> ${LINES[l].name}: ${LINES[l].skill}`).join(" · ")}</p>
      <div class="diagram" data-strip>${stripSVG()}</div>
    </section>
    ${serviceBand()}
    <div class="today-grid">
      <section class="timetable" aria-labelledby="tt-h">
        <div class="timetable__head"><h2 id="tt-h">Next stops <span>· ${mins} min</span></h2>${pushButton(open)}</div>
        ${tasks.map(stopRow).join("")}
        ${STATE.replan === "reverted" ? "" : TODAY.cancelled.map(cancelledRow).join("")}
      </section>
      <aside class="side">
        ${googlePanel(open)}
        <section class="panel"><h2>Coming up</h2>
          <ul class="next-list">${coming.map((p) => `<li>${bullet(p.line, true)}<span>${esc(p.title)}</span><span>Wk ${p.week}</span></li>`).join("")}</ul>
          <p style="margin-top:10px"><a href="#/pathway">See the whole route</a></p>
        </section>
      </aside>
    </div>`;

  const bind = (root) => {
    const strip = root.querySelector("[data-strip]");
    if (strip && strip.scrollWidth > strip.clientWidth) {
      const idx = PATHWAY.findIndex((p) => p.status === "current");
      strip.scrollLeft = Math.max(0, (idx / PATHWAY.length) * strip.scrollWidth - 60);
    }
    root.addEventListener("click", (e) => {
      const b = e.target.closest("[data-act]");
      if (!b) return;
      const act = b.dataset.act;
      if (act === "tick") {
        const id = b.dataset.id;
        if (STATE.done.has(id)) STATE.done.delete(id); else STATE.done.add(id);
        refreshStatus();
        rerender(`[data-id="${id}"]`);
      } else if (act === "push") {
        STATE.push = "pushing";
        rerender();
        setTimeout(() => {
          STATE.push = "sent";
          STATE.sent = activeTasks().filter((t) => !STATE.done.has(t.id));
          rerender();
          toast(`${STATE.sent.length} stops sent to Google Tasks.`, "Undo", () => { STATE.push = "idle"; rerender(); });
        }, 1100);
      } else if (act === "unpush") {
        STATE.push = "idle";
        rerender();
        toast("Removed today's list from Google Tasks.");
      } else if (act === "replan-keep") {
        STATE.replan = "kept";
        rerender();
      } else if (act === "replan-revert") {
        STATE.replan = "reverted";
        if (STATE.push === "sent") STATE.push = "idle";
        rerender();
      }
    });
  };
  return { html, bind };
}

/* ── CV & routes ───────────────────────────────────────────────── */
/* The backend reads the CV (POST /api/cv/extract), the user ticks what is right, and Save keeps the
   profile on the server (POST /api/profile/apply). STATE.saved is that profile; without it the screen
   shows the bundled sample, so the page still works opened as a file. */
const BASIS = { stated: "In your CV", implied: "Implied", suggested: "Suggested", self_reported: "Added by you" };
const QUOTE_DROPS = new Set(["QUOTE_NOT_FOUND", "PHRASE_NOT_IN_QUOTE"]);
const yearsText = (y) => (y == null ? "–" : `${y} yr`);

function llmLine(status) {
  if (status === "llm") return `Read by ${STATE.review.model}. Every quote was checked against your CV.`;
  if (status === "cached") return "A saved AI reading of this sample CV (no API key needed). Every quote was checked again.";
  return `The AI reading was not used (${status.replace("off:", "")}). These are keyword matches: tick the ones that are right.`;
}

function cvPanel() {
  if (STATE.cv === "review") {
    return `<div class="cvfile">
      <div class="cvfile__name">${ICON.file}${esc(STATE.cvFile)}</div>
      <p>${esc(llmLine(STATE.review.llm_status))}</p>
      ${STATE.review.injection_hint ? `<p class="err" role="alert">Some lines look like instructions to an AI. They were read as CV text only, and skills on them are not ticked.</p>` : ""}
      <p>Untick anything that is wrong, then save. Nothing is stored until you do.</p>
      <button class="btn btn--primary" data-act="cv-save">Save ${STATE.keep.size} skills</button>
      <button class="btn btn--quiet" data-act="cv-replace">Cancel</button>
    </div>`;
  }
  if (STATE.cv === "parsed" && STATE.saved) {
    return `<div class="cvfile">
      <div class="cvfile__name">${ICON.file}Your saved profile</div>
      <p>${STATE.saved.skills.length} skills · updated ${esc(STATE.saved.updated_at.slice(0, 10))}. Kept on Varity's server; only this browser holds the key to it.</p>
      <button class="btn" data-act="cv-replace">Read another CV</button>
      <button class="btn btn--quiet" data-act="profile-delete">Delete my profile</button>
    </div>`;
  }
  if (STATE.cv === "parsed") {
    return `<div class="cvfile">
      <div class="cvfile__name">${ICON.file}${esc(STATE.cvFile)}</div>
      <p>Read on 23 Oct · ${PROFILE.skills.length} skills found · ${PROFILE.years} of experience.</p>
      <p>${esc(PROFILE.model)}.</p>
      <button class="btn" data-act="cv-replace">Replace CV</button>
    </div>`;
  }
  if (STATE.cv === "parsing") {
    return `<div class="cvfile" aria-busy="true"><div class="cvfile__name">${ICON.file}${esc(STATE.cvFile)}</div><p>Reading your CV and quoting the evidence for each skill…</p><div class="skel" style="margin-top:14px;width:80%"></div></div>`;
  }
  const err = STATE.cv === "error" ? `<p class="err" role="alert">${esc(STATE.cvError)}</p>` : "";
  return `<div class="drop" data-drop>
      ${ICON.up}
      <strong>Drop your CV here</strong>
      <p>PDF or text, up to 5 MB and 4 pages. Use a public or synthetic CV. The file is read, not stored; only the skills you save are kept.</p>
      ${err}
      <input type="file" accept=".pdf,.txt,.md" hidden data-file>
      <button class="btn" type="button" data-act="cv-choose">Choose a file</button>
      <button class="btn btn--quiet" type="button" data-act="cv-sample">Use the synthetic sample CV</button>
    </div>`;
}

function reviewTable() {
  const r = STATE.review;
  const rows = r.rows.map((row) => `<tr>
      <td><input type="checkbox" class="keep" data-keep="${esc(row.skill_id)}" aria-label="Keep ${esc(row.name)}"${STATE.keep.has(row.skill_id) ? " checked" : ""}></td>
      <td>${esc(row.name)}</td><td><span class="lvl">${BASIS[row.basis]}</span></td>
      <td class="q">${row.quote ? `“${esc(row.why)}”` : esc(row.why)}${row.note ? `<br><span class="err">${esc(row.note)}</span>` : ""}</td>
      <td>${yearsText(row.years)}</td></tr>`).join("");
  const dropped = r.dropped.filter((d) => QUOTE_DROPS.has(d.reason));
  return `<table class="skills"><thead><tr><th scope="col">Keep</th><th scope="col">Skill</th><th scope="col">Basis</th><th scope="col">Why</th><th scope="col">Years</th></tr></thead><tbody>${rows}</tbody></table>
    ${r.interests.length ? `<p class="empty"><b>Learning, not counted as skills:</b> ${r.interests.map((i) => esc(i.name)).join(", ")}</p>` : ""}
    ${dropped.length ? `<p class="empty"><b>Dropped because the quote is not in your CV:</b> ${dropped.map((d) => esc(d.phrase)).join(", ")}</p>` : ""}`;
}

function savedTable() {
  const why = (s) => (s.evidence_quote ? `“${esc(s.evidence_quote)}”` : esc((s.evidence.find((e) => e.rule) || {}).rule || "Added by you"));
  return `<table class="skills"><thead><tr><th scope="col">Skill</th><th scope="col">Basis</th><th scope="col">Why</th><th scope="col">Years</th><th scope="col">Edit</th></tr></thead>
    <tbody>${STATE.saved.skills.map((s) => `<tr><td>${esc(s.name)}</td><td><span class="lvl">${BASIS[s.basis]}</span></td><td class="q">${why(s)}</td><td>${yearsText(s.years)}</td>
      <td><button class="btn btn--quiet" data-act="skill-remove" data-id="${esc(s.skill_id)}" aria-label="Remove ${esc(s.name)}">Remove</button></td></tr>`).join("")}</tbody></table>`;
}

function skillsTable() {
  if (STATE.cv === "review") return reviewTable();
  if (STATE.cv === "parsed" && STATE.saved) return savedTable();
  if (STATE.cv === "parsing") {
    const row = `<tr><td><div class="skel" style="width:120px"></div></td><td><div class="skel" style="width:60px"></div></td><td><div class="skel"></div></td></tr>`;
    return `<table class="skills"><tbody>${row.repeat(4)}</tbody></table>`;
  }
  if (STATE.cv !== "parsed") {
    return `<p class="empty">Your origin station appears here once a CV is read: the role you hold now, your years of experience, and each skill with the sentence from your CV that proves it.</p>`;
  }
  return `<table class="skills">
    <thead><tr><th scope="col">Skill</th><th scope="col">Level</th><th scope="col">Evidence from your CV</th></tr></thead>
    <tbody>${PROFILE.skills.map((s) => `<tr><td>${esc(s.name)}</td><td><span class="lvl">${s.level}</span></td><td class="q">“${esc(s.evidence)}”</td></tr>`).join("")}</tbody>
  </table>`;
}

function routeRow(r) {
  const cur = STATE.routeId === r.id;
  const action = cur
    ? `<span class="current-tag"><i></i>Your current route</span>`
    : `<button class="btn" data-act="route" data-id="${r.id}">Switch to this route</button>`;
  return `<div class="route${cur ? " is-current" : ""}">
    <div class="route__row">
      <div class="route__match">${r.match}%<small>match now</small></div>
      <div><div class="route__role">${esc(r.role)}</div>
        <div class="route__role-sub"><span class="bullets">${r.lines.map((l) => bullet(l, true)).join("")}</span>Outlook: ${r.outlook} (estimate)</div></div>
      <div class="route__fact"><b>${r.stops} stops</b><span>to go</span></div>
      <div class="route__fact"><b>${r.weeks}</b><span>${r.hours}</span></div>
      ${action}
    </div>
    <div class="route__gap">
      <div><h3>You already have</h3><div class="chips">${r.have.map((h) => `<span class="chip">${esc(h)}</span>`).join("")}</div></div>
      <div><h3>Skills gap</h3><div class="chips">${r.gap.map((g) => `<span class="chip chip--gap">${esc(g)}</span>`).join("")}</div></div>
    </div>
  </div>`;
}

/* Live route from GET /api/roles/suggestions. Every reason chip was written by code from a dated source;
   the AI (when used) only chose which chips to show and wrote the one-line summary. */
const CHIP_ICON = { skill_fit: "🧩", small_gap: "🎯", demand_rising: "📈", ai_boost: "⚡", watch_out: "⚠️", pays_more: "💰",
  closes_gap: "🧩", skill_rising: "📈", no_regret: "🎯" };
const SOURCE_TEXT = { profile: "your saved profile", role_forecast: "job forecast", signals: "AI signals run", resources: "verified resources",
  role_profiles: "role profiles", skill_scores: "skill scores" };
const reasonChip = (c, cls = "") => `<span class="chip reason${cls}" title="Source: ${esc(SOURCE_TEXT[c.source] || c.source)}${c.asOf ? `, ${esc(c.asOf)}` : ""}"><span aria-hidden="true">${CHIP_ICON[c.type] || "•"}</span> ${esc(c.text)}</span>`;

function liveRouteRow(r) {
  const cur = STATE.routeId === r.roleId;
  const action = cur
    ? `<span class="current-tag"><i></i>Your current route</span>`
    : `<button class="btn" data-act="route" data-id="${esc(r.roleId)}">Switch to this route</button>`;
  const outlook = r.outlook && r.outlook.label ? `Demand: ${esc(r.outlook.label)} (job forecast, ${esc(r.outlook.asOf || "")})` : "Demand: too few posts to tell";
  return `<div class="route${cur ? " is-current" : ""}">
    <div class="route__row">
      <div class="route__match">${r.matchPct}%<small>match now</small></div>
      <div><div class="route__role">#${r.rank} ${esc(r.name)}</div>
        <div class="route__role-sub"><b>${esc(r.fitLabel)}</b> · ${outlook}</div>
        ${r.summary ? `<p class="route__summary">${esc(r.summary)}</p>` : ""}</div>
      <div class="route__fact"><b>${r.gap.length} skills</b><span>to learn</span></div>
      <div class="route__fact"><b>${r.have.length} of ${r.have.length + r.gap.length}</b><span>core skills held</span></div>
      ${action}
    </div>
    <div class="route__why"><div class="chips">${r.reasons.map((c) => reasonChip(c)).join("")}${r.watchOut ? reasonChip(r.watchOut, " reason--watch") : ""}</div></div>
    <div class="route__gap">
      <div><h3>You already have</h3><div class="chips">${r.have.map((h) => `<span class="chip">${esc(h)}</span>`).join("") || "<span>None yet</span>"}</div></div>
      <div><h3>Skills gap</h3><div class="chips">${r.gap.map((g) => `<span class="chip chip--gap">${esc(g)}</span>`).join("") || "<span>No gap</span>"}</div></div>
    </div>
  </div>`;
}

function liveRoutes() {
  const s = STATE.suggest;
  const by = s.rankedBy === "llm" ? "Ranked by AI within limits, checked against the data" : "Ranked by the formula (match 70% + demand 30%)";
  const low = s.lowMatch.length ? `<p class="empty"><b>Low match, not ranked:</b> ${s.lowMatch.map((r) => `${esc(r.name)} (${r.matchPct}%)`).join(", ")}</p>` : "";
  const unmapped = s.unmappedSkills.length ? `<p class="empty"><b>Not in the job data yet, so not counted:</b> ${s.unmappedSkills.map(esc).join(", ")}</p>` : "";
  return `<p class="route-note">${by}. Skills as of ${esc(s.inputs.skillsAsOf || "–")}, job forecast as of ${esc(s.inputs.forecastAsOf || "–")}. Salary data is not available yet.</p>
    ${s.roles.length ? s.roles.map(liveRouteRow).join("") : `<p class="empty">No role matches your saved skills well yet. Add skills from another CV.</p>`}${low}${unmapped}`;
}

function stationText() {
  if (STATE.cv === "parsed" && STATE.saved) return [STATE.saved.name || "Your profile", `${STATE.saved.skills.length} skills, each with its evidence`];
  if (STATE.cv === "parsed") return [PROFILE.name, `${PROFILE.years} · read from ${STATE.cvFile}`];
  if (STATE.cv === "review") return ["Check your skills", `${STATE.review.rows.length} found in ${STATE.cvFile}`];
  return ["Origin station", "Waiting for a CV"];
}

function renderProfile() {
  const parsed = STATE.cv === "parsed";
  const [station, stationSub] = stationText();
  const html = `
    ${head("Your CV and routes", "Varity reads your CV, shows the sentence behind every skill it finds, then plans routes to roles that are rising.", STATE.suggest ? real("Real match scores") : synth(STATE.saved ? "Synthetic match scores" : "Synthetic CV and match scores"))}
    <div class="origin">
      <div>${cvPanel()}</div>
      <section aria-labelledby="org-h">
        <div class="origin-stn"><span class="origin-stn__ring" aria-hidden="true"></span><div><h2 id="org-h">${esc(station)}</h2><p>${esc(stationSub)}</p></div></div>
        ${skillsTable()}
      </section>
    </div>
    <section aria-labelledby="jp-h">
      <h2 class="sec" id="jp-h">Journey planner <small>Match = share of the role's core skills your CV already shows</small></h2>
      ${STATE.suggest && parsed
        ? `<div class="planner__from"><b>From</b> ${esc(STATE.saved.name || "your saved profile")} ${ICON.arrow} <b>To</b> the roles your skills fit best</div>${liveRoutes()}`
        : `<div class="planner__from"><b>From</b> ${parsed ? esc(PROFILE.name) : "your CV"} ${ICON.arrow} <b>To</b> three roles rising in the job forecast</div>
      ${parsed ? ROUTES.map(routeRow).join("") : `<p class="empty">Routes appear after your CV is read.</p>`}`}
    </section>`;

  const bind = (root) => {
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
        if (err instanceof TypeError && body.sample) {
          // No backend (page opened as a file): fall back to the bundled sample.
          STATE.cv = "parsed";
          STATE.cvFile = PROFILE.file;
          rerender();
          toast("Varity's server is not reachable, so this is the bundled sample CV.");
          return;
        }
        fail(err instanceof TypeError ? "Could not reach Varity's server. Try again." : err.message);
        return;
      }
      STATE.keep = new Set(STATE.review.rows.filter((r) => r.default_keep).map((r) => r.skill_id));
      STATE.cv = "review";
      rerender();
      toast("CV read. Check each skill against its quote.");
    };
    const accept = (file) => {
      if (!/\.(pdf|txt|md)$/i.test(file.name)) return fail(`“${file.name}” is not a PDF or text file. Export your CV as a PDF and try again.`);
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
        toast(err instanceof TypeError ? "Could not reach Varity's server. Try again." : err.message);
      }
    };
    root.addEventListener("change", (e) => {
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
    root.addEventListener("click", (e) => {
      const b = e.target.closest("[data-act]");
      if (!b) return;
      const act = b.dataset.act;
      if (act === "cv-replace") { STATE.cv = "empty"; STATE.review = null; rerender(); }
      else if (act === "cv-choose") fileInput.click();
      else if (act === "cv-sample") read("aina.txt (synthetic sample)", { sample: "aina" });
      else if (act === "cv-save") {
        call("/api/profile/apply", { method: "POST", body: JSON.stringify({ review_id: STATE.review.review_id, kept_ids: [...STATE.keep] }) }, (data) => {
          setProfileToken(data.token);
          STATE.saved = data.profile;
          STATE.review = null;
          STATE.cv = "parsed";
          rerender();
          toast(`Saved ${data.profile.skills.length} skills to your profile.`);
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
          STATE.routeId = "llm-app";
          applyPlan(null);
          STATE.cv = "empty";
          rerender();
          toast("Your profile was deleted.");
        });
      }
      else if (act === "route" && STATE.suggest) {
        call("/api/profile/target-role", { method: "POST", body: JSON.stringify({ roleId: b.dataset.id }) }, async (data) => {
          STATE.saved = data.profile;
          STATE.routeId = data.profile.target_role;
          STATE.done = new Set();  // ticks belong to the old route's tasks
          await loadPlan();
          location.hash = "#/pathway";
          toast(STATE.plan ? `Route switched. Your pathway now leads to ${STATE.plan.targetRole}.` : "Route saved, but the pathway could not be built.");
        });
      }
      else if (act === "route") {
        STATE.routeId = b.dataset.id;
        rerender();
        toast("Route switched. This sample shows only the LLM application engineer pathway; save your CV for real routes.");
      }
    });
  };
  return { html, bind };
}

/* ── Pathway ───────────────────────────────────────────────────── */
function renderPathway() {
  const totalMin = PATHWAY.reduce((n, p) => n + p.mins, 0);
  const weeks = [...new Set(PATHWAY.map((p) => p.week))];
  const statusText = { done: "Done", current: "You are here", next: "Upcoming" };
  const stopHTML = (p) => `<div class="pstop is-${p.status}" data-stop="${p.id}">
      ${bullet(p.line, true)}
      <div><div class="pstop__t">${esc(p.title)}<span>${p.mins} min</span></div>
        <div class="pstop__r">${ext(p.url, p.resource)}</div>
        <div class="pstop__m">${p.status === "current" ? `<span class="here-tag">You are here</span>` : `<span>${statusText[p.status]}</span>`}<span class="tag">${p.cost}</span><span class="tag">SDG ${p.sdg}</span></div>
        ${p.why ? `<p class="pstop__why">${esc(p.why)}</p>` : ""}
        ${p.reasons ? `<div class="chips">${p.reasons.map((c) => reasonChip(c)).join("")}</div>` : ""}</div>
    </div>`;
  const weekHTML = (w) => {
    const stops = PATHWAY.filter((p) => p.week === w);
    const hrs = Math.round((stops.reduce((n, p) => n + p.mins, 0) / 60) * 10) / 10;
    return `<section class="week"><h3>Week ${w} <span>${hrs} h</span></h3>${stops.map(stopHTML).join("")}</section>`;
  };

  const plan = STATE.plan;
  const badge = !plan ? synth("Synthetic pathway · real resources")
    : real(plan.personalisedBy === "llm" ? "Personalised by AI, checked against the data" : "Built by the formula from your profile");
  const lede = plan && !PATHWAY.length
    ? `You already have every core skill of ${esc(TARGET.role)}, so there is no gap to plan.`
    : `${PATHWAY.length} stops over ${weeks.length} weeks, about ${Math.round(totalMin / 60)} hours, all with free resources. Hover a station to light its line.`;
  const used = ["apps", "guard", "serve"].filter((l) => PATHWAY.some((p) => p.line === l));

  const html = `
    ${head(`Pathway to ${esc(TARGET.role)}`, lede, badge)}
    ${plan ? `<p class="route-note">${plan.hoursPerWeek} h a week from ${esc(plan.startDate)}${plan.finishDate ? ` to ${esc(plan.finishDate)}` : ""}. Skills as of ${esc(plan.skillsAsOf || "–")}. ${esc(plan.notes[0] || "")} <a href="#/profile">Change route</a></p>` : ""}
    <section class="pathmap" aria-label="Route map">
      <div class="diagram">${pathwaySVG()}</div>
      <p class="swipe-hint" style="padding:0 12px">Swipe the map sideways to see every station.</p>
      <div class="legend">
        ${used.map((l) => `<span><i class="sw-line" style="background:var(--${l})"></i>${LINES[l].name} · ${LINES[l].skill}</span>`).join("")}
        <span><i class="sw-dot sw-done"></i>Done</span>
        <span><i class="sw-dot sw-here"></i>You are here</span>
        <span><i class="sw-x"></i>Interchange: one stop on two lines</span>
      </div>
    </section>
    <div class="weeks">${weeks.map(weekHTML).join("")}</div>`;

  const bind = (root) => {
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
