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
  goal: "",               // an SDG sector id from the goal picker, or "" for any goal
  scenario: "moderate",   // moderate | fast: both are engine scenarios, shown as estimates
  destination: "",        // role id picked on the CV screen; "" = Not sure yet
  suggest: null,          // GET /api/roles/suggestions for the saved profile
  suggestError: "",
  plan: null,             // GET /api/pathway for the chosen route
  planError: "",
  sig: "",                // the plan id (its role); keys the ticks kept in localStorage and on the server
  signalsLive: false,     // true once GET /api/signals replaced the offline snapshot
  forecastLive: false,    // true once GET /api/roles/forecast replaced the offline snapshot
  filter: "all",
  flowSel: "f7",
};

/* Filled from GET /api/pathway by applyPlan; empty until a profile and a route exist. */
const PATHWAY = [];
const TODAY = { date: "", tasks: [], all: [] };
const TARGET = { role: "" };

const SCREENS = {
  home: renderLanding,
  how: renderHowTab,
  profile: renderProfile,
  today: renderToday,
  pathway: renderPathway,
  signals: renderSignals,
  forecast: renderForecast,
  radar: renderRadar,
  method: renderMethod,
  cv: renderCv,
};
const TITLES = { home: "Varity: from CV to hired", how: "How Varity works", profile: "CV & routes", today: "Today", pathway: "Pathway", signals: "Signals", forecast: "Job forecast", radar: "Skills radar", method: "Method", cv: "My CV" };
const DEFAULT_SCREEN = "today";

/* An explicit hash wins ("#/" is the landing). With none, a visitor with a saved profile (account or this
   browser's token) starts on Today; everyone else starts on the landing. */
function currentScreen() {
  const r = location.hash.replace(/^#\/?/, "").split("?")[0];
  if (r === "" && location.hash.startsWith("#/")) return "home";
  if (r === "flow") return "how";  // old Flow map links
  if (SCREENS[r]) return needsSignIn(r) ? "home" : r;
  return hasKey() || ACCOUNT.signedIn ? DEFAULT_SCREEN : "home";  // signed in, no CV yet: the app, so the CV pop-up shows
}

/* With login on, the app screens need an account; the landing, How it works and the two evidence pages it links to
   stay open. With login off (local copies, the backup demo) nothing is locked. */
const PUBLIC_SCREENS = new Set(["home", "how", "radar", "method"]);
const needsSignIn = (screen) => ACCOUNT.loaded && ACCOUNT.enabled && !ACCOUNT.signedIn && !PUBLIC_SCREENS.has(screen);
const hashScreen = () => location.hash.replace(/^#\/?/, "").split("?")[0];
let shownScreen = "";

/* Draw the current screen into a fresh <main> (dropping old listeners).
   `refocus` is a selector to focus afterwards, so ticking a stop keeps keyboard position. */
function rerender(refocus) {
  const old = document.getElementById("main");
  const screen = currentScreen();
  const { html, bind } = SCREENS[screen]();
  const fresh = old.cloneNode(false);
  fresh.innerHTML = screen === "cv" ? `<div class="cvpop__bar"><a class="btn" href="#/profile">Close</a></div>${html}` : html;
  old.replaceWith(fresh);
  bind(fresh);
  syncShell(screen);
  if (refocus) {
    const el = fresh.querySelector(refocus);
    if (el) el.focus();
  }
  return fresh;
}

/* Header nav (Home / How before a profile exists, the app tabs after), the CV-first pop-up, and the
   My CV pop-up. My CV stays its own screen so its redraws keep working; <main> is styled as a sheet
   over a still copy of CV & routes. */
const APP_SCREENS = new Set(["today", "pathway", "signals", "forecast", "radar", "method"]);
function syncShell(screen) {
  const inApp = hasKey();
  document.querySelector('[data-nav="out"]').hidden = inApp;
  document.querySelector('[data-nav="in"]').hidden = !inApp;
  if (document.querySelector("[data-acct] [data-out-only]")) document.querySelector("[data-acct]").hidden = inApp;
  document.body.classList.toggle("is-cvpop", screen === "cv");
  const behind = document.querySelector("[data-cvpop-behind]");
  if (screen === "cv" && behind.hidden) { behind.innerHTML = renderProfile().html; behind.hidden = false; }
  if (screen !== "cv" && !behind.hidden) { behind.hidden = true; behind.innerHTML = ""; }
  const gate = document.querySelector("[data-gate]");
  // Wait for /api/me so a returning account holder never sees the pop-up flash.
  const show = ACCOUNT.loaded && !inApp && !STATE.loading && APP_SCREENS.has(screen);
  if (show) {
    const opening = gate.hidden;
    gate.innerHTML = gateHtml();
    gate.hidden = false;
    if (opening) gate.querySelector("a, button").focus();
  } else if (!gate.hidden) { gate.hidden = true; gate.innerHTML = ""; }
}

/* CV first, no Close: the user reads a CV here or picks a sample. A read CV opens CV & routes for the skill
   review; the header Home link still leaves. GATE survives the pop-up's redraws. */
const GATE = { consent: false, busy: "", error: "" };
function gateHtml() {
  // Aina comes as her CV file (read like an upload), so her skills-only example is left out here.
  const samples = STATE.examples.filter((e) => e.id !== "aina").map((e) => `<button class="sample" type="button" data-global="example" data-id="${esc(e.id)}">
      <span>${esc(e.name)}<small>${esc(e.headline)} · skills only, no CV read</small></span><span class="synthetic">Synthetic</span></button>`).join("");
  const drop = GATE.busy
    ? `<div class="gdrop is-busy" aria-busy="true"><span class="gdrop__icon">${ICON.file}</span>
        <div><strong>Reading ${esc(GATE.busy)}…</strong><p>Quoting the sentence behind each skill.</p></div></div>`
    : `<div class="gdrop" data-gdrop>
        <span class="gdrop__icon">${ICON.up}</span>
        <div><strong>Drop your CV here</strong><p>PDF, Word, OpenDocument, RTF, HTML or text · up to 5 MB and 4 pages</p></div>
        <button class="btn btn--primary" type="button" data-global="gate-choose">Choose a file</button>
      </div>`;
  return `<div class="sheet sheet--cv" role="dialog" aria-modal="true" aria-labelledby="gate-h">
    <div class="sheet__head"><h2 id="gate-h">Start with your CV</h2><p>Every match, gap and task is built from it. You can replace it later.</p></div>
    <div class="sheet__body">
      ${drop}
      ${GATE.error ? `<p class="gerr" role="alert">${esc(GATE.error)}</p>` : ""}
      <label class="gconsent"><input type="checkbox" data-gate-consent${GATE.consent ? " checked" : ""}${GATE.busy ? " disabled" : ""}>
        <span>I use a sample CV, not a real person's. The text goes to Anthropic for reading. <a href="privacy.html" target="_blank" rel="noopener">Privacy notice</a><small>The file is read, not stored. Only the skills you save are kept.</small></span></label>
      <input type="file" accept=".pdf,.docx,.odt,.rtf,.html,.htm,.txt,.md" hidden data-gate-file>
      <div class="or">or use a sample</div>
      <div class="samples">
        <button class="sample" type="button" data-global="gate-sample"${GATE.busy ? " disabled" : ""}><span>Aina (synthetic)<small>Junior Python developer · her CV is read like an upload, so you see each quote</small></span><span class="synthetic">Synthetic</span></button>
        ${samples}
      </div>
    </div></div>`;
}

/* Read a CV from the pop-up. Errors stay in the pop-up; success hands the review to CV & routes. */
async function gateRead(name, body) {
  GATE.busy = name;
  GATE.error = "";
  syncShell(currentScreen());
  try {
    STATE.review = await api("/api/cv/extract", { method: "POST", body: JSON.stringify(body) });
  } catch (err) {
    GATE.busy = "";
    GATE.error = errText(err);
    syncShell(currentScreen());
    return;
  }
  GATE.busy = "";
  STATE.keep = new Set(STATE.review.rows.filter((r) => r.default_keep).map((r) => r.skill_id));
  STATE.cv = "review";
  location.hash = "#/profile";
  toast("CV read. Check each skill against its quote, then save.");
}
function gateFile(file) {
  if (!file || GATE.busy) return;
  const fail = (m) => { GATE.error = m; syncShell(currentScreen()); };
  if (!GATE.consent) return fail("Tick the box first: use a sample CV, not a real person's.");
  if (!/\.(pdf|docx|odt|rtf|html?|txt|md)$/i.test(file.name)) return fail(`“${file.name}” is not a supported file type. Export your CV as a PDF and try again.`);
  if (file.size > 5 * 1024 * 1024) return fail(`“${file.name}” is larger than 5 MB. Try a smaller file.`);
  const reader = new FileReader();
  reader.onload = () => gateRead(file.name, { file_name: file.name, file_b64: String(reader.result).split(",")[1] || "" });
  reader.onerror = () => fail(`“${file.name}” could not be opened. Try again.`);
  reader.readAsDataURL(file);
}
{
  const gate = document.querySelector("[data-gate]");  // the pop-up host stays; its inside is redrawn, so listen here
  gate.addEventListener("change", (e) => {
    if (e.target.matches("[data-gate-consent]")) { GATE.consent = e.target.checked; if (GATE.consent && /Tick the box/.test(GATE.error)) { GATE.error = ""; syncShell(currentScreen()); } }
    else if (e.target.matches("[data-gate-file]")) gateFile(e.target.files[0]);
  });
  gate.addEventListener("dragover", (e) => { const d = e.target.closest("[data-gdrop]"); if (d) { e.preventDefault(); d.classList.add("is-over"); } });
  gate.addEventListener("dragleave", (e) => { const d = e.target.closest("[data-gdrop]"); if (d) d.classList.remove("is-over"); });
  gate.addEventListener("drop", (e) => { const d = e.target.closest("[data-gdrop]"); if (d) { e.preventDefault(); gateFile(e.dataTransfer.files[0]); } });
}

function navigate() {
  const asked = hashScreen();
  if (SCREENS[asked] && needsSignIn(asked)) {
    history.replaceState(null, "", "#/");
    toast(`Sign in to open ${TITLES[asked]}: press Get started.`);
  }
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
    STATE.forecastMeta = body.meta || {};
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

/* The replay month this tab chose (sessionStorage, this tab only). Sent as asOf on the calls that serve trend data. */
const ASOF_KEY = "verity_asof";
const getAsOf = () => { try { return sessionStorage.getItem(ASOF_KEY) || ""; } catch (e) { return ""; } };
const setAsOf = (m) => { try { m ? sessionStorage.setItem(ASOF_KEY, m) : sessionStorage.removeItem(ASOF_KEY); } catch (e) { /* no storage: replay lasts until reload */ } };
const withAsOf = (path) => (getAsOf() && /^\/api\/(roles\/suggestions|pathway|skills\/radar|data\/status)/.test(path)
  ? path + (path.includes("?") ? "&" : "?") + "asOf=" + encodeURIComponent(getAsOf()) : path);

/* JSON call to the backend. Throws Error(server message) on an API error and TypeError when unreachable. */
async function api(path, options = {}) {
  const token = ACCOUNT.signedIn ? null : profileToken();  // signed in: the cookie speaks for the profile
  const headers = { Accept: "application/json", "Content-Type": "application/json", ...(token ? { "X-Profile-Token": token } : {}) };
  const res = await fetch(withAsOf(path), { ...options, headers });
  const body = await res.json().catch(() => null);
  if (!res.ok || !body || !body.success) {
    const err = new Error((body && body.error) || `Server error (${res.status})`);
    err.status = res.status;
    throw err;
  }
  if (body.meta && body.meta.malaysia) STATE.malaysia = body.meta.malaysia;  // DOSM check, shown on CV & routes
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

const goalQ = () => (STATE.goal ? `&goal=${encodeURIComponent(STATE.goal)}` : "");

let routesSeq = 0;  // a late answer for an older profile must not overwrite the newer one
async function loadRoutes() {
  const seq = ++routesSeq;
  STATE.suggest = null;
  STATE.suggestError = "";
  STATE.routeId = null;
  if (!STATE.saved) return;
  STATE.loading = "routes";
  try {
    const s = await api(`/api/roles/suggestions?scenario=${STATE.scenario}${goalQ()}`);
    if (seq !== routesSeq) return;
    STATE.suggest = s;
    // Only a role that has a pathway can be the route.
    const ids = new Set([...s.roles, ...s.lowMatch].map((r) => r.roleId));
    STATE.routeId = ids.has(s.targetRoleId) ? s.targetRoleId : (s.roles[0] || {}).roleId || null;
  } catch (e) {
    if (seq === routesSeq) STATE.suggestError = errText(e);
  }
}

async function loadPlan() {
  STATE.planError = "";
  if (!STATE.saved || !STATE.routeId) return applyPlan(null);
  STATE.loading = "plan";
  try {
    applyPlan(await api(`/api/pathway?roleId=${encodeURIComponent(STATE.routeId)}&scenario=${STATE.scenario}${goalQ()}`));
  } catch (e) {
    applyPlan(null);
    STATE.planError = errText(e);
  }
  await loadProof();  // Project and Cert stations follow the route
}

/* Keep / Revert a changed plan, or Add / Not now a trend skill (POST /api/pathway/decision). */
const DECISION_TEXT = { keep: "Plan updated.", revert: "Kept your old plan. The new skills are hidden for 30 days.",
  add: "Added to your plan.", later: "Hidden for 30 days." };
async function planDecision(action, skill) {
  try {
    applyPlan(await api("/api/pathway/decision", { method: "POST",
      body: JSON.stringify({ roleId: STATE.routeId, action, skill: skill || null, scenario: STATE.scenario }) }));
    toast(DECISION_TEXT[action]);
  } catch (e) {
    toast(errText(e));
  }
  rerender();
}

/* Every task of a skill is ticked: the user says it is learned, so it joins the profile and leaves the gap. */
async function markLearned(skill) {
  try {
    STATE.saved = (await api("/api/profile/learned", { method: "POST", body: JSON.stringify({ skill }) })).profile;
  } catch (e) {
    toast(errText(e));
    return;
  }
  toast(`${skill} is now in your profile.`);
  const kept = STATE.done;
  await refreshRoutes();  // clears ticks and gets a new planId, so put back ticks whose task is still in the plan
  if (!STATE.plan) return;
  const ids = new Set(STATE.plan.tasks.map((t) => t.id));
  STATE.done = new Set([...STATE.done, ...[...kept].filter((id) => ids.has(id))]);
  saveDone();
  refreshStatus();
  rerender();
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
  PATHWAY.forEach((p, i) => {
    p.status = stepStatus(steps[i], firstOpen);
    p.progress = steps[i].taskIds.length ? steps[i].taskIds.filter((id) => STATE.done.has(id)).length / steps[i].taskIds.length : 0;
  });
  buildToday();
}

/* Week number of a task, counted from the plan start (week 1 = first 7 days). */
function taskWeek(t) {
  return Math.floor((new Date(t.date).getTime() - new Date(STATE.plan.startDate).getTime()) / DAY_MS / 7) + 1;
}

/* Weeks unlock in order: a task can be ticked once every earlier week is done, and unticked
   only while no later week has a tick (so progress never skips a week). */
function canToggle(t) {
  const w = taskWeek(t);
  if (STATE.done.has(t.id)) return !STATE.plan.tasks.some((o) => taskWeek(o) > w && STATE.done.has(o.id));
  return STATE.plan.tasks.every((o) => taskWeek(o) >= w || STATE.done.has(o.id));
}

/* TODAY.all = every task in screen shape; TODAY.tasks = the first unfinished day (also what Google Tasks gets). */
function buildToday() {
  const plan = STATE.plan;
  const view = (t) => {
    const i = plan.steps.findIndex((s) => s.order === t.step);
    const stop = PATHWAY[i], step = plan.steps[i];
    const chip = step.reasons[0];
    return { id: t.id, station: stop.id, line: stop.line, mins: t.minutes, title: t.title, resource: t.resourceTitle,
      url: t.resourceUrl, date: t.date, week: taskWeek(t), raw: t,
      why: step.whyForYou || (chip ? chip.text : t.reason), source: chip ? `${SOURCE_TEXT[chip.source] || chip.source}, ${chip.asOf || "undated"}` : "Pathway" };
  };
  TODAY.all = plan.tasks.map(view);
  const next = plan.tasks.find((t) => !STATE.done.has(t.id));
  const day = next ? next.date : null;
  TODAY.date = day ? new Date(`${day}T00:00:00`).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" }) : "nothing left";
  TODAY.day = day;
  TODAY.tasks = TODAY.all.filter((t) => t.date === day);
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
  TODAY.all = [];
  TARGET.role = "";
  if (!plan) { STATE.sig = ""; return; }
  STATE.sig = plan.planId;  // task ids are stable per skill, so ticks survive new dates and added skills
  const prog = STATE.saved && STATE.saved.progress;
  STATE.done = prog && prog.signature === STATE.sig && Array.isArray(prog.doneIds) ? new Set(prog.doneIds) : loadDone();
  const start = new Date(plan.startDate).getTime();
  const gap = 920 / Math.max(plan.steps.length - 1, 1);
  PATHWAY.push(...plan.steps.map((s, i) => {
    const res = s.resource || {};
    const stop = {
      id: `s${s.order}`, line: STAGE_LINE[s.stage] || "serve", x: Math.round(80 + i * gap),
      week: s.startDate ? Math.floor((new Date(s.startDate).getTime() - start) / DAY_MS / 7) + 1 : "–",
      status: "next", title: s.skill, mins: s.minutes, resource: res.title || s.resourceNote, url: res.url || "",
      cost: res.cost === "free" ? "Free" : res.cost || "–", sdgTags: s.sdgTags, sdgReason: s.sdgReason, goalLinked: s.goalLinked,
      why: s.whyForYou, reasons: s.reasons, employer: s.employerFunded || null,
    };
    return stop;
  }));
  refreshStatus();
  TARGET.role = plan.targetRole;
}

const LEARNING_NOTE = "Times are for the starter course only. Job-level skill needs practice on real projects after it.";
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
document.addEventListener("change", (e) => {
  if (e.target.matches("select[data-goal]")) { STATE.goal = e.target.value; refreshRoutes(); }
});

document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-global]");
  if (!b) return;
  const act = b.dataset.global;
  if (act === "signin") {
    signIn();
  } else if (act === "gate-choose") {
    if (!GATE.consent) { GATE.error = "Tick the box first: use a sample CV, not a real person's."; syncShell(currentScreen()); }
    else document.querySelector("[data-gate-file]").click();
  } else if (act === "gate-sample") {
    gateRead("Aina's sample CV (synthetic)", { sample: "aina" });
  } else if (act === "start") {
    if (ACCOUNT.enabled && !ACCOUNT.signedIn) signIn("/#/today");  // login off (local copies): straight to the CV pop-up
    else location.hash = "#/today";
  } else if (act === "retry") {
    loadMine();
  } else if (act === "scenario") {
    STATE.scenario = b.dataset.value;
    refreshRoutes();
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
      STATE.suggest = null;  // routes belong to the old profile: hide them until the new ones load
      resetCvBuilder();
      rerender();
      toast("Example profile saved. It is synthetic: no CV was read.");
      refreshRoutes();
    } catch (err) {
      toast(errText(err));
    }
  }
});

/* ── Accounts (hidden unless GET /api/me says login is configured) ─────────────── */
const ACCOUNT = { loaded: false, enabled: false, signedIn: false, user: null, hasProfile: false, googleClientId: "" };
/* Is there a saved profile to ask for: the account's, or one this browser holds a token for? */
// Signed in: /api/me's answer at load, or a profile saved since (an account save returns no token).
const hasKey = () => (ACCOUNT.signedIn ? ACCOUNT.hasProfile || !!STATE.saved : !!profileToken());

async function loadMe() {
  try {
    const d = await api("/api/me");
    Object.assign(ACCOUNT, { enabled: !!d.enabled, signedIn: !!(d.enabled && d.signedIn), user: d.user || null, hasProfile: !!d.hasProfile,
      googleClientId: d.googleClientId || "" });
  } catch (e) { /* login unavailable: no account UI */ }
  ACCOUNT.loaded = true;
  renderAcct();
}

async function signIn(returnTo) {
  try {
    await api("/api/login/prepare", { method: "POST" });
  } catch (e) { toast(errText(e)); return; }
  const here = returnTo || location.pathname + location.hash.replace(/\?login=failed/, "");
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
  host.hidden = false;
  if (!ACCOUNT.enabled) {  // login off (local copies): Sign in opens the CV pop-up, like Get started
    host.innerHTML = `<button type="button" class="acct__in" data-global="start" data-out-only>Sign in</button>`;
    host.hidden = hasKey();
    return;
  }
  if (!ACCOUNT.signedIn) {
    host.innerHTML = `<button type="button" class="acct__in" data-global="start">Sign in</button>`;  // then Today, or the CV pop-up
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
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (currentScreen() === "cv") location.hash = "#/profile";
});
STATE.loading = profileToken() ? "profile" : "";
/* Bare URL and no browser token: an account may still hold a profile (Today, not the landing), so draw nothing until /api/me answers. */
const waitForMe = (!location.hash && !profileToken()) || !PUBLIC_SCREENS.has(hashScreen() || "home");  // an app screen: check sign-in first
if (!waitForMe) navigate();  // draw at once; the data arrives below
if (loginFailed) toast("Sign-in did not finish. Try again.");
loadMine();
loadSignals().then(() => rerender());
loadForecast().then(() => rerender());
loadExamples().then(() => rerender());
loadDataStatus().then(() => rerender());
