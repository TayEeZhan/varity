# Upgraded CV generator: architecture

Status: built on branch `feat/cv-agent`, not merged. The agent is tested with a scripted model; the real-model
cases (`tests/cv_agent_cases.json`, `VARITY_AGENT_EVAL=1`) have not been run yet. Builds on `docs/generate-cv-plan.md`.

## Goal
Turn the one-button CV generator into a CV assistant that works like Claude Code: the user talks to an agent, the agent reads what it needs, asks clarifying questions when it is unsure, proposes a plan for big changes, and edits the CV one section at a time with the user approving each edit. The CV is shown in Jake's resume layout and downloads as a PDF.

## Features
| # | Feature | Today | After |
|---|---------|-------|-------|
| 0 | Target role bug | Generate CV fails with "pick a target role first" when the user never picked a destination | The button saves the route shown on screen, then generates |
| 18 | Jake's resume layout | Markdown only | HTML preview in Jake's layout (one column, centred header, small-caps headings with a rule, dates right-aligned) |
| 19 | XYZ bullets | Not built | Prompt rule: "Accomplished X, measured by Y, by doing Z". Y must be a number from the CV or a user answer |
| 20 | Tailor to a job ad | One target role only | Optional pasted job ad; it steers order and wording, never adds skills |
| 21 | Download as PDF | `.md` download | Browser print to PDF from the preview (selectable text, ATS-readable). No new dependency |
| 22 | Direct editing | Not built | Click any text in the preview to edit it. Works with no API key |
| 23 | CV agent | Not built | Chat panel with an agent loop (below) |
| 24 | CV notes | Not built | Saved per-user preferences ("British spelling", "one page"), loaded every session |
| 25 | "CV for:" role picker | CV only for the saved target role | Drop-down in the Generate CV panel. Defaults to the role the user's Learning Pathway is built for (the role on screen, so no saved role is needed; this also fixes #0). Picking another role changes only that CV, never the pathway. Lists only roles that have a pathway |
| 26 | Every skill on the CV | Only skills in the 40-skill taxonomy appear; others are dropped | All profile skills appear (see Skills) |
| 27 | Projects kept | Projects section lost in AI mode | Projects copied from the original CV and checked like jobs |
| 28 | Trend input | Not used | Ranked skill signals from the AI Trend Signal Layer steer order and emphasis (see Trend input) |

## Skills
- Source: every skill in the profile (the ledger), not only the taxonomy-matched ones (`service._match` returns only the 40 taxonomy skills; that stays for role matching).
- Order: the CV role's wanted skills first, then rising skills (Trend input), then the rest. Duplicates removed ignoring case.
- Grouped Jake-style (Languages / Data / Tools / Other). A skill outside the taxonomy goes under Other; nothing is dropped.
- Learned skills (pathway "Mark as learned") keep the "learned through Varity" tag. Learned skills never create experience; experience comes only from the original CV.
- Test: every profile skill appears in the generated CV.
- The 40-skill taxonomy is hand-edited and does not grow by itself. Growing it is separate work (it changes role matching and forecasts).

## Experience: copy, then rewrite
1. **Copy**: the model copies each job (title, employer, dates, bullets) and each project word for word. Code checks every copied line against the original CV, ignoring case, spaces and punctuation ("Sdn. Bhd." = "Sdn Bhd").
2. **Count check**: if a copied job or project is missing from the rewrite, code puts it back with its original bullets. No entry can disappear.
3. **Rewrite**: each new bullet carries `source`: the original bullet it rewrites. A bullet whose source is not one of the copied bullets is rejected.
4. The user sees each bullet before and after.

## Trend input
- A tool `read_skill_trends(skills)` returns at most 10 rows picked by code: skills on this CV plus the top 3–5 rising skills for the CV role.
- Each row: skill, rank, score, trend label, source, date.
- Only skill and tool signals are passed. News and event signals are left out: they say what happened, not what a person can do.
- One-line legend sent with the rows: "score = impact from the trend ranker, higher = more impact; rank 1 = highest; data as of <date>".
- Used only for order and emphasis. A trend or score never appears on the CV, and a trending skill the user does not hold is never added (the checker blocks it).

## The CV agent

### Loop
The agent runs in a tool-use loop (Anthropic SDK tool runner) on Sonnet. Each turn it may call tools until it asks the user something, proposes a plan, proposes edits, or answers. The loop stops at 15 steps per user message (cost guard), and the user can press **Just do it** to tell it to stop asking and act.

### Tools
| Tool | What it does | Claude Code equivalent |
|------|--------------|------------------------|
| `read_original_cv` | Cleaned CV text from `owner_cvs` | Reading a file |
| `read_skill_profile` | Skills, evidence, which were learned through Varity | Reading a file |
| `read_target_role` | Role name, required skills, gap | Reading a file |
| `read_job_ad` | The pasted job ad, if any | Reading a file |
| `read_current_cv` | The current structured draft (`CvDraft`) and the selected section | Reading a file |
| `ask_user` | 1–4 questions, each with options plus free text. The AI decides when and what to ask | AskUserQuestion |
| `propose_plan` | A list of changes for big requests; waits for Go / Change plan | Plan mode |
| `edit_section` | Replace one section of `CvDraft`; runs the checker; returns the before/after or why it was rejected | Edit + permission prompt |
| `save_note` | Store a lasting preference in CV notes | CLAUDE.md |

### Hallucination guards
The model will sometimes invent things, so each layer assumes the one before it can fail.

| Layer | Stops | How it is built |
|-------|-------|-----------------|
| Inputs tagged as data | Invented content, instructions hidden in a CV or job ad | CV, job ad and trend rows sent inside `<cv_data>`, `<job_ad_data>`, `<trend_data>`; closing tags stripped from the text; system rules say they are data |
| Fixed output shape | Extra sections, rambling | Every tool takes a Pydantic schema (`CvDraft`, `Edit`, `Question`); an answer that does not parse is rejected and retried once, then the step fails safely |
| Code checker | Jobs, employers, schools, dates, numbers, skills not in the CV, profile or user answers | `cv_writer.check`, run inside `edit_section`; a failure goes back to the model as "not in the CV: ask the user" |
| Bullet source | Invented bullets | Each bullet carries `source`; code checks it matches a copied original bullet |
| Claim strength | Exaggeration ("helped" → "led") | A verb list in code (helped < supported < built < led < owned); a bullet may not use a stronger verb than its source. Optional second check by a cheap model compares each bullet with its source and flags overclaims |
| `ask_user` | Guessing missing facts | The checker's rejection message tells the model to call `ask_user`; the prompt says ask when a fact is missing |
| *Added by you* | User answers mixed with CV facts | Answers stored with source `user_answer` in `owner_cv_drafts`; shown in italics in the preview; the checker accepts them |
| User approval | Anything the layers above miss | Nothing enters the draft until the user accepts the before/after |
| Sample cases | Getting worse after a prompt or model change | `tests/cv_agent_cases.json`: 10–15 requests (clear, vague, missing fact, conflicts with CV, injection in a job ad) with the expected ask / plan / edit / reject; run on every prompt or model change |

What code cannot fully stop: changes in meaning with no new name, number or verb. The user's approval is the last guard for those.

### Selecting a part
The user can click a section or bullet in the preview. The chat shows "Editing: <section>" and the selection is sent with the message, so "make this shorter" needs no guessing.

## Flow
| # | Step | Who |
|---|------|-----|
| 1 | User clicks Generate CV (target role saved first if missing) | Frontend |
| 2 | `POST /api/cv/generate` builds the first `CvDraft` (existing code + XYZ rule + optional job ad) | API, LLM, checker |
| 3 | Preview renders the draft in Jake's layout | Frontend |
| 4 | User edits directly, or types to the agent (optionally after selecting a section) | Frontend |
| 5 | `POST /api/cv/agent` (streams) runs the tool loop | API, LLM |
| 6 | Agent reads context, then asks / plans / proposes edits | LLM via tools |
| 7 | Each edit passes the checker; the user sees before/after and accepts or rejects | Code, Frontend |
| 8 | Accepted draft is saved in `owner_cv_drafts` | API |
| 9 | Download PDF prints the preview; Download .md stays | Frontend |

## Frontend

### New screen: My CV (`#/cv`)
A ninth screen, because the preview and the chat need more room than the "Take it with you" panel.

| Part | What it does |
|------|--------------|
| Top bar | **CV for:** drop-down (defaults to the Learning Pathway role, other roles with match %), optional **Paste job ad**, **Generate**, **Download PDF**, **Download .md** |
| CV preview (left) | Jake's layout. Click text to edit it directly. Click a section or bullet to select it for the agent ("Editing: Kopi Data, bullet 2"). *Added by you* facts in italics; learned skills tagged |
| Chat panel (right) | Messages, **Just do it** button |
| Question card | `ask_user`: 1–4 questions with options plus free text |
| Plan card | `propose_plan`: list of changes, **Go** / **Change plan** |
| Edit card | `edit_section`: before and after, **Accept** / **Undo** |
| States | Loading, AI off ("you can still edit and download"), no saved CV ("upload your CV again"), error, nothing generated yet |
| Print CSS | Hides everything but the CV for Download PDF |
| Phone | Preview and chat stacked, with a tab to switch |

### Existing UI that changes
| Where | Change |
|-------|--------|
| Today and Pathway, "Take it with you" | **Generate CV for this role (.md)** becomes **Open CV builder**, which opens `#/cv` with the pathway role selected |
| `app.js` `generateCv()` | Moves to the new screen and sends the chosen role (fixes #0). The quick `.md` download stays |
| Top menu | New **My CV** item |
| Delete profile | Also clears the CV draft and chat held in the browser |

### Files
- **New**: `frontend/screens-cv.js` (screen, cards, chat; same pattern as `screens-evidence.js`), `frontend/cv.css` (Jake's layout and print CSS; same pattern as `evidence.css`).
- **Updated**: `frontend/index.html` (load the new files), `frontend/app.js` (route, menu, generate call), `frontend/screens.js` (the two buttons), `frontend/styles.css` (menu item).

### Not affected
CV & routes (upload, skill review, destination, save), Flow map, Signals, Job forecast, Skills radar, Method, pathway ticks and Mark as learned. Only knock-on effect: learned skills appear in the next CV.

### Frontend risks
- Nine menu items may not fit on phones; My CV may need an overflow menu.
- Leaving mid-edit: the draft is saved on each Accept; warn before leaving with unaccepted changes.
- Accessibility: keyboard focus for chat and cards, labels, and live-region announcements for new messages.

## Data
- `owner_cvs` (exists): original cleaned CV text.
- `owner_cv_drafts` (new): `owner_key`, `draft_json` (`CvDraft` plus `added_by_user` facts), `updated_at` (ISO 8601). Deleted with the profile.
- `owner_cv_notes` (new): `owner_key`, `notes` (short list of strings), `updated_at` (ISO 8601).
- Chat history: kept in the browser for the session and sent back with each message (last 20 turns). Not stored on the server.

## Changes by file
- **Updated**: `frontend/index.html`, `frontend/app.js`, `frontend/screens.js`, `frontend/styles.css` (see Frontend), `advisor/cv_writer.py` (XYZ rule, job ad), `web/roles_api.py` (agent route), `web/accounts_store.py` (two tables).
- **New**: `frontend/screens-cv.js`, `frontend/cv.css`, `advisor/cv_agent.py` (tools and loop), `tests/test_cv_agent.py`, `tests/cv_agent_cases.json` (10–15 sample requests labelled ask / plan / edit).

## When there is no LLM
Preview, direct editing and PDF download all work. The chat panel says the assistant is off.

## Risks
- Asking too often or too rarely: measured with the sample-request cases, tuned in the prompt.
- Cost: Sonnet per step; the existing daily budget cap and per-user rate limit apply, plus the 15-step limit.
- Prompt injection from the CV or job ad: both are passed as tagged data, and edits still go through the checker.
- Personal data: drafts and notes sit behind the profile token and are deleted with the profile.

## Provider
The team is moving to Replit AI Integrations. Before building the agent, check that the chosen model supports tool use. If it does not, keep the "edit this section" chat without the agent loop.

## Build order
1. "CV for:" picker with the pathway role as default (25, fixes 0); every skill (26); copy, then rewrite, with Projects (27).
2. Jake's preview + PDF (18, 21), direct editing (22).
3. XYZ rule and job ad (19, 20).
4. Agent with read tools, `ask_user`, `edit_section` (23).
5. `propose_plan` and CV notes (24); trend input (28).

## Not building
Several templates, `.docx` export, server-side PDF rendering, chat history stored on the server.
Later add-on, separate feature: pathway tasks that suggest a project once some skills are learned.
