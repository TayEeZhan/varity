/* Varity prototype: hash router, shared state, toast. */

const STATE = {
  done: new Set(),
  replan: "pending",      // pending | kept | reverted
  push: "idle",           // idle | pushing | sent
  sent: [],
  cv: "parsed",           // empty | parsing | review | parsed | error
  cvFile: PROFILE.file,
  cvError: "",
  review: null,           // POST /api/cv/extract result waiting for Save
  keep: new Set(),        // skill ids ticked in the review
  saved: null,            // the profile kept on the server (GET /api/profile)
  routeId: "llm-app",
  suggest: null,          // GET /api/roles/suggestions for the saved profile
  plan: null,             // GET /api/pathway for the chosen route; null = the bundled sample pathway
  forecastLive: false,    // true once GET /api/roles/forecast replaced the saved copy
  filter: "all",
  flowSel: "f7",
};

const SCREENS = {
  flow: renderFlow,
  profile: renderProfile,
  today: renderToday,
  pathway: renderPathway,
  signals: renderSignals,
  forecast: renderForecast,
};
const TITLES = { flow: "Flow map", profile: "CV & routes", today: "Today", pathway: "Pathway", signals: "Signals", forecast: "Job forecast" };
const DEFAULT_SCREEN = "today";

function currentScreen() {
  const r = location.hash.replace(/^#\/?/, "");
  return SCREENS[r] ? r : DEFAULT_SCREEN;
}

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
  document.title = `${TITLES[screen]} · Varity`;
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

/* Swap the bundled copy of the signal data for the live ranker's output. Keeps the copy if the API is
   unreachable (e.g. the page opened as a file) or has not ranked anything yet. */
async function loadSignals() {
  try {
    const res = await fetch("/api/signals", { headers: { Accept: "application/json" } });
    const body = await res.json();
    if (!res.ok || !body.success || !body.data.run || !body.data.stories.length) return;
    const { run, stories, skills } = body.data;
    Object.assign(SIGNAL_RUN, run);
    STORIES.splice(0, STORIES.length, ...stories);
    if (skills.length) SKILLS.splice(0, SKILLS.length, ...skills);
  } catch (e) {
    return;
  }
  const time = document.querySelector(".band__meta time");
  if (time && SIGNAL_RUN.generatedIso) {
    time.dateTime = SIGNAL_RUN.generatedIso;
    time.textContent = SIGNAL_RUN.generatedAt.replace(/ \d{4},/, ",");
  }
  const run = document.querySelector("[data-run-id]");
  if (run) run.textContent = SIGNAL_RUN.runId;
}

/* Swap the saved copy of the role forecast for the backend's file. Keeps the copy if the API is unreachable
   or has no forecast yet. */
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
  const token = profileToken();
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

async function loadProfile() {
  if (!profileToken()) return;
  try {
    STATE.saved = (await api("/api/profile")).profile;
  } catch (e) {
    if (e.status === 404) setProfileToken(null);  // deleted on the server; any other error keeps the key
  }
}

/* ── Routes and pathway from the saved profile ─────────────────── */
/* The bundled sample pathway, restored when the profile is deleted. */
const SAMPLE = { pathway: PATHWAY.slice(), lines: JSON.parse(JSON.stringify(LINES)), today: { ...TODAY }, target: TARGET.role, match: TARGET.match };
/* Pathway stages drawn as the three map lines (colours in styles.css). */
const STAGE_LINE = { no_regret: "apps", near_term: "serve", other: "serve", future_bet: "guard" };
const LIVE_LINES = {
  apps: { letter: "N", name: "No-regret line", skill: "skills most of your best-fit roles need" },
  serve: { letter: "D", name: "Demand line", skill: "skills job posts ask for now" },
  guard: { letter: "F", name: "Future line", skill: "rising or AI-complement skills" },
};
const DAY_MS = 86400000;

async function loadRoutes() {
  STATE.suggest = null;
  if (!STATE.saved) return;
  try {
    STATE.suggest = await api("/api/roles/suggestions");
    // No saved route yet: show the top suggestion's pathway rather than the sample.
    STATE.routeId = STATE.suggest.targetRoleId || (STATE.suggest.roles[0] || {}).roleId || null;
  } catch (e) {
    return;  // offline or no role data: the screen shows the sample routes
  }
}

async function loadPlan() {
  if (!STATE.saved || !STATE.routeId) return applyPlan(null);
  try {
    applyPlan(await api(`/api/pathway?roleId=${encodeURIComponent(STATE.routeId)}`));
  } catch (e) {
    applyPlan(null);
  }
}

/* Reload routes and pathway after the profile changed, then redraw. */
async function refreshRoutes() {
  STATE.done = new Set();  // task ids are positional, so old ticks would land on the rebuilt plan's tasks
  await loadRoutes();
  await loadPlan();
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

/* Fill PATHWAY, LINES, TODAY and TARGET (the shapes the screens draw) from GET /api/pathway, or restore the sample. */
function applyPlan(plan) {
  STATE.plan = plan;
  if (!plan) {
    PATHWAY.splice(0, PATHWAY.length, ...SAMPLE.pathway);
    Object.assign(LINES, JSON.parse(JSON.stringify(SAMPLE.lines)));
    Object.assign(TODAY, SAMPLE.today);
    Object.assign(TARGET, { role: SAMPLE.target, match: SAMPLE.match, live: false });
    return;
  }
  Object.keys(LIVE_LINES).forEach((id) => Object.assign(LINES[id], LIVE_LINES[id]));
  const start = new Date(plan.startDate).getTime();
  const gap = 920 / Math.max(plan.steps.length - 1, 1);
  const byStep = {};
  PATHWAY.splice(0, PATHWAY.length, ...plan.steps.map((s, i) => {
    const res = s.resource || {};
    const stop = {
      id: `s${s.order}`, line: STAGE_LINE[s.stage] || "serve", x: Math.round(80 + i * gap),
      week: s.startDate ? Math.floor((new Date(s.startDate).getTime() - start) / DAY_MS / 7) + 1 : "–",
      status: "next", title: s.skill, mins: s.minutes, resource: res.title || s.resourceNote, url: res.url || "#",
      cost: res.cost === "free" ? "Free" : res.cost || "–", sdg: s.sdg[0] || "–", why: s.whyForYou, reasons: s.reasons,
    };
    byStep[s.order] = { stop, step: s };
    return stop;
  }));
  refreshStatus();
  const next = plan.tasks.find((t) => !STATE.done.has(t.id));
  const day = next ? next.date : null;
  const tasks = plan.tasks.filter((t) => t.date === day).map((t) => {
    const { stop, step } = byStep[t.step];
    const chip = step.reasons[0];
    return { id: t.id, station: stop.id, line: stop.line, mins: t.minutes, title: t.title, resource: t.resourceTitle,
      url: t.resourceUrl, why: step.whyForYou || (chip ? chip.text : t.reason), source: chip ? `${SOURCE_TEXT[chip.source] || chip.source}, ${chip.asOf || "undated"}` : "Pathway" };
  });
  const label = day ? new Date(`${day}T00:00:00`).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" }) : "nothing left";
  Object.assign(TODAY, { date: label, replan: null, tasks, cancelled: [] });
  Object.assign(TARGET, { role: plan.targetRole, match: `${plan.matchPct}% match`, live: true });
}

window.addEventListener("hashchange", navigate);
Promise.all([loadSignals(), loadForecast(), loadProfile().then(loadRoutes).then(loadPlan)]).finally(navigate);
