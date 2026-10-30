# CV layout upgrade: plan

Goal: the CV builder's page and its Download PDF look like a clean one-page resume
(centred name, spaced-capital section titles with a full-width line, organisation and dates
on one row, role in italics underneath), and can show Leadership and Achievements when the
user's own CV has them.

Reference: the mock `cv-after-change.pdf` (Wei Jie Tan) and the user's UM resume.

## Phase 1: layout (frontend only)

| File | Change |
|---|---|
| `frontend/cv.css` | Lato font; centred spaced-capital name; contact line split by `•`; section titles in spaced capitals with a full-width rule; tighter print spacing for one A4 page. |
| `frontend/screens-cv.js` `cvDocHTML()` | Entry order: organisation (bold) + dates (italic, right), then role/degree (italic), then bullets. Section order: Summary, Education, Experience, Projects, Leadership, Technical Skills, Achievements. Editing, Ask AI and "added by you" marks unchanged. |
| `frontend/index.html` | Add Lato to the Google Fonts link; bump `cv.css` and `screens-cv.js` versions. |

Affects: how the CV looks on My CV and in the PDF. No backend, AI, checker or test change.
Old saved drafts render in the new style.

## Phase 2: Leadership, Achievements, Education bullets (only when the CV has them)

Rule: these sections are copied from the user's original CV only. If the CV has none,
the section is empty and is not shown. The AI never creates them.

| File | Change |
|---|---|
| `backend/signals/advisor/cv_writer.py` | `CvDraft` gets `leadership: list[Job]` and `achievements: list[str]` (default empty), and `Education` gets `details: list[str]` (default empty). The prompt says: copy these only from `<cv_data>`, leave empty if absent. The checker keeps an item only if its text is backed by the CV (same `backed` test as bullets); dropped items go in `dropped`. `render()` writes the new sections to the `.md`. |
| `backend/signals/advisor/cv_agent.py` | The assistant may edit `leadership[i].bullets` and `achievements`, through the same checker. |
| `frontend/screens-cv.js` | Render Leadership, Achievements and Education details, each only when non-empty, with Ask AI on each. |
| `backend/signals/tests/test_cv_writer.py`, `test_cv_agent.py` | A CV with leadership and achievements keeps them; a CV without gets none; an invented achievement is dropped. |

Affects: the AI prompt, the checker, the saved draft shape (new fields default to empty, so old
drafts still load), and the `.md` download. Re-run the real-model eval (`VARITY_AGENT_EVAL=1`).

## Verify

1. Backend test suite passes.
2. Local preview (port 8126): generate Wei Jie's CV and a CV with leadership; take
   screenshots; print to PDF and compare with the mock.
3. New PR from `feat/cv-layout`. Do not merge until the user says so.
