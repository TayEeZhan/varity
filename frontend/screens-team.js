/* Team screen (HR / L&D): POST /api/team. Synthetic profiles in, a have/gap heatmap and a team plan out. Nothing is stored. */
const TEAM = { text: "", role: "backend_engineer", result: null, error: "", busy: false };

const parseTeam = (text) => text.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
  const i = l.indexOf(":");
  return { label: (i > 0 ? l.slice(0, i) : l).trim().slice(0, 60), skills: (i > 0 ? l.slice(i + 1) : "").split(",").map((s) => s.trim()).filter(Boolean) };
});

function teamBody(d) {
  const head = d.skills.map((s) => `<th scope="col" class="team__skill"><span>${esc(s)}</span></th>`).join("");
  const rows = d.rows.map((r) => {
    const have = new Set(r.have);
    return `<tr><th scope="row">${esc(r.label)} <small>${Number(r.matchPct)}%</small></th>${d.skills.map((s) => have.has(s)
      ? `<td class="team__have">Have</td>` : `<td class="team__gap">Gap</td>`).join("")}</tr>`;
  }).join("");
  const n = d.rows.length;
  const plan = d.teamGaps.filter((g) => g.missing > 0).map((g) =>
    `<li><b>${g.missing} of ${n} people miss ${esc(g.skill)}</b>${g.trendLabel ? ` · ${esc(g.trendLabel)}` : ""}</li>`).join("");
  return `<h2 class="sec">${esc(d.role)}: who has which skill</h2>
    <div class="team__scroll"><table class="team"><caption class="sr-only">Skills each person has or misses for ${esc(d.role)}</caption>
    <thead><tr><th scope="col">Person</th>${head}</tr></thead><tbody>${rows}</tbody></table></div>
    <h2 class="sec">Team plan</h2>${plan ? `<ol>${plan}</ol>` : `<p class="empty">Everyone holds every skill of this role.</p>`}`;
}

function renderTeam() {
  const roles = Object.entries(FORECAST.roles).map(([id, r]) => `<option value="${esc(id)}"${id === TEAM.role ? " selected" : ""}>${esc(r.name)}</option>`).join("");
  const html = `${head("Team", "Compare a team with one target role. Paste one person per line, or use the example profiles. Nothing is stored.")}
    <p class="method" role="note"><b>Synthetic profiles only. Verity supports L&amp;D decisions; it never makes hiring decisions.</b></p>
    <div class="team__form">
      <label for="team-text">One person per line: label: skill, skill</label>
      <textarea id="team-text" rows="6" maxlength="20000" data-team-text>${esc(TEAM.text)}</textarea>
      <label for="team-role">Target role</label>
      <select id="team-role" data-team-role>${roles}</select>
      <div><button class="btn btn--primary" type="button" data-team="run">Compare</button>
      <button class="btn" type="button" data-team="examples">Use the 3 example profiles</button></div>
    </div>
    <div aria-live="polite">${TEAM.error ? `<p class="err" role="alert">${esc(TEAM.error)}</p>` : ""}${TEAM.busy ? `<p class="empty">Working…</p>` : ""}${TEAM.result ? teamBody(TEAM.result) : ""}</div>`;
  const bind = (root) => {
    const text = root.querySelector("[data-team-text]");
    text.addEventListener("input", () => { TEAM.text = text.value; });
    root.querySelector("[data-team-role]").addEventListener("change", (e) => { TEAM.role = e.target.value; });
    const run = async (profiles) => {
      TEAM.error = ""; TEAM.busy = true; rerender();
      try { TEAM.result = await api("/api/team", { method: "POST", body: JSON.stringify({ profiles, roleId: TEAM.role }) }); }
      catch (e) { TEAM.result = null; TEAM.error = errText(e); }
      TEAM.busy = false; rerender();
    };
    root.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-team]");
      if (!b) return;
      if (b.dataset.team === "examples") {
        try {
          const ex = (await api("/api/profile/examples")).examples;
          TEAM.text = ex.map((p) => `${p.name}: ${p.skills.join(", ")}`).join("\n");
        } catch (err) { TEAM.error = errText(err); }
        rerender();
      } else run(parseTeam(TEAM.text));
    });
  };
  return { html, bind };
}
