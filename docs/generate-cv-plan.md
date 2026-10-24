# Generate new CV: architecture plan

Status: built (PR: feat/generate-cv).

## Goal
One button builds a new CV for the role the user picked on the pathway. It uses the original CV plus the latest skill profile, including skills marked as learned. No new page is added.

## Gap to fix first
The CV text is thrown away after skills are pulled out of it. `Profile` (`backend/signals/intake/models.py`) keeps skills, target role and plan, but no CV text. Without it, a new CV would only have a skills section.

- Save the cleaned CV text (contact details already replaced with placeholders such as `[email]` and `[phone]`) in its own table, `owner_cvs(owner_key, cv_text, updated_at)`. It is written by `POST /api/profile/apply`.
- It is kept apart from the profile, so personal details are not sent to the browser with every profile request.
- It is stored in the same database as the profile (SQLite locally, Postgres on Replit). It moves with the profile when the user signs in, and it is deleted with the profile.
- The generator reads the whole text, including degree, university and work history, and the checker tests every claim against it.

## Flow
| # | Step | Who | Notes |
|---|------|-----|-------|
| 1 | User clicks **Generate CV for <role>** | Frontend | In the "Take it with you" panel on the Today page and on the Pathway page. |
| 2 | `POST /api/cv/generate` (`X-Profile-Token`) | API (`roles_api.py`, which already loads role data) | Rate limited and returns the standard envelope, like the other endpoints. |
| 3 | Load inputs: saved CV text, profile skills, `target_role` and its required skills | Code | Uses data the app already has. |
| 4 | Choose and order skills for the role | Code | Reuses the gap and match ranking from `advisor/service.py`. |
| 5 | **Write the CV**: summary, reworded bullets, skills | **LLM** | Uses the app's existing model-calling helper, without the answer cache, so no CV text is kept outside the `owner_cvs` table. Gets only the original CV, the chosen skills and the role. Returns structured fields. |
| 6 | Check every claim | Code | Each skill must be in the profile. Each job, date and number must be in the original CV. Anything that fails is removed. Reuses the line-matching idea from `intake/verify.py`. |
| 7 | Mark skills learned through Varity | Code | Uses each skill's recorded evidence source (`pathway` / `task_done`). |
| 8 | Return the CV as Markdown, plus a list of what changed | API | Download as `.md`, or print to PDF from the browser. |

## When there is no LLM
If there is no API key or the call fails, keep the original CV and add an updated skills section, built by code alone. If there is no saved `cv_text` (users who joined before this change), return a CV with skills only and a "re-upload your CV for a full version" message.

## Changes by file
- **Updated**:
  - `accounts_store.py`: the `owner_cvs` table (get, put, delete, move).
  - `web/cv_api.py`: save the CV text when the profile is applied.
  - `web/roles_api.py`: the `generate` route.
  - `frontend/screens.js`: the button and download.
- **New**:
  - `advisor/cv_writer.py`: steps 3–7, kept as pure functions where possible.
  - `tests/test_cv_writer.py`: the checker drops invented skills and jobs; the no-LLM fallback works.
- **Removed**: nothing.

## Risks
- Invented facts: steps 4 and 6 are code, so the model can only reword, never add claims.
- Personal data in `cv_text`: stays behind the profile token and is deleted with the profile.
- Older users have no stored CV: handled by the fallback above.

## Not building
Several templates, `.docx` files, editing the CV in the app, and a history of past CVs.
