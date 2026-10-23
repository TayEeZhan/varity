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
  scenario: "moderate",   // moderate | fast
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

window.addEventListener("hashchange", navigate);
Promise.all([loadSignals(), loadProfile()]).finally(navigate);
