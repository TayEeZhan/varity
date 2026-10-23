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
  const pct = Math.round((doneStops / PATHWAY.length) * 100);
  const coming = PATHWAY.filter((p) => p.status === "next" && !tasks.some((t) => t.station === p.id)).slice(0, 4);

  const html = `
    ${head(`Today, ${TODAY.date}`, `${tasks.length} stops, ${mins} minutes. Each one is on your list because of a dated signal.`, synth("Synthetic plan · real signals"))}
    <section class="route-strip" aria-label="Your route">
      <div class="route-strip__head">
        <h2><span class="bullets">${bullet("apps")}${bullet("guard")}${bullet("serve")}</span>To LLM application engineer</h2>
        <div class="progress">${doneStops} of ${PATHWAY.length} stops done <span class="progress__bar"><i style="width:${pct}%"></i></span>62% match</div>
      </div>
      <p class="route-key">${["apps", "guard", "serve"].map((l) => `<b>${LINES[l].letter}</b> ${LINES[l].name}: ${LINES[l].skill}`).join(" · ")}</p>
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
function cvPanel() {
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
      <p>PDF or DOCX, up to 5 MB. Use a public or synthetic CV: this prototype never stores files.</p>
      ${err}
      <input type="file" accept=".pdf,.docx" hidden data-file>
      <button class="btn" type="button" data-act="cv-choose">Choose a file</button>
      <button class="btn btn--quiet" type="button" data-act="cv-sample">Use the synthetic sample CV</button>
    </div>`;
}

function skillsTable() {
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

function renderProfile() {
  const parsed = STATE.cv === "parsed";
  const html = `
    ${head("Your CV and routes", "Varity reads your CV, shows the sentence behind every skill it finds, then plans routes to roles that are rising.", synth("Synthetic CV and match scores"))}
    <div class="origin">
      <div>${cvPanel()}</div>
      <section aria-labelledby="org-h">
        <div class="origin-stn"><span class="origin-stn__ring" aria-hidden="true"></span><div><h2 id="org-h">${parsed ? esc(PROFILE.name) : "Origin station"}</h2><p>${parsed ? `${PROFILE.years} · read from ${esc(STATE.cvFile)}` : "Waiting for a CV"}</p></div></div>
        ${skillsTable()}
      </section>
    </div>
    <section aria-labelledby="jp-h">
      <h2 class="sec" id="jp-h">Journey planner <small>Match = share of the role's core skills your CV already shows</small></h2>
      <div class="planner__from"><b>From</b> ${parsed ? esc(PROFILE.name) : "your CV"} ${ICON.arrow} <b>To</b> three roles rising in the job forecast</div>
      ${parsed ? ROUTES.map(routeRow).join("") : `<p class="empty">Routes appear after your CV is read.</p>`}
    </section>`;

  const bind = (root) => {
    const fileInput = root.querySelector("[data-file]");
    const drop = root.querySelector("[data-drop]");
    const parse = (name) => {
      STATE.cv = "parsing";
      STATE.cvFile = name;
      rerender();
      setTimeout(() => { STATE.cv = "parsed"; rerender(); toast("CV read. Check each skill against its quote."); }, 1200);
    };
    const accept = (file) => {
      if (!/\.(pdf|docx)$/i.test(file.name)) {
        STATE.cv = "error";
        STATE.cvError = `“${file.name}” is not a PDF or DOCX. Export your CV as a PDF and try again.`;
        rerender();
        return;
      }
      parse(file.name);
    };
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
      if (act === "cv-replace") { STATE.cv = "empty"; rerender(); }
      else if (act === "cv-choose") fileInput.click();
      else if (act === "cv-sample") parse(PROFILE.file);
      else if (act === "route") {
        STATE.routeId = b.dataset.id;
        rerender();
        toast("Route switched. In this prototype only the LLM application engineer pathway is drawn.");
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
        <div class="pstop__m">${p.status === "current" ? `<span class="here-tag">You are here</span>` : `<span>${statusText[p.status]}</span>`}<span class="tag">${p.cost}</span><span class="tag">SDG ${p.sdg}</span></div></div>
    </div>`;
  const weekHTML = (w) => {
    const stops = PATHWAY.filter((p) => p.week === w);
    const hrs = Math.round((stops.reduce((n, p) => n + p.mins, 0) / 60) * 10) / 10;
    return `<section class="week"><h3>Week ${w} <span>${hrs} h</span></h3>${stops.map(stopHTML).join("")}</section>`;
  };

  const html = `
    ${head("Pathway to LLM application engineer", `${PATHWAY.length} stops over ${weeks.length} weeks, about ${Math.round(totalMin / 60)} hours, all with free resources. Hover a station to light its line.`, synth("Synthetic pathway · real resources"))}
    <section class="pathmap" aria-label="Route map">
      <div class="diagram">${pathwaySVG()}</div>
      <p class="swipe-hint" style="padding:0 12px">Swipe the map sideways to see every station.</p>
      <div class="legend">
        <span><i class="sw-line" style="background:var(--apps)"></i>Apps line · ${LINES.apps.skill}</span>
        <span><i class="sw-line" style="background:var(--guard)"></i>Guard line · ${LINES.guard.skill}</span>
        <span><i class="sw-line" style="background:var(--serve)"></i>Serving line · ${LINES.serve.skill}</span>
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
