/* Project and Cert stations (tasks/plan-projects-certs.md): the proof line on Pathway, the Departures timetable,
   the submit form, the jury result, certs, and the proof counts on CV & routes. Data: GET /api/proof. */

const PROOF = { data: null, error: "", open: "", busy: false, demo: null };
const STATUS_SIGN = { on_board: "IN PROGRESS", reviewing: "REVIEWING", not_yet: "NOT YET", delayed: "REVIEW DELAYED",
  hard_fail: "CHECKS FAILED", passed: "DEPARTED" };
const MARK = { pass: ["st-ok", "✓"], fail: ["st-no", "✕"], none: ["st-wait", "–"] };
const mark = (kind) => `<span class="${MARK[kind][0]}">${MARK[kind][1]}</span>`;
const CREDIT_SEEN_KEY = "varity.creditNoticeSeen";
let proofPoll;

async function loadProof() {
  PROOF.error = "";
  if (!STATE.saved || !STATE.routeId) { PROOF.data = null; return; }
  try {
    PROOF.data = await api(`/api/proof?roleId=${encodeURIComponent(STATE.routeId)}`);
  } catch (e) {
    PROOF.data = null;
    PROOF.error = errText(e);
  }
  pollIfRunning();
}

function pollIfRunning() {
  clearTimeout(proofPoll);
  if (PROOF.data && PROOF.data.mine.some((p) => p.running)) {
    proofPoll = setTimeout(async () => { await loadProof(); if (["pathway", "today"].includes(currentScreen())) rerender(); }, 3000);
  }
}

async function proofPost(path, body, done) {
  if (PROOF.busy) return;
  PROOF.busy = true;
  rerender();
  try {
    const data = await api(path, { method: "POST", body: JSON.stringify(body || {}) });
    if (data && data.mine) PROOF.data = data;
    if (done) toast(done);
  } catch (e) {
    toast(errText(e));
  }
  PROOF.busy = false;
  pollIfRunning();
  rerender();
}

const activeProject = () => PROOF.data && PROOF.data.mine.find((p) => PROOF.data.openStatuses.includes(p.status));
const catalogItem = (id) => PROOF.data && PROOF.data.projects.find((p) => p.id === id);
const matchGain = (x) => `+${Math.round(Number(x) * 100)}%`;
const LEVEL_LINE = { medium: "apps", hard: "serve" };

/* ── The proof line: starter courses → Project → Cert → the role ── */
function proofLineSVG() {
  const mine = PROOF.data.mine, active = activeProject();
  const passed = mine.some((p) => p.status === "passed");
  const certified = PROOF.data.myCerts.some((c) => c.status === "certified");
  const here = active || !passed ? "project" : !certified ? "cert" : "end";
  const coursesDone = PATHWAY.some((p) => p.status === "done");
  const stop = (x, label, sub, kind, on) => {
    const capsule = kind === "end"
      ? `<rect class="proof__cap" x="${x - 13}" y="22" width="26" height="56" rx="13"/>`
      : `<rect class="proof__cap${kind === "done" ? " proof__cap--done" : ""}" x="${x - 24}" y="38" width="48" height="24" rx="12"/>`;
    const halo = on ? `<rect class="proof__halo" x="${x - 32}" y="30" width="64" height="40" rx="20"/>` : "";
    return `<g class="proof__stop${on ? " is-here" : ""}">${halo}${capsule}
      <text x="${x}" y="100" text-anchor="middle" class="stn__label">${esc(label)}</text>
      <text x="${x}" y="116" text-anchor="middle" class="stn__sub">${esc(sub)}</text></g>`;
  };
  const credit = creditText(PROOF.data.learnedCredit);
  return `<svg viewBox="0 0 690 128" role="img" aria-label="Proof line: starter courses, project, cert, ${esc(TARGET.role)}">
    <line class="proof__track" x1="60" y1="50" x2="580" y2="50"/>
    ${stop(70, "Starter courses", coursesDone ? `Learned · ${credit} credit` : "Learned", coursesDone ? "done" : "stop", false)}
    ${stop(250, "Project", passed ? "Applied" : active ? STATUS_SIGN[active.status].toLowerCase() : "Next stop", passed ? "done" : "stop", here === "project")}
    ${stop(420, "Cert", certified ? "Certified" : "Optional", certified ? "done" : "stop", here === "cert")}
    ${stop(575, TARGET.role, "Destination", "end", here === "end")}
  </svg>`;
}

function platformSign(p, item) {
  return `<div class="platform"><span class="platform__plate">${esc(STATUS_SIGN[p.status] || "NEXT STOP")}</span><span>${esc(item ? item.title : p.id)}</span>
    ${p.unverified ? `<span class="platform__note">Unverified owner</span>` : ""}</div>`;
}

/* ── Re-plan offers use the shared service-change band (screens.js serviceBand) ── */
function replanBands() {
  const skills = [...new Set([...PROOF.data.mine, ...PROOF.data.myCerts].flatMap((x) => x.replan || []))];
  return skills.map((s) => serviceBand("Service change",
    `<p><b>1 stop offered before Project: ${esc(s)}</b></p><p>An item needs ${esc(s)}, and your route has no stop for it yet. Keep adds the stop.</p>`,
    `<button class="btn" type="button" data-proof="replan" data-skill="${esc(s)}" data-action="keep">Keep</button>
     <button class="btn" type="button" data-proof="replan" data-skill="${esc(s)}" data-action="revert">Revert</button>`)).join("");
}

/* One-time note: learned-only skills now count part of their weight (the score may have dropped). */
function creditNotice() {
  let seen = false;
  try { seen = localStorage.getItem(CREDIT_SEEN_KEY) === "1"; } catch (e) { /* no storage: show it each visit */ }
  const route = STATE.suggest && [...STATE.suggest.roles, ...STATE.suggest.lowMatch].find((r) => r.roleId === STATE.routeId);
  if (seen || !route || !(route.learnedOnly || []).length) return "";
  return serviceBand("Plan changed",
    `<p><b>Learned skills now count ${creditText(PROOF.data.learnedCredit)} until a project or cert proves them.</b></p>
     <p>${esc(route.learnedOnly.join(", "))} came from ticked tasks, so your match may be lower than before. A passed project or a verified cert gives full credit.</p>`,
    `<button class="btn" type="button" data-proof="credit-seen">Got it</button>`);
}

/* ── Jury: three stations on a short track per item ── */
function juryTrack(item, i, canDispute) {
  const votes = item.votes || [];
  const passes = votes.filter((v) => v.vote === "pass").length;
  const verdict = { pass: "majority pass", fail: "majority fail", delayed: "no majority yet" }[item.result];
  const dot = (v) => `<span class="vd vd--${v.vote}" aria-hidden="true"></span>`;
  const rows = votes.map((v) => `<li>${mark(v.vote)}<b>${esc(v.model)}</b><span>${esc(v.reason)}${v.cite ? ` <code>${esc(v.cite)}</code>` : ""}</span></li>`).join("");
  const dispute = canDispute && item.result === "fail" && !item.disputed
    ? `<details class="dispute"><summary>Disagree?</summary><form data-proof-form="dispute" data-item="${i}">
        <label>What did the jury miss? Point to the file and line.<textarea name="note" maxlength="500" required minlength="3"></textarea></label>
        <button class="btn" type="submit">Re-check this item</button></form></details>` : "";
  return `<details class="jury"><summary><span class="track">${votes.map(dot).join("")}</span>
      <span class="tally"><b>${passes} of ${votes.length}</b> pass · ${esc(verdict)}</span></summary>
    <ol>${rows}</ol><p class="jury__note">A pass counts only if code finds the quoted text on the cited line. A majority decides each item.</p></details>${dispute}`;
}

function reviewBody(r, item, jurors, canDispute) {
  const hard = r.hard.map((h) => `<li>${mark(h.ok ? "pass" : "fail")}<span>${esc(h.detail)}</span></li>`).join("");
  const n = r.items.filter((x) => x.result === "pass").length;
  const title = { passed: "Project passed", not_yet: `Not yet: ${r.items.length - n} item${r.items.length - n === 1 ? "" : "s"} to fix`,
    delayed: "Review delayed", hard_fail: "Checks failed before the review" }[r.outcome] || "";
  const stamp = r.outcome === "passed" ? `<span class="pstamp">APPLIED</span>` : r.outcome === "not_yet" ? `<span class="pstamp pstamp--ink">${n} / ${r.items.length}</span>` : "";
  const items = r.items.map((x, i) => `<li>${mark(x.result === "pass" ? "pass" : "fail")}<div><span>${esc(x.criterion)}</span>${juryTrack(x, i, canDispute)}</div></li>`).join("");
  return `<div class="review__head"><h3>${esc(title)}</h3>${stamp}</div>
    <ul class="checks">${hard}</ul>${items ? `<ul class="checks checks--items">${items}</ul>` : ""}
    ${(r.skippedFiles || []).length ? `<p class="route-note">Could not read: ${esc(r.skippedFiles.join(", "))}.</p>` : ""}
    ${r.outcome === "delayed" ? `<p class="route-note">${esc(r.error || "Not enough AI jurors answered. Nothing was passed or failed.")} Try Re-check.</p>` : ""}
    ${r.outcome === "hard_fail" ? `<p class="route-note">Fix these and submit again. The AI jury did not run, so nothing was used up.</p>` : ""}
    <p class="route-note">Graded by an LLM jury (${esc(jurors.join(", ") || "none available")}), not by a person.</p>`;
}

function reviewHTML(p, item) {
  const r = p.reviews[p.reviews.length - 1];
  if (!r) return "";
  if (p.running || r.outcome === "reviewing") {
    const hard = r.hard.map((h) => `<li>${mark(h.ok ? "pass" : "fail")}<span>${esc(h.detail)}</span></li>`).join("");
    return `<ul class="checks">${hard}<li><span class="st-wait spin" aria-hidden="true">◌</span><span>Reviewing code against your ${item.criteria.length} items<small>${esc(PROOF.data.jurors.length)} AI models vote on each item</small></span></li></ul>`;
  }
  return reviewBody(r, item, PROOF.data.jurors, r.outcome === "not_yet");
}

function consentHTML() {
  return `<form class="consent" data-proof-form="consent"><p><b>Before the first review.</b> To check each item, Varity sends the files it picks from your repo to
    ${esc(PROOF.data.jurors.join(", ") || "the AI jury")}. Only public repos can be reviewed. Nothing else from your profile is sent.
    <a href="privacy.html" target="_blank" rel="noopener">Privacy</a></p>
    <button class="btn" type="submit">I agree</button></form>`;
}

function repoField(p) {
  return `<label>Public repo link <span class="route-note">(labelled "Unverified owner")</span>
      <input name="repo" value="${esc(p.repo || "")}" placeholder="https://github.com/you/project" required></label>`;
}

function activeHTML(p) {
  const item = catalogItem(p.id) || { title: p.id, criteria: [], twist: "" };
  const crit = item.criteria.map((c) => `<li><span>${esc(c.text)} <span class="tag">${esc(c.skill)}</span></span></li>`).join("");
  const last = p.reviews[p.reviews.length - 1];
  const form = p.running ? "" : !PROOF.data.consent ? consentHTML() : `<form class="submit" data-proof-form="submit">
      ${repoField(p)}
      ${item.needsPr ? `<label>Pull request link<input name="prUrl" value="${esc(p.prUrl || "")}" placeholder="https://github.com/owner/repo/pull/123" required></label>` : ""}
      <label>Demo link (optional)<input name="demoUrl" value="${esc(p.demoUrl || "")}" placeholder="https://…" type="url"></label>
      <p class="route-note">Varity reads the code, the push history and the CI result. A repeat review needs new commits.</p>
      <p><button class="btn btn--primary" type="submit"${PROOF.busy ? " disabled" : ""}>${last ? "Re-check" : "Submit for review"}</button>
      <button class="btn btn--quiet" type="button" data-proof="abandon" data-id="${esc(p.id)}">Abandon project</button></p></form>`;
  return `<section class="proof-card">${platformSign(p, item)}
    <h3>What the review checks</h3><ol class="crit">${crit}</ol>
    ${item.twist ? `<p class="route-note"><b>Twist:</b> ${esc(item.twist)}</p>` : ""}
    ${reviewHTML(p, item)}${form}</section>`;
}

function departureRow(p) {
  const mine = PROOF.data.mine.find((m) => m.id === p.id);
  const passed = mine && mine.status === "passed";
  return `<details class="dep"${PROOF.open === p.id ? " open" : ""} data-dep="${esc(p.id)}"><summary>
      ${bullet(LEVEL_LINE[p.level] || "apps")}${passed || Math.round(p.gain * 100) >= 1 ? `<span class="dep__gain">${passed ? "Done" : `${matchGain(p.gain)}<small>match</small>`}</span>` : `<span class="dep__gain dep__gain--word">Practice<small>no new skill</small></span>`}
      <span class="dep__main"><span><b>${esc(p.title)}</b> <span class="tag">${esc(p.level)}</span></span>
        <span class="chips">${p.skills.map((s) => `<span class="chip${p.closes.includes(s) ? "" : " chip--gap"}">${esc(s)}</span>`).join("")}</span>
        <span class="pstop__why"><b>Why:</b> ${esc(p.why)} ${ext(p.source.url, p.source.label)}</span></span></summary>
    <div class="dep__body"><h3>What the review checks</h3><ol class="crit">${p.criteria.map((c) => `<li><span>${esc(c.text)}</span></li>`).join("")}</ol>
      ${p.twist ? `<p class="route-note"><b>Twist:</b> ${esc(p.twist)}</p>` : ""}
      ${passed ? `<span class="pstamp">APPLIED</span>` : `<button class="btn" type="button" data-proof="board" data-id="${esc(p.id)}"${PROOF.busy ? " disabled" : ""}>Board this project</button>`}</div></details>`;
}

function certRow(c) {
  const mine = PROOF.data.myCerts.find((m) => m.id === c.id);
  const demand = c.share == null ? "No HN count yet" : `Named in ${Number(c.mentions)} of ${Number(c.posts)} posts`;
  let action = `<button class="btn" type="button" data-proof="cert-plan" data-id="${esc(c.id)}">Add to my plan</button>`;
  if (mine && mine.status === "certified") action = `<span class="pstamp">CERTIFIED</span>`;
  else if (mine) {
    action = `<form class="cert-pass" data-proof-form="cert-passed" data-id="${esc(c.id)}">
      <input name="badgeUrl" type="url" required placeholder="https://www.credly.com/badges/…" aria-label="Credly badge link">
      <button class="btn" type="submit">I passed</button></form>
      ${mine.status === "self_reported" ? `<p class="route-note">Self-reported: ${esc(mine.detail || "")}</p>` : ""}`;
  }
  return `<div class="dep dep--cert">${Math.round(c.coverage * 100) >= 1 ? `<span class="dep__gain dep__gain--${c.coverage >= 0.75 ? "high" : c.coverage >= 0.4 ? "mid" : "low"}">${Math.round(c.coverage * 100)}%<small>covered</small></span>` : `<span class="dep__gain dep__gain--word dep__gain--new"><span class="dep__plate">All new</span><small>fresh start</small></span>`}
    <span class="dep__main"><b>${esc(c.name)}</b>
      <span class="pstop__why">${esc(demand)} · ${esc(c.issuer)} · ${ext(c.url, "Official page")}${c.adds.length ? ` · Adds stops: ${esc(c.adds.join(", "))}` : ""}</span></span>
    <span class="dep__act">${action}</span></div>`;
}

/* A stored sample review (frontend/demo-review.json), labelled synthetic: shows a full jury result with no repo. */
function demoHTML() {
  if (!PROOF.demo) return `<p><button class="btn btn--quiet" type="button" data-proof="demo">See a sample review (synthetic)</button></p>`;
  const d = PROOF.demo;
  return `<section class="proof-card proof-card--demo"><div class="platform"><span class="platform__plate">SAMPLE</span><span>${esc(d.title)}</span>
    <span class="platform__note">Synthetic · not a real review</span></div>${reviewBody(d.review, d, d.jurors, false)}</section>`;
}

function proofSection() {
  if (PROOF.error) return `<section class="proof"><h2 class="sec">Project and Cert stations</h2><p class="route-note">${esc(PROOF.error)}</p></section>`;
  const d = PROOF.data;
  if (!d) return "";
  const active = activeProject();
  const passed = d.mine.filter((p) => p.status === "passed");
  const cancelled = d.mine.filter((p) => p.status === "cancelled");
  const certsNote = d.certs.some((c) => c.share == null) ? "Rank = your syllabus coverage (no HN cert counts yet)" : "Rank = share of HN posts naming it × your syllabus coverage";
  return `<section class="proof" aria-labelledby="proof-h">
    <h2 class="sec" id="proof-h">Project and Cert stations <small>Finishing tasks is not proof. A project or a cert is.</small></h2>
    <div class="diagram proof__line">${proofLineSVG()}</div>
    <p class="route-note">Learned skills count ${creditText(d.learnedCredit)} in your match until a passed project or a verified cert proves them (an assumption, see Method).</p>
    ${creditNotice()}${replanBands()}
    ${active ? activeHTML(active) : demoHTML()}
    ${passed.map((p) => `<p class="proof-done"><span class="pstamp">APPLIED</span>${esc((catalogItem(p.id) || {}).title || p.id)} · ${esc(p.repo || "")}</p>`).join("")}
    ${cancelled.map((p) => `<p class="proof-done"><span class="stamp">Cancelled</span><s>${esc((catalogItem(p.id) || {}).title || p.id)}</s> <span class="route-note">${esc((p.cancelledAt || "").slice(0, 10))}${p.cancelReason ? ` · ${esc(p.cancelReason)}` : ""}</span></p>`).join("")}
    <h3 class="proof__h">Departures from Project <small>Ranked by how much your match rises if it passes (a formula). The Why line is written by AI and checked by code.</small></h3>
    <div class="deps">${d.projects.map(departureRow).join("") || `<p class="route-note">No projects for this role yet.</p>`}</div>
    <h3 class="proof__h">Certs for ${esc(d.roleName || TARGET.role)} <small>${esc(certsNote)}</small></h3>
    <div class="deps">${d.certs.map(certRow).join("") || `<p class="route-note">No certs listed for this role.</p>`}</div>
  </section>`;
}

function formValues(form) {
  return Object.fromEntries([...new FormData(form).entries()].map(([k, v]) => [k, String(v).trim() || null]));
}

async function proofClick(b) {
  const act = b.dataset.proof, roleId = STATE.routeId;
  if (act === "board") return proofPost("/api/proof/board", { projectId: b.dataset.id, roleId }, "On board. The checklist is on Today.");
  if (act === "abandon") return confirm("Abandon this project? It stays on your line as cancelled.") && proofPost("/api/proof/abandon", { projectId: b.dataset.id });
  if (act === "cert-plan") return proofPost("/api/proof/certs/plan", { certId: b.dataset.id, roleId }, "Cert added to your plan.");
  if (act === "replan") {
    await proofPost("/api/proof/replan", { roleId, skill: b.dataset.skill, action: b.dataset.action },
      b.dataset.action === "keep" ? `${b.dataset.skill} added to your route.` : "Kept your route. Hidden for 30 days.");
    return refreshRoutes();
  }
  if (act === "credit-seen") { try { localStorage.setItem(CREDIT_SEEN_KEY, "1"); } catch (e) { /* no storage */ } return rerender(); }
  if (act === "demo") {
    try { PROOF.demo = await (await fetch("demo-review.json")).json(); } catch (err) { toast("The sample review could not load."); }
    return rerender();
  }
}

function bindProof(root) {
  const sec = root.querySelector(".proof");
  if (!sec) return;
  sec.addEventListener("toggle", (e) => { if (e.target.matches(".dep[data-dep]") && e.target.open) PROOF.open = e.target.dataset.dep; }, true);
  sec.addEventListener("click", (e) => { const b = e.target.closest("[data-proof]"); if (b) proofClick(b); });
  sec.addEventListener("submit", async (e) => {
    const form = e.target.closest("[data-proof-form]");
    if (!form) return;
    e.preventDefault();
    const v = formValues(form), active = activeProject(), kind = form.dataset.proofForm;
    if (kind === "consent") { await proofPost("/api/proof/consent", {}); await loadProof(); rerender(); }
    else if (kind === "submit" && active) proofPost("/api/proof/submit", { projectId: active.id, ...v });
    else if (kind === "dispute" && active) proofPost("/api/proof/dispute", { projectId: active.id, item: Number(form.dataset.item), note: v.note });
    else if (kind === "cert-passed") proofPost("/api/proof/certs/passed", { certId: form.dataset.id, badgeUrl: v.badgeUrl });
  });
}

/* ── Today: the boarded project's checklist (ticks are notes in this browser; the review decides) ── */
const tickKey = (id) => `varity.proofTicks.${id}`;
const readTicks = (id) => { try { return new Set(JSON.parse(localStorage.getItem(tickKey(id)) || "[]")); } catch (e) { return new Set(); } };
function todayProofPanel() {
  const p = activeProject(), item = p && catalogItem(p.id);
  if (!item) return "";
  const ticks = readTicks(p.id);
  return `<section class="panel"><h2>On board: ${esc(item.title)}</h2>
    <ul class="next-list">${item.criteria.map((c, i) => `<li><button class="tick" type="button" data-ptick="${i}" aria-pressed="${ticks.has(i)}" aria-label="Done in my notes: ${esc(c.text)}">✓</button><span>${esc(c.text)}</span></li>`).join("")}</ul>
    <p class="route-note">Your ticks are notes. The review on Pathway decides.</p><p><a href="#/pathway">Submit on Pathway</a></p></section>`;
}
function bindTodayProof(root) {
  const p = activeProject();
  if (!p) return;
  root.querySelectorAll("[data-ptick]").forEach((b) => b.addEventListener("click", () => {
    const ticks = readTicks(p.id), i = Number(b.dataset.ptick);
    if (ticks.has(i)) ticks.delete(i); else ticks.add(i);
    try { localStorage.setItem(tickKey(p.id), JSON.stringify([...ticks])); } catch (e) { /* no storage: ticks last until reload */ }
    b.setAttribute("aria-pressed", String(ticks.has(i)));
  }));
}

/* ── CV & routes: proof counts per route, from the saved profile's evidence ── */
function proofCounts(r) {
  const levels = (r.breakdown && r.breakdown.levels) || [];
  const count = (lv) => levels.filter((x) => x.level === lv).length;
  const part = levels.filter((x) => x.credit < 1).length;
  return `<p class="route-note proof-count"><b>${count("Applied")}</b> Applied · <b>${count("Certified")}</b> Certified${part ? ` · ${part} learned only (part credit)` : ""}</p>`;
}
