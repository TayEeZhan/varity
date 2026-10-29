/* My CV: the CV builder. Generate a CV for any role with a pathway (default: the Learning Pathway's role), see
   it in Jake's resume layout, edit any text directly, or ask the CV agent. The agent asks when unsure, plans big
   changes and proposes one checked edit at a time; nothing changes until you press Accept. */

const CVB = {
  loaded: false,      // GET /api/cv/draft tried for this profile
  loading: "",        // "" | draft | generate | agent
  error: "",
  roleId: "",         // the "CV for:" choice; "" = the pathway's role
  jobAd: "",
  data: null,         // {roleId, role, jobAd, draft, facts, addedByYou, markdown}
  plain: "",          // markdown when the AI was off (no structured draft)
  note: "",           // what the last Generate said (AI off, lines removed…)
  chat: [],           // {role: "user"|"assistant", text, card?}
  input: "",
  selection: "",      // "summary" | "skills" | "jobs[0].bullets" | "projects[1].bullets"
  planActive: false,
  pane: "preview",    // phone layout: preview | chat
};
const CV_OFF = { NO_KEY: "The assistant is off on this server (no AI key).", SPEND_LIMIT: "The assistant hit today's budget.",
  RATE_LIMITED: "Too many messages from here. Wait a minute.", TIMEOUT: "The assistant took too long. Try again." };
const SKILL_GROUPS = [
  ["Languages", /^(python|sql|javascript|typescript|javascript\/typescript|java|go|rust|c\+\+|c#|c|r|html|css|kotlin|swift|scala|php|ruby|bash)$/i],
  ["Data", /pandas|numpy|postgres|mysql|sqlite|mongo|spark|airflow|dbt|snowflake|bigquery|excel|matplotlib|jupyter|machine learning|statistic|data|time series|tableau|power bi|backtest|finance/i],
  ["Tools", /docker|git|kubernetes|aws|gcp|azure|linux|flask|django|fastapi|react|node|pytest|ci\/cd|terraform|unit test|rest|backend|api/i],
];

function resetCvBuilder() {
  Object.assign(CVB, { loaded: false, loading: "", error: "", roleId: "", jobAd: "", data: null, plain: "", note: "",
    chat: [], input: "", selection: "", planActive: false });
}

const cvRole = () => CVB.roleId || STATE.routeId || "";
const sectionLabel = (path) => {
  const m = /^(jobs|projects)\[(\d+)\]/.exec(path);
  if (!m || !CVB.data) return path === "skills" ? "Skills" : path === "summary" ? "Summary" : path;
  const item = CVB.data.draft[m[1]][Number(m[2])];
  return item ? `${item.title || item.name}${item.employer ? `, ${item.employer}` : ""}` : path;
};

/* ── Server calls ─────────────────────────────────────────────── */
async function loadCvDraft() {
  if (CVB.loaded || !STATE.saved) return;
  CVB.loaded = true;
  CVB.loading = "draft";
  try {
    CVB.data = await api("/api/cv/draft");
    CVB.roleId = CVB.data.roleId;
    CVB.jobAd = CVB.data.jobAd || "";
  } catch (e) {
    if (e.status !== 404) CVB.error = errText(e);
  }
  CVB.loading = "";
  if (currentScreen() === "cv") rerender();
}

async function generateCvDraft() {
  if (!cvRole()) { toast("Pick a role for this CV first."); return; }
  if (CVB.data && !confirm("Generate a new CV? Edits you made to the current one will be replaced.")) return;
  CVB.loading = "generate";
  CVB.error = "";
  rerender();
  try {
    const out = await api("/api/cv/generate", { method: "POST", body: JSON.stringify({ roleId: cvRole(), jobAd: CVB.jobAd }) });
    CVB.roleId = out.roleId;
    CVB.chat = [];
    CVB.selection = "";
    CVB.planActive = false;
    if (out.draft) {
      CVB.data = { roleId: out.roleId, role: out.role, jobAd: CVB.jobAd, draft: out.draft, facts: [], addedByYou: [], markdown: out.markdown };
      CVB.plain = "";
    } else {
      CVB.data = null;
      CVB.plain = out.markdown;
    }
    CVB.note = out.mode === "no_cv" ? "No saved CV: upload your CV again on CV & routes for a full version."
      : out.mode.startsWith("off:") ? "AI is off, so this is your original CV with an updated skills list. Edit it below, then download."
      : out.dropped.length ? `${out.dropped.length} line(s) were changed or removed because your CV does not back them.` : "";
  } catch (e) {
    CVB.error = errText(e);
  }
  CVB.loading = "";
  rerender();
}

async function saveCvDraft() {
  if (!CVB.data) return;
  try {
    const out = await api("/api/cv/draft", { method: "PUT", body: JSON.stringify({ draft: CVB.data.draft, facts: CVB.data.facts || [], addedByYou: CVB.data.addedByYou || [] }) });
    CVB.data.markdown = out.markdown;
  } catch (e) {
    toast(`Not saved: ${errText(e)}`);
  }
}

/* What the agent sees of the chat: plain text turns; cards are summed up in words. */
function chatHistory() {
  return CVB.chat.map((m) => ({ role: m.role, text: m.text })).filter((m) => m.text).slice(-20);
}

async function sendToAgent(message, justDoIt = false) {
  const text = message.trim();
  if (!text || CVB.loading) return;
  const history = chatHistory();
  CVB.chat.push({ role: "user", text: justDoIt ? `${text} (Just do it)` : text });
  CVB.input = "";
  CVB.loading = "agent";
  rerender();
  try {
    const out = await api("/api/cv/agent", { method: "POST", body: JSON.stringify({ message: text, history, selection: CVB.selection, justDoIt }) });
    CVB.chat.push(agentTurn(out));
  } catch (e) {
    CVB.chat.push({ role: "assistant", text: "", card: { type: "error", text: errText(e) } });
  }
  CVB.loading = "";
  rerender("[data-chat-input]");
}

function agentTurn(out) {
  if (out.type === "off") return { role: "assistant", text: "", card: { type: "off", text: CV_OFF[out.code] || `The assistant is off (${out.code}).` } };
  if (out.type === "ask") return { role: "assistant", text: [out.text, ...out.questions.map((q) => q.question)].filter(Boolean).join("\n"), card: { ...out, open: true } };
  if (out.type === "plan") {
    CVB.planActive = true;
    return { role: "assistant", text: `${out.text ? `${out.text}\n` : ""}Plan: ${out.steps.join("; ")}`, card: { ...out, open: true } };
  }
  if (out.type === "edit") return { role: "assistant", text: `Proposed an edit to ${sectionLabel(out.section)}. ${out.reason || ""}`.trim(), card: { ...out, open: true } };
  return { role: "assistant", text: out.text };
}

/* Apply an accepted agent edit to the draft, then save. */
function applyEdit(card) {
  const d = JSON.parse(JSON.stringify(CVB.data.draft));
  const m = /^(jobs|projects)\[(\d+)\]\.bullets$/.exec(card.section);
  if (m) d[m[1]][Number(m[2])].bullets = card.after;
  else d[card.section] = card.after;
  const added = new Set(CVB.data.addedByYou || []);
  if (card.addedByYou) added.add(card.section); else added.delete(card.section);
  CVB.data = { ...CVB.data, draft: d, addedByYou: [...added], facts: [...(CVB.data.facts || []), ...(card.facts || [])].slice(-40) };
  return saveCvDraft();
}

/* ── Direct editing: dotted paths into the draft ─────────────────── */
const step = (o, k) => o[/^\d+$/.test(k) ? Number(k) : k];
function setDraftText(path, value) {
  const d = JSON.parse(JSON.stringify(CVB.data.draft));
  const keys = path.split(".");
  const parent = keys.slice(0, -1).reduce(step, d);
  const last = keys[keys.length - 1];
  if (String(parent[last] ?? "") === value) return false;
  parent[last] = value;
  if (last === "text" && keys.includes("bullets") && !value) {  // an emptied bullet is removed
    keys.slice(0, -2).reduce(step, d).splice(Number(keys[keys.length - 2]), 1);
  }
  CVB.data = { ...CVB.data, draft: d };
  return true;
}

/* ── Rendering ─────────────────────────────────────────────────── */
const ed = (path, text, tag = "span") =>
  `<${tag} class="cv-ed" contenteditable="plaintext-only" spellcheck="true" data-path="${esc(path)}" aria-label="Edit ${esc(path)}">${esc(text || "")}</${tag}>`;
const pick = (path) => `<button type="button" class="cv-pick${CVB.selection === path ? " is-on" : ""}" data-cv="select" data-section="${esc(path)}"
  aria-pressed="${CVB.selection === path}" title="Ask the assistant about this part">${CVB.selection === path ? "Selected" : "Ask AI"}</button>`;
const mine = (path) => ((CVB.data.addedByYou || []).includes(path) ? " cv-mine" : "");

function skillGroups(skills) {
  const groups = SKILL_GROUPS.map(([name]) => [name, []]).concat([["Other", []]]);
  skills.forEach((s) => {
    const i = SKILL_GROUPS.findIndex(([, re]) => re.test(s));
    groups[i === -1 ? groups.length - 1 : i][1].push(s);
  });
  return groups.filter(([, list]) => list.length);
}

function cvDocHTML() {
  const { draft: d, role } = CVB.data;
  const learned = new Set(((STATE.saved && STATE.saved.skills) || [])
    .filter((s) => (s.evidence || []).some((e) => e.source === "pathway")).map((s) => s.name));
  const bullets = (kind, i, list) => `<ul>${list.map((b, j) => `<li>${ed(`${kind}.${i}.bullets.${j}.text`, b.text)}</li>`).join("")}</ul>`;
  const entries = (kind) => d[kind].map((x, i) => `
    <div class="cv-entry${mine(`${kind}[${i}].bullets`)}">
      <div class="cv-row">${kind === "jobs" ? `<b>${ed(`jobs.${i}.title`, x.title)}</b>`
        : `<span><b>${ed(`projects.${i}.name`, x.name)}</b>${x.tech ? ` | <i>${ed(`projects.${i}.tech`, x.tech)}</i>` : ""}</span>`}<span>${ed(`${kind}.${i}.dates`, x.dates)}</span></div>
      ${kind === "jobs" ? `<div class="cv-row"><i>${ed(`jobs.${i}.employer`, x.employer)}</i></div>` : ""}
      ${bullets(kind, i, x.bullets)}${pick(`${kind}[${i}].bullets`)}
    </div>`).join("");
  return `<article class="cvdoc" aria-label="CV preview for ${esc(role)}">
    <header class="cv-head"><h2>${ed("name", d.name || "Your name")}</h2><p>${ed("contact", d.contact)}</p></header>
    <h3>Summary ${pick("summary")}</h3><p class="cv-summary${mine("summary")}">${ed("summary", d.summary)}</p>
    ${d.jobs.length ? `<h3>Experience</h3>${entries("jobs")}` : ""}
    ${d.projects.length ? `<h3>Projects</h3>${entries("projects")}` : ""}
    ${d.education.length ? `<h3>Education</h3>${d.education.map((e, i) => `<div class="cv-entry"><div class="cv-row"><b>${ed(`education.${i}.school`, e.school)}</b><span>${ed(`education.${i}.dates`, e.dates)}</span></div><div class="cv-row"><i>${ed(`education.${i}.qualification`, e.qualification)}</i></div></div>`).join("")}` : ""}
    <h3>Technical skills ${pick("skills")}</h3>
    <div class="cv-skills${mine("skills")}">${skillGroups(d.skills).map(([g, list]) => `<p><b>${g}</b>: ${list.map((s) => (learned.has(s) ? `<span class="cv-learned" title="Learned through Varity">${esc(s)}*</span>` : esc(s))).join(", ")}</p>`).join("")}
      ${d.skills.some((s) => learned.has(s)) ? `<p class="cv-foot">* learned through Varity</p>` : ""}</div>
  </article>`;
}

function cardHTML(card, idx) {
  if (card.type === "off" || card.type === "error") return `<div class="cv-card cv-card--off" role="note">${esc(card.text)}<p>You can still edit the CV directly and download it.</p></div>`;
  const done = card.open ? "" : `<p class="cv-done">${esc(card.outcome || "")}</p>`;
  if (card.type === "ask") return `<form class="cv-card" data-cv-ask="${idx}" aria-label="Questions from the assistant">
      ${card.text ? `<p>${esc(card.text)}</p>` : ""}
      ${card.questions.map((q, qi) => `<fieldset ${card.open ? "" : "disabled"}><legend>${esc(q.question)}</legend>
        ${q.options.map((o) => `<label class="cv-opt"><input type="radio" name="q${qi}" value="${esc(o)}"> ${esc(o)}</label>`).join("")}
        <label class="cv-opt cv-opt--other">Other: <input type="text" name="o${qi}" maxlength="300" aria-label="Your own answer to: ${esc(q.question)}"></label></fieldset>`).join("")}
      ${card.open ? `<div class="cv-actions"><button class="btn btn--primary" type="submit">Answer</button></div>` : done}</form>`;
  if (card.type === "plan") return `<div class="cv-card" aria-label="Plan from the assistant">${card.text ? `<p>${esc(card.text)}</p>` : ""}<p><b>Plan</b></p><ol>${card.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
      ${card.open ? `<div class="cv-actions"><button class="btn btn--primary" type="button" data-cv="plan-go" data-idx="${idx}">Go</button>
        <button class="btn" type="button" data-cv="plan-change" data-idx="${idx}">Change plan</button></div>` : done}</div>`;
  const show = (v) => (typeof v === "string" ? `<p>${esc(v)}</p>` : `<ul>${v.map((b) => `<li>${esc(typeof b === "string" ? b : b.text)}</li>`).join("")}</ul>`);
  return `<div class="cv-card" aria-label="Proposed edit"><p><b>Edit: ${esc(sectionLabel(card.section))}</b>${card.addedByYou ? ` <i class="cv-mine">uses what you told me</i>` : ""}</p>
      ${card.reason ? `<p class="cv-hint">${esc(card.reason)}</p>` : ""}
      <div class="cv-diff"><div class="cv-before"><span>Before</span>${show(card.before)}</div><div class="cv-after"><span>After</span>${show(card.after)}</div></div>
      ${card.open ? `<div class="cv-actions"><button class="btn btn--primary" type="button" data-cv="accept" data-idx="${idx}">Accept</button>
        <button class="btn" type="button" data-cv="reject" data-idx="${idx}">Undo</button></div>` : done}</div>`;
}

function chatHTML() {
  const msgs = CVB.chat.map((m, i) => (m.card ? cardHTML(m.card, i)
    : `<p class="cv-msg cv-msg--${m.role}"><span class="visually-hidden">${m.role === "user" ? "You" : "Assistant"}: </span>${esc(m.text)}</p>`)).join("");
  const busy = CVB.loading === "agent";
  return `<section class="cv-chat" aria-labelledby="cv-chat-h">
    <h2 id="cv-chat-h">CV assistant</h2>
    <p class="cv-hint">Ask for a change, or press <b>Ask AI</b> on a part of the CV first. Nothing changes until you accept.</p>
    <div class="cv-log" role="log" aria-live="polite">${msgs || `<p class="empty">Try: “Make my summary fit this role” or “Rewrite these bullets in XYZ style”.</p>`}
      ${busy ? `<p class="cv-msg cv-msg--assistant">Thinking…</p>` : ""}</div>
    ${CVB.selection ? `<p class="cv-sel">Editing: <b>${esc(sectionLabel(CVB.selection))}</b> <button type="button" class="acct-link" data-cv="unselect">Clear</button></p>` : ""}
    <form class="cv-send" data-cv-send>
      <label for="cv-msg" class="visually-hidden">Message to the CV assistant</label>
      <textarea id="cv-msg" data-chat-input rows="3" maxlength="2000" placeholder="What should change?" ${busy ? "disabled" : ""}>${esc(CVB.input)}</textarea>
      <div class="cv-actions"><button class="btn btn--primary" type="submit" ${busy ? "disabled" : ""}>Send</button>
        <button class="btn" type="button" data-cv="justdoit" ${busy ? "disabled" : ""} title="Stop asking and make the best checked edit">Just do it</button></div>
    </form></section>`;
}

function roleOptions() {
  const s = STATE.suggest;
  if (!s) return "";
  return [...s.roles, ...s.lowMatch].map((r) => `<option value="${esc(r.roleId)}"${r.roleId === cvRole() ? " selected" : ""}>${esc(r.name)}${r.roleId === STATE.routeId ? " (your pathway)" : ""} · ${Number(r.matchPct)}% match</option>`).join("");
}

function renderCv() {
  if (!STATE.saved) {
    const html = `${head("My CV", "Upload your CV first, then build a CV for the role you want.")}
      ${STATE.loading ? `<p class="empty">Loading your profile…</p>` : `<p class="empty">No profile yet. <a href="#/profile">Go to CV &amp; routes</a></p>`}`;
    return { html, bind: () => {} };
  }
  loadCvDraft();
  const gen = CVB.loading === "generate";
  const has = !!(CVB.data || CVB.plain);
  const top = `<section class="cv-top panel" aria-label="CV settings">
      <label>CV for: <select data-cv-role ${gen ? "disabled" : ""}>${roleOptions() || `<option value="">Loading roles…</option>`}</select></label>
      <details${CVB.jobAd ? " open" : ""}><summary>Paste a job ad (optional)</summary>
        <label for="cv-ad" class="visually-hidden">Job ad</label>
        <textarea id="cv-ad" data-cv-ad rows="4" maxlength="8000" placeholder="Paste the job ad. It changes order and wording, never adds skills you do not have.">${esc(CVB.jobAd)}</textarea></details>
      <div class="cv-actions">
        <button class="btn btn--primary" type="button" data-cv="generate" ${gen ? "disabled" : ""}>${gen ? "Writing your CV…" : has ? "Generate again" : "Generate CV"}</button>
        <button class="btn" type="button" data-cv="pdf" ${has ? "" : "disabled"}>Download PDF</button>
        <button class="btn" type="button" data-cv="md" ${has ? "" : "disabled"}>Download .md</button>
      </div>
      <p class="cv-note">Choosing another role changes only this CV, never your pathway.</p>
    </section>`;
  const state = CVB.loading === "draft" ? `<p class="empty">Loading your CV…</p>`
    : CVB.error ? `<p class="empty" role="alert">${esc(CVB.error)} <button type="button" class="acct-link" data-cv="generate">Try again</button></p>`
    : !has ? `<p class="empty">Nothing generated yet. Pick a role and press <b>Generate CV</b>.</p>` : "";
  const preview = state || (CVB.data ? cvDocHTML()
    : `<article class="cvdoc cvdoc--plain" aria-label="CV preview"><pre class="cv-ed" contenteditable="plaintext-only" data-plain aria-label="Edit your CV">${esc(CVB.plain)}</pre></article>`);
  const html = `${head("My CV", "Your CV for the role you choose, in a clean one-page layout. Edit any text, or ask the assistant.",
      real("Every fact is checked against your original CV"))}
    ${top}
    ${CVB.note ? `<p class="cv-note cv-note--warn" role="status">${esc(CVB.note)}</p>` : ""}
    <div class="cv-tabs" role="tablist" aria-label="Preview or assistant">
      <button type="button" role="tab" aria-selected="${CVB.pane === "preview"}" data-cv="pane" data-pane="preview">Preview</button>
      <button type="button" role="tab" aria-selected="${CVB.pane === "chat"}" data-cv="pane" data-pane="chat">Assistant</button></div>
    <div class="cv-grid" data-pane="${CVB.pane}">
      <div class="cv-preview">${preview}</div>
      ${CVB.data ? chatHTML() : `<section class="cv-chat"><h2>CV assistant</h2><p class="empty">${CVB.plain ? "The assistant needs an AI-written CV. You can still edit and download this one." : "Generate a CV to talk to the assistant."}</p></section>`}
    </div>`;
  return { html, bind: bindCv };
}

function answerText(form, card) {
  return card.questions.map((q, qi) => {
    const other = form.querySelector(`[name="o${qi}"]`).value.trim();
    const chosen = form.querySelector(`[name="q${qi}"]:checked`);
    return `${q.question} ${other || (chosen ? chosen.value : "(no answer)")}`;
  }).join("\n");
}

function bindCv(root) {
  const log = root.querySelector(".cv-log");
  if (log) log.scrollTop = log.scrollHeight;
  root.querySelector("[data-cv-role]")?.addEventListener("change", (e) => { CVB.roleId = e.target.value; });
  root.querySelector("[data-cv-ad]")?.addEventListener("input", (e) => { CVB.jobAd = e.target.value; });
  const input = root.querySelector("[data-chat-input]");
  input?.addEventListener("input", (e) => { CVB.input = e.target.value; });
  input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendToAgent(CVB.input); }
  });
  root.querySelector("[data-cv-send]")?.addEventListener("submit", (e) => { e.preventDefault(); sendToAgent(CVB.input); });
  root.querySelectorAll("[data-cv-ask]").forEach((form) => form.addEventListener("submit", (e) => {
    e.preventDefault();
    const card = CVB.chat[Number(form.dataset.cvAsk)].card;
    const answer = answerText(form, card);
    Object.assign(card, { open: false, outcome: "Answered" });
    sendToAgent(answer);
  }));
  root.querySelector("[data-plain]")?.addEventListener("blur", (e) => { CVB.plain = e.target.innerText; });
  root.querySelectorAll(".cvdoc .cv-ed[data-path]").forEach((el) => el.addEventListener("blur", () => {
    if (setDraftText(el.dataset.path, el.innerText.trim())) saveCvDraft();
  }));
  root.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-cv]");
    if (!b) return;
    const act = b.dataset.cv;
    const card = b.dataset.idx !== undefined ? CVB.chat[Number(b.dataset.idx)].card : null;
    if (act === "generate") generateCvDraft();
    else if (act === "pdf") window.print();
    else if (act === "md") download("verity_cv.md", "text/markdown", CVB.data ? CVB.data.markdown : CVB.plain);
    else if (act === "select") { CVB.selection = CVB.selection === b.dataset.section ? "" : b.dataset.section; CVB.pane = "chat"; rerender("[data-chat-input]"); }
    else if (act === "unselect") { CVB.selection = ""; rerender("[data-chat-input]"); }
    else if (act === "pane") { CVB.pane = b.dataset.pane; rerender(); }
    else if (act === "justdoit") sendToAgent(CVB.input || "Go ahead with your best edit.", true);
    else if (act === "plan-go") { Object.assign(card, { open: false, outcome: "Approved" }); sendToAgent("Go ahead with the plan."); }
    else if (act === "plan-change") { Object.assign(card, { open: false, outcome: "Changing the plan" }); CVB.planActive = false; rerender("[data-chat-input]"); }
    else if (act === "accept") {
      Object.assign(card, { open: false, outcome: "Accepted" });
      CVB.chat.push({ role: "user", text: `I accepted the edit to ${sectionLabel(card.section)}.` });
      await applyEdit(card);
      if (CVB.planActive) sendToAgent("Accepted. Continue with the next step of the plan, if any.");
      else rerender();
    } else if (act === "reject") {
      Object.assign(card, { open: false, outcome: "Undone" });
      CVB.chat.push({ role: "user", text: `I rejected the edit to ${sectionLabel(card.section)}.` });
      rerender("[data-chat-input]");
    }
  });
}

/* An edit waiting for Accept / Undo is not saved: warn before the page is left. */
window.addEventListener("beforeunload", (e) => {
  if (CVB.chat.some((m) => m.card && m.card.type === "edit" && m.card.open)) e.preventDefault();
});
