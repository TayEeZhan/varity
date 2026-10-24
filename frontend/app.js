/* Varity: hash router, shared state, toast, API calls. Everything about the user comes from the API;
   nothing here is a sample. */

const STATE = {
  done: new Set(),
  cv: "empty",            // empty | parsing | review | parsed | error
  cvFile: "",
  cvError: "",
  review: null,           // POST /api/cv/extract result waiting for Save
  keep: new Set(),        // skill ids ticked in the review
  saved: null,            // the profile kept on the server (GET /api/profile)
  examples: [],           // GET /api/profile/examples
  loading: "",            // "" | profile | routes | plan: which call is in flight
  profileError: "",
  routeId: null,
  scenario: "moderate",   // moderate | fast: both are engine scenarios, shown as estimates
  destination: "",        // role id picked on the CV screen; "" = Not sure yet
  suggest: null,          // GET /api/roles/suggestions for the saved profile
  suggestError: "",
  plan: null,             // GET /api/pathway for the chosen route
  planError: "",
  sig: "",                // short hash of the plan's tasks; keys the ticks kept in localStorage
  signalsLive: false,     // true once GET /api/signals replaced the offline snapshot
  forecastLive: false,    // true once GET /api/roles/forecast replaced the offline snapshot
  filter: "all",
  flowSel: "f7",
};

/* Filled from GET /api/pathway by applyPlan; empty until a profile and a route exist. */
const PATHWAY = [];
const TODAY = { date: "", tasks: [] };
const TARGET = { role: "" };

const SCREENS = {
  home: renderLanding,
  how: renderHow,
  flow: renderFlow,
  profile: renderProfile,
  today: renderToday,
  pathway: renderPathway,
  signals: renderSignals,
  forecast: renderForecast,
  radar: renderRadar,
  method: renderMethod,
};
const TITLES = { home: "Varity: from CV to hired", how: "How Varity works", flow: "Flow map", profile: "CV & routes", today: "Today", pathway: "Pathway", signals: "Signals", forecast: "Job forecast", radar: "Skills radar", method: "Method" };
const DEFAULT_SCREEN = "today";

/* An explicit hash wins ("#/" is the landing). With none, a visitor with a saved profile (account or this
   browser's token) starts on Today; everyone else starts on the landing. */
function currentScreen() {
  const r = location.hash.replace(/^#\/?/, "").split("?")[0];
  if (r === "" && location.hash.startsWith("#/")) return "home";
  if (SCREENS[r]) return r;
  return hasKey() ? DEFAULT_SCREEN : "home";
}
let shownScreen = "";

/* Draw the current screen into a fresh <main> (dropping old listeners).
   `refocus` is a selector to focus afterwards, so ticking a stop keeps keyboard position. */
function rerender(refocus) {
  const old = document.getElementById("main");
  const { html, bind } = SCREENS[currentScreen()]();
  const fresh = old.cloneNode(false);
  fresh.innerHTML = html;
  old.replaceWith(fresh);
  bind(fresh);
  if (refocus) {
    const el = fresh.querySelector(refocus);
    if (el) el.focus();
  }
  return fresh;
}

function navigate() {
  const screen = currentScreen();
  document.querySelectorAll(".tabs a").forEach((a) => {
    if (a.dataset.route === screen) {
      a.setAttribute("aria-current", "page");
      a.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
    else a.removeAttribute("aria-current");
  });
  shownScreen = screen;
  document.title = screen === "home" ? TITLES.home : `${TITLES[screen]} · Varity`;
  const el = rerender();
  window.scrollTo(0, 0);
  el.focus({ preventScroll: true });
}

let toastTimer;
function toast(message, actionLabel, onAction) {
  let t = document.querySelector(".toast");
  if (!t) {
    t = document.createElement("div");
    t.className = "toast";
    t.setAttribute("role", "status");
    document.body.appendChild(t);
  }
  t.innerHTML = `<span>${esc(message)}</span>${actionLabel ? `<button type="button">${esc(actionLabel)}</button>` : ""}`;
  if (actionLabel) {
    t.querySelector("button").addEventListener("click", () => { t.classList.remove("is-on"); onAction(); });
  }
  requestAnimationFrame(() => t.classList.add("is-on"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("is-on"), 4200);
}

/* Swap the offline snapshot of the signal data for the live ranker's output. Keeps the snapshot (labelled as
   such) if the API is unreachable or has not ranked anything yet. */
async function loadSignals() {
  try {
    const res = await fetch("/api/signals", { headers: { Accept: "application/json" } });
    const body = await res.json();
    if (!res.ok || !body.success || !body.data.run || !body.data.stories.length) return;
    const { run, stories, skills } = body.data;
    Object.assign(SIGNAL_RUN, run);
    STORIES.splice(0, STORIES.length, ...stories);
    if (skills.length) SKILLS.splice(0, SKILLS.length, ...skills);
    STATE.signalsLive = true;
  } catch (e) {
    return;
  }
  const time = document.querySelector(".band__meta time");
  if (time && SIGNAL_RUN.generatedIso) {
    time.dateTime = SIGNAL_RUN.generatedIso;
    time.textContent = SIGNAL_RUN.generatedAt.replace(/ \d{4},/, ",");
    time.previousSibling.textContent = "Signals updated ";
  }
  const run = document.querySelector("[data-run-id]");
  if (run) run.textContent = SIGNAL_RUN.runId;
}

/* Swap the offline snapshot of the role forecast for the backend's file. */
async function loadForecast() {
  try {
    const res = await fetch("/api/roles/forecast", { headers: { Accept: "application/json" } });
    const body = await res.json();
    if (!res.ok || !body.success || !body.data || !body.data.roles) return;
    Object.keys(FORECAST).forEach((k) => delete FORECAST[k]);
    Object.assign(FORECAST, body.data);
    STATE.forecastLive = true;
  } catch (e) {
    return;
  }
}

/* The saved profile is reached with a random token only this browser holds. */
const TOKEN_KEY = "varity.profileToken";
function profileToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch (e) { return null; }
}
function setProfileToken(token) {
  try { token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY); } catch (e) { /* private mode: profile lasts this visit only */ }
}

/* JSON call to the backend. Throws Error(server message) on an API error and TypeError when unreachable. */
async function api(path, options = {}) {
  const token = ACCOUNT.signedIn ? null : profileToken();  // signed in: the cookie speaks for the profile
  const headers = { Accept: "application/json", "Content-Type": "application/json", ...(token ? { "X-Profile-Token": token } : {}) };
  const res = await fetch(path, { ...options, headers });
  const body = await res.json().catch(() => null);
  if (!res.ok || !body || !body.success) {
    const err = new Error((body && body.error) || `Server error (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return body.data;
}

const errText = (e) => (e instanceof TypeError ? "Could not reach Varity's server. Try again." : e.message);

async function loadExamples() {
  try { STATE.examples = (await api("/api/profile/examples")).examples; } catch (e) { STATE.examples = []; }
}

async function loadProfile() {
  STATE.profileError = "";
  if (!hasKey()) return;
  STATE.loading = "profile";
  try {
    STATE.saved = (await api("/api/profile")).profile;
    STATE.cv = "parsed";
  } catch (e) {
    if (e.status === 404) setProfileToken(null);  // deleted on the server
    else STATE.profileError = errText(e);
  }
}

/* ── Routes and pathway from the saved profile ─────────────────── */
/* Pathway stages drawn as the three map lines (colours in styles.css). */
const STAGE_LINE = { no_regret: "apps", near_term: "serve", other: "serve", future_bet: "guard" };

async function loadRoutes() {
  STATE.suggest = null;
  STATE.suggestError = "";
  STATE.routeId = null;
  if (!STATE.saved) return;
  STATE.loading = "routes";
  try {
    const s = await api(`/api/roles/suggestions?scenario=${STATE.scenario}`);
    STATE.suggest = s;
    // Only a role that has a pathway can be the route.
    const ids = new Set([...s.roles, ...s.lowMatch].map((r) => r.roleId));
    STATE.routeId = ids.has(s.targetRoleId) ? s.targetRoleId : (s.roles[0] || {}).roleId || null;
  } catch (e) {
    STATE.suggestError = errText(e);
  }
}

async function loadPlan() {
  STATE.planError = "";
  if (!STATE.saved || !STATE.routeId) return applyPlan(null);
  STATE.loading = "plan";
  try {
    applyPlan(await api(`/api/pathway?roleId=${encodeURIComponent(STATE.routeId)}&scenario=${STATE.scenario}`));
  } catch (e) {
    applyPlan(null);
    STATE.planError = errText(e);
  }
}

/* Load profile, routes and pathway one after the other, drawing after each so the page is never blank. */
async function loadMine() {
  await loadMe();
  STATE.loading = hasKey() ? "profile" : "";
  if (currentScreen() !== shownScreen) navigate();  // signed in with a profile: the bare URL means Today, not the landing
  else rerender();
  await loadProfile();
  rerender();
  await loadRoutes();
  rerender();
  await loadPlan();
  STATE.loading = "";
  rerender();
}

/* Reload routes and pathway after the profile or scenario changed, then redraw. */
async function refreshRoutes() {
  STATE.done = new Set();
  await loadRoutes();
  rerender();
  await loadPlan();
  STATE.loading = "";
  rerender();
}

function stepStatus(step, firstOpen) {
  if (step.taskIds.length && step.taskIds.every((id) => STATE.done.has(id))) return "done";
  return step === firstOpen ? "current" : "next";
}

/* Re-mark done / current / next after a tick. */
function refreshStatus() {
  if (!STATE.plan) return;
  const steps = STATE.plan.steps;
  const firstOpen = steps.find((s) => !(s.taskIds.length && s.taskIds.every((id) => STATE.done.has(id))));
  PATHWAY.forEach((p, i) => { p.status = stepStatus(steps[i], firstOpen); });
}

/* Short hash (djb2) of a string: keys the saved ticks and the calendar UIDs. */
function shortHash(text) {
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = ((h << 5) + h + text.charCodeAt(i)) >>> 0;
  return h.toString(16).padStart(8, "0");
}
const doneKey = () => `varity.done.${STATE.sig}`;
function saveDone() {
  try { localStorage.setItem(doneKey(), JSON.stringify([...STATE.done])); } catch (e) { /* ticks last this visit only */ }
  pushProgress();
}
/* Ticks also go to the server (debounced). localStorage stays the fallback; one error toast per visit. */
let progressTimer, progressWarned = false;
function pushProgress() {
  if (!STATE.saved || !STATE.sig) return;
  clearTimeout(progressTimer);
  progressTimer = setTimeout(async () => {
    const body = { signature: STATE.sig, doneIds: [...STATE.done] };
    try {
      await api("/api/profile/progress", { method: "PUT", body: JSON.stringify(body) });
      if (STATE.saved) STATE.saved.progress = { ...body, updatedAt: new Date().toISOString() };
    } catch (e) {
      if (!progressWarned) { progressWarned = true; toast("Could not save your ticks to the server. They are kept in this browser."); }
    }
  }, 500);
}
function loadDone() {
  try { return new Set(JSON.parse(localStorage.getItem(doneKey()) || "[]")); } catch (e) { return new Set(); }
}

const DAY_MS = 86400000;
const todayIso = () => new Date().toLocaleDateString("en-CA");

/* Fill PATHWAY, TODAY and TARGET (the shapes the screens draw) from GET /api/pathway, or empty them. */
function applyPlan(plan) {
  STATE.plan = plan;
  PATHWAY.length = 0;
  TODAY.date = "";
  TODAY.tasks = [];
  TARGET.role = "";
  if (!plan) { STATE.sig = ""; return; }
  STATE.sig = shortHash(plan.tasks.map((t) => `${t.id}|${t.title}|${t.date}`).join("\n"));
  const prog = STATE.saved && STATE.saved.progress;
  STATE.done = prog && prog.signature === STATE.sig && Array.isArray(prog.doneIds) ? new Set(prog.doneIds) : loadDone();
  const start = new Date(plan.startDate).getTime();
  const gap = 920 / Math.max(plan.steps.length - 1, 1);
  const byStep = {};
  PATHWAY.push(...plan.steps.map((s, i) => {
    const res = s.resource || {};
    const stop = {
      id: `s${s.order}`, line: STAGE_LINE[s.stage] || "serve", x: Math.round(80 + i * gap),
      week: s.startDate ? Math.floor((new Date(s.startDate).getTime() - start) / DAY_MS / 7) + 1 : "–",
      status: "next", title: s.skill, mins: s.minutes, resource: res.title || s.resourceNote, url: res.url || "",
      cost: res.cost === "free" ? "Free" : res.cost || "–", sdgTags: s.sdgTags, sdgReason: s.sdgReason,
      why: s.whyForYou, reasons: s.reasons,
    };
    byStep[s.order] = { stop, step: s };
    return stop;
  }));
  refreshStatus();
  const next = plan.tasks.find((t) => !STATE.done.has(t.id));
  const day = next ? next.date : null;
  TODAY.date = day ? new Date(`${day}T00:00:00`).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" }) : "nothing left";
  TODAY.day = day;
  TODAY.tasks = plan.tasks.filter((t) => t.date === day).map((t) => {
    const { stop, step } = byStep[t.step];
    const chip = step.reasons[0];
    return { id: t.id, station: stop.id, line: stop.line, mins: t.minutes, title: t.title, resource: t.resourceTitle,
      url: t.resourceUrl, why: step.whyForYou || (chip ? chip.text : t.reason), source: chip ? `${SOURCE_TEXT[chip.source] || chip.source}, ${chip.asOf || "undated"}` : "Pathway" };
  });
  TARGET.role = plan.targetRole;
}

/* ── Plan files, built here from the pathway payload (same fields as engine/pathway.py to_markdown / to_ics) ── */
function planMarkdown(p) {
  const t = p.totals;
  const lines = [
    `# Reskilling pathway: ${p.targetRole}`, "",
    `- Scenario: ${p.scenarioLabel}`,
    `- Pace: ${p.hoursPerWeek} hours a week, Monday to Friday`,
    `- Plan: ${t.steps} skills, ${t.tasks} daily tasks, about ${t.hours} hours (estimate)`,
    `- Dates: ${p.startDate} to ${p.finishDate || "n/a"}`,
    `- Skill data as of: ${p.skillsAsOf || "n/a"}`, "",
    "## Order of skills", "",
  ];
  for (const stage of p.stages) {
    lines.push(`### ${stage.label}`, "");
    const steps = p.steps.filter((s) => s.stage === stage.name);
    if (!steps.length) { lines.push("None.", ""); continue; }
    for (const s of steps) {
      const r = s.resource;
      lines.push(`${s.order}. **${s.skill}** (about ${s.minutes} min, estimate)`, `   - Why: ${s.reason}`);
      if (r) {
        const cost = r.cost + (r.hrd_corp ? ", HRD Corp-claimable" : "");
        lines.push(`   - Resource: [${r.title}](${r.url}) (${r.provider}, ${cost}, ${r.level}; link checked ${r.checked})`);
      } else lines.push(`   - Resource: ${s.resourceNote}`);
      if (s.sdg.length) lines.push(`   - SDG: ${s.sdg.join(", ")}. ${s.sdgReason || ""}`.trimEnd());
      lines.push(`   - Source: ${s.source}`);
    }
    lines.push("");
  }
  lines.push("## Daily tasks", "", "| Id | Date | Min | Task | Link |", "|---|---|---|---|---|");
  for (const k of p.tasks) lines.push(`| ${k.id} | ${k.date} | ${k.minutes} | ${k.title} | ${k.resourceUrl} |`);
  lines.push("", "## SDG links", "");
  for (const [target, n] of Object.entries(p.sdgSummary.counts)) {
    lines.push(`- SDG ${target}: ${n} step${n !== 1 ? "s" : ""} (${p.sdgSummary.skills_by_target[target].join(", ")})`);
  }
  lines.push("", p.sdgSummary.line, "", "## Notes", "");
  lines.push(...p.notes.map((n) => `- ${n}`));
  if (p.unresolved.length) {
    const note = (p.steps.find((s) => !s.resource) || {}).resourceNote;
    lines.push(`- ${note}: ${p.unresolved.join(", ")}.`);
  }
  return lines.join("\n") + "\n";
}

const icsEscape = (s) => String(s).replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r\n|\r|\n/g, "\\n");
/* Fold at 75 octets, never inside a UTF-8 character (RFC 5545 section 3.1). */
function icsFold(line) {
  const enc = new TextEncoder();
  const out = [];
  let cur = "", size = 0;
  for (const ch of line) {
    const n = enc.encode(ch).length;
    if (size + n > 75) { out.push(cur); cur = " " + ch; size = 1 + n; } else { cur += ch; size += n; }
  }
  out.push(cur);
  return out.join("\r\n");
}
const icsDay = (iso, add = 0) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + add);
  return d.toISOString().slice(0, 10).replace(/-/g, "");
};

function planIcs(p) {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Verity//Pathway E8//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
    `X-WR-CALNAME:${icsEscape("Verity reskilling plan")}`];
  for (const t of p.tasks) {
    const desc = `${t.minutes} min (estimate). Resource: ${t.resourceTitle} ${t.resourceUrl} Why: ${t.reason} Finish by ${t.date}.`;
    lines.push("BEGIN:VEVENT", `UID:${STATE.sig}-${t.id}-${t.date}@verity.pathway`, `DTSTAMP:${stamp}`,
      `DTSTART;VALUE=DATE:${icsDay(t.date)}`, `DTEND;VALUE=DATE:${icsDay(t.date, 1)}`,
      `SUMMARY:${icsEscape(t.title)}`, `DESCRIPTION:${icsEscape(desc)}`, `URL:${t.resourceUrl}`, "TRANSP:TRANSPARENT", "END:VEVENT");
  }
  lines.push("END:VCALENDAR");
  return lines.map(icsFold).join("\r\n") + "\r\n";
}

function download(name, mime, text) {
  const url = URL.createObjectURL(new Blob([text], { type: `${mime};charset=utf-8` }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/* ── Google Tasks (shown only when the server has GOOGLE_CLIENT_ID) ───────────────
   The browser asks Google for a Tasks-only token and writes the list itself. The token stays in this
   page's memory; Varity's server never sees it or the tasks. */
const GTASKS = { busy: false };
let gisLoading = null;
function loadGis() {
  gisLoading = gisLoading || new Promise((ok, no) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.onload = ok;
    s.onerror = () => { gisLoading = null; no(new Error("Could not load Google sign-in. Try again.")); };
    document.head.appendChild(s);
  });
  return gisLoading;
}
function googleToken() {
  return new Promise((ok, no) => {
    window.google.accounts.oauth2.initTokenClient({
      client_id: ACCOUNT.googleClientId,
      scope: "https://www.googleapis.com/auth/tasks",
      callback: (r) => (r.error ? no(new Error(r.error === "access_denied" ? "You did not give Varity access to Google Tasks." : "Google did not give access to Tasks.")) : ok(r.access_token)),
      error_callback: (e) => no(new Error(e && e.type === "popup_closed" ? "Google sign-in was closed before it finished."
        : e && e.type === "popup_failed_to_open" ? "Your browser blocked the Google pop-up. Allow pop-ups for this site and try again."
        : "Google could not start sign-in. Try again later.")),
    }).requestAccessToken();
  });
}
async function gtasks(token, path, method = "GET", body) {
  let res;
  try {
    res = await fetch(`https://tasks.googleapis.com/tasks/v1/${path}`, { method, body: body && JSON.stringify(body),
      headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) } });
  } catch (e) {
    throw new Error("Could not reach Google Tasks. Try again.");
  }
  if (!res.ok) throw new Error(`Google Tasks refused the request (${res.status}). Try again.`);
  return res.status === 204 ? null : res.json();
}
/* One dated list per push. New tasks go to the top unless "previous" is given, so chain them to keep the timetable order. */
async function pushToGoogleTasks(tasks) {
  await loadGis();
  const token = await googleToken();
  const list = await gtasks(token, "users/@me/lists", "POST", { title: `Varity · ${TODAY.date}` });
  try {
    let previous = "";
    for (const t of tasks) {
      const notes = [t.resource, t.url, `Why today: ${t.why} · ${t.source}`].filter(Boolean).join("\n");
      const made = await gtasks(token, `lists/${encodeURIComponent(list.id)}/tasks${previous ? `?previous=${encodeURIComponent(previous)}` : ""}`,
        "POST", { title: `${t.title} (${Number(t.mins)} min)`, notes, due: `${TODAY.day}T00:00:00.000Z` });
      previous = made.id;
    }
  } catch (err) {
    await gtasks(token, `users/@me/lists/${encodeURIComponent(list.id)}`, "DELETE").catch(() => {});  // no half-filled list left behind
    throw err;
  }
  return { ...list, token };
}
async function undoGoogleTasks(list) {
  try {
    await gtasks(list.token, `users/@me/lists/${encodeURIComponent(list.id)}`, "DELETE");
    toast("Removed the list from Google Tasks.");
  } catch (err) {
    toast(err.message);
  }
}

/* Buttons that work on any screen. */
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-global]");
  if (!b) return;
  const act = b.dataset.global;
  if (act === "signin") {
    signIn();
  } else if (act === "retry") {
    loadMine();
  } else if (act === "scenario") {
    STATE.scenario = b.dataset.value;
    refreshRoutes();
  } else if (act === "download-md" && STATE.plan) {
    download("verity_plan.md", "text/markdown", planMarkdown(STATE.plan));
  } else if (act === "download-ics" && STATE.plan) {
    download("verity_plan.ics", "text/calendar", planIcs(STATE.plan));
  } else if (act === "gtasks" && TODAY.tasks.length && !GTASKS.busy) {
    GTASKS.busy = true;
    rerender();
    try {
      const list = await pushToGoogleTasks(TODAY.tasks);
      toast(`Sent ${TODAY.tasks.length} stops to Google Tasks, list “${list.title}”.`, "Undo", () => undoGoogleTasks(list));
    } catch (err) {
      toast(err.message);
    }
    GTASKS.busy = false;
    rerender();
  } else if (act === "example") {
    if (STATE.saved && !confirm("Replace your saved profile with this synthetic example?")) return;
    try {
      const data = await api("/api/profile/example", { method: "POST", body: JSON.stringify({ id: b.dataset.id }) });
      setProfileToken(data.token);
      STATE.saved = data.profile;
      STATE.profileError = "";
      STATE.review = null;
      STATE.cv = "parsed";
      rerender();
      toast("Example profile saved. It is synthetic: no CV was read.");
      refreshRoutes();
    } catch (err) {
      toast(errText(err));
    }
  }
});

/* ── Accounts (hidden unless GET /api/me says login is configured) ─────────────── */
const ACCOUNT = { enabled: false, signedIn: false, user: null, hasProfile: false, googleClientId: "" };
/* Is there a saved profile to ask for: the account's, or one this browser holds a token for? */
const hasKey = () => (ACCOUNT.signedIn ? ACCOUNT.hasProfile : !!profileToken());

async function loadMe() {
  try {
    const d = await api("/api/me");
    Object.assign(ACCOUNT, { enabled: !!d.enabled, signedIn: !!(d.enabled && d.signedIn), user: d.user || null, hasProfile: !!d.hasProfile,
      googleClientId: d.googleClientId || "" });
  } catch (e) { /* login unavailable: no account UI */ }
  renderAcct();
}

async function signIn() {
  try {
    await api("/api/login/prepare", { method: "POST" });
  } catch (e) { toast(errText(e)); return; }
  const here = location.pathname + location.hash.replace(/\?login=failed/, "");
  location.href = `/api/login?returnTo=${encodeURIComponent(here)}`;
}

function accountChip() {
  if (!ACCOUNT.enabled) return "";
  if (ACCOUNT.signedIn) return `<p class="acct-chip acct-chip--on">Saved to your account</p>`;
  return `<p class="acct-chip">Saved for this browser <button type="button" class="acct-link" data-global="signin">Sign in to keep it</button></p>`;
}

function renderAcct() {
  const host = document.querySelector("[data-acct]");
  if (!host) return;
  host.hidden = !ACCOUNT.enabled;
  if (!ACCOUNT.enabled) { host.innerHTML = ""; return; }
  if (!ACCOUNT.signedIn) {
    host.innerHTML = `<button type="button" class="acct__in" data-global="signin">Sign in</button>`;
    return;
  }
  const u = ACCOUNT.user || {};
  const first = (u.name || u.email || "You").trim().split(/\s+/)[0];
  const img = u.imageUrl && safeUrl(u.imageUrl) !== "#" ? `<img src="${esc(safeUrl(u.imageUrl))}" alt="" referrerpolicy="no-referrer">` : "";
  host.innerHTML = `<button type="button" class="acct__btn" aria-haspopup="menu" aria-expanded="false" aria-controls="acct-menu" aria-label="Account: ${esc(first)}">
      <span class="acct__av" aria-hidden="true">${esc(first.charAt(0).toUpperCase())}${img}</span><span class="acct__name">${esc(first)}</span></button>
    <div class="acct__menu" id="acct-menu" role="menu" hidden>
      <p class="acct__who">Signed in as <b>${esc(u.email || u.name || "")}</b></p>
      <a role="menuitem" href="/api/logout">Sign out</a>
      <button type="button" role="menuitem" data-acct-delete>Delete account…</button>
    </div>`;
  const im = host.querySelector("img");
  if (im) im.addEventListener("error", () => im.remove());
  const btn = host.querySelector(".acct__btn"), menu = host.querySelector(".acct__menu");
  const setOpen = (open, refocus) => {
    menu.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
    if (open) menu.querySelector("a").focus(); else if (refocus) btn.focus();
  };
  btn.addEventListener("click", () => setOpen(menu.hidden));
  host.addEventListener("keydown", (e) => { if (e.key === "Escape" && !menu.hidden) { e.stopPropagation(); setOpen(false, true); } });
  host.addEventListener("focusout", (e) => { if (!menu.hidden && !host.contains(e.relatedTarget)) setOpen(false); });
  document.addEventListener("click", (e) => { if (!menu.hidden && !host.contains(e.target)) setOpen(false); });
  host.querySelector("[data-acct-delete]").addEventListener("click", async () => {
    setOpen(false, true);
    if (!confirm("Delete your account? This deletes your account and your saved profile from Varity's server. It cannot be undone.")) return;
    try {
      await api("/api/me", { method: "DELETE" });
      setProfileToken(null);
      location.href = "/#/profile";
      location.reload();
    } catch (err) { toast(errText(err)); }
  });
}

/* A failed sign-in returns with ?login=failed in the hash: say so once and clean the hash before routing. */
const loginFailed = /\?login=failed/.test(location.hash);
if (loginFailed) history.replaceState(null, "", location.pathname + location.search + location.hash.replace(/\?login=failed/, ""));

window.addEventListener("hashchange", navigate);
STATE.loading = profileToken() ? "profile" : "";
/* Bare URL and no browser token: an account may still hold a profile (Today, not the landing), so draw nothing until /api/me answers. */
const waitForMe = !location.hash && !profileToken();
if (!waitForMe) navigate();  // draw at once; the data arrives below
if (loginFailed) toast("Sign-in did not finish. Try again.");
loadMine();
loadSignals().then(() => rerender());
loadForecast().then(() => rerender());
loadExamples().then(() => rerender());
