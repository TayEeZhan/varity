# Submission documents: what is left for the team

Drafted on 22 Oct 2026; updated 24 Oct 2026 for the Varity-only app (Streamlit retired, FastAPI plus a static web app). Every number comes from a file in this repository, or from the Domain 1 brief figures that Ee Zhan supplied (see "Check before you sign").

## Files to export

| Source | Export as |
|---|---|
| `docs/submission/preliminary-proposal.md` | `SDC2026_HokkienMeeIsPurple_Preliminary.pdf` |
| `docs/submission/tech-declaration.md` | `SDC2026_HokkienMeeIsPurple_TechDeclaration.pdf` |

Confirm the file-name spacing rule in the organisers' submission video. The mermaid diagram in the proposal (section 3.1) must render in the PDF. If your tool does not render it, export it as an image.

## Still [TEAM TO FILL]

### Preliminary proposal
- Section 1: leader email, leader phone, university.
- Section 3.2: any real user interviews (or delete the sentence), and the number of volunteer users for Phase 2 testing.
- Section 4: the full Hays Asia Salary Guide 2025 and MOSTI references with links (copy them from the Domain 1 brief).
- Section 5: tick the eligibility box (both members) and the workshops box (only if both members finished the GenAI, Database and Cloud workshops). Match each line to the official template wording.
- Section 6.2: licence of the chart colour values. Claude Haiku 5.5 is named; check the model ID after the first live CV run.
- Section 6.3: permission evidence (if you claim any) and any other declaration the template asks for.
- Section 7: declaration wording, signature and date.

### Tech declaration
- Section 3.2: Replit plan, region. Create the App Storage bucket and the Scheduled Deployment (code is built; setup is pending; the Varity app does not read the snapshots yet), run it once, then remove "pending" from the proposal (3.1, 3.2, diagram) and from this declaration (2.1, 3.2, 5).
- Section 4.1 and 3.2: Claude Haiku 5.5 through a direct Anthropic key is written; the route advisor is confirmed live. Confirm the CV-intake call on the deployed app, then remove "not yet confirmed" (also in the proposal, `qa-prep.md` #18 and #26, the root `README.md` and `docs/architecture.md` 3.18). Declare Jev's exact model id if you enable the ranker.
- Section 4.3: Replit Agent model (if shown), and any other AI tool either member used.
- Section 5: confirm the Replit plan; attach any extra proof of use.
- Section 7: tick "repository is public", "committee accounts added", "every AI tool declared", "workshops done", "both members can explain every part".
- Section 8: declaration wording, signature and date.

## Check before you sign
1. **Hays Asia Salary Guide 2025 (56%, 26%) and MOSTI (more than 600,000).** These figures are not in `BRIEF.md` or in the repository. The proposal quotes them from the Domain 1 brief, as a fact-check supplied them. Check the wording against the brief PDF.
2. **SDG sub-target wording** (4.4, 8.5, 8.2) is the official UN text from memory. Check it at https://sdgs.un.org/goals.
3. **Phase 2 targets** (50%, 80%, 60% of test users) are placeholders for the team to confirm or change. They are targets, not results.
4. **The four readiness boxes and the compliance checklist** follow `BRIEF.md`, because the official template text is not in the sources. Match them to the template.
5. **Prototype data and live version.** The live Replit site is published (24 Oct 2026). Open the live URL in a private window, and check that it shows the eight Varity screens with real data (no "offline snapshot" label on Job forecast or Skills radar). If it still shows the Streamlit app, the deployment is old.
6. **Replit setup.** `docs/replit-schedule.md` lists the App Storage bucket and the Scheduled Deployment as steps still to do. The documents say "code built; Replit setup pending". After you finish the setup, change those lines.
7. **Git author name and email.** 20 commits show `greenrobot8888 <(email removed)>`. The leader is named Tay Ee Zhan. The repository goes public at submission, so the personal email becomes public. `docs/build-plan.md` lists this as an open decision.
8. **AIOE licence.** The AIOE data has no licence file. `data/SOURCES.md` lists the fallback (remove the two AIOE indices).
9. **Word limits.** Counts are in the documents (updated 24 Oct for the proposal 2.2 and 3.2 and the tech declaration 2.1). Re-count after any edit. Word counters differ by a few words.
10. **Test count.** "Over 700 tests" dates from 22 Oct, before the Streamlit tests were removed. Re-run `pytest` and update the proposal 3.2, the tech declaration (2.2 and 4.3), `qa-prep.md` and the architecture if the count changed.
11. **Library licences marked (PyPI) or [TEAM TO FILL].** jinja2, apscheduler and feedparser were not installed locally, so their licences come from memory of their PyPI pages. The `typesafe-sdk` licence is not known. Check them before you sign.
12. **Leader's university.** Sheng Kuan's commit email is a (university removed) student address. Ee Zhan's university is not in any file.

## If Sheng Kuan's AI-trend-signal-layer branch is merged

- [ ] Declare Jev (TypeSafe AI, via OpenRouter) and any Claude models (Haiku, Sonnet) in the tech declaration, sections 4.1 and 5. Done for Claude Haiku 5.5 (CV intake, advisor, coach). Still open for Jev and the ranker's Sonnet use: they are off by default, and 4.1 says so.
- [ ] Declare the new data sources (RSS, arXiv, HF papers, HN, Bluesky, X API, Threads) in section 4.2 with their terms and personal-data flags.
- [x] Change every "no LLM" line: tech declaration 3.1 and 4.1, pitch row 10, qa-prep #1, #18 and #19, deck slide 7, `docs/architecture.md`, `docs/build-plan.md`, root `README.md`. The wording now says that the CV intake, an optional route advisor and an optional pathway coach use an LLM (the Streamlit `app.py` text is gone). Check that the Varity screens still read true.
- [ ] Resolve the conflict with the "we did not use X" statements (for example the X and Bluesky lines in the proposal 3.2, `docs/data-contract.md` and `docs/build-plan.md`).
- [ ] Be ready to explain the six commits that share one timestamp (22 Oct 13:13).
