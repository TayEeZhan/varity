# UI plan: landing gate, Google sign-in, CV-first onboarding

Status: built 31 Oct 2026 (steps 1–5; step 6 demo docs not yet updated). Upload in the CV pop-up opens CV & routes, which already has the upload and review flow. Risk 1 open: Get started uses Replit login (`/api/login`). Date: 2026-10-31. Preview: `frontend/preview.html`.

## Goal

A first-time visitor sees one choice (Get started). Signing in and adding a CV come before the app. After that, the app is the original app.

## Decisions (user, 31 Oct 2026)

- Landing is the first page for anyone without a profile.
- One button only: **Get started**. No separate "Already have an account? Sign in" link.
- Get started → **choose a Google (Gmail) account** → **CV pop-up** → app.
- Signed-out header: **Home** and **How Varity works** only.
- After sign-in: the **original tabs and screens, unchanged**, except Flow map and How Varity works (move to the landing) and My CV (becomes a pop-up).
- **My CV is a pop-up**, opened by a **Generate my CV** button on CV & routes. Inside it is the original My CV screen (CV generator + CV chat assistant), unchanged.
- Rejected: the 3-tab grouping (My Routes / My Plan / Market) and the redesigned screen contents.

## Current state (verity-cv-agent/frontend)

- Hash router in `app.js` (`SCREENS`, `TITLES`, `currentScreen()`). With no hash, a visitor with a saved profile lands on Today; anyone else lands on `home` (`landing.js`).
- Header nav (`index.html:31-39`) shows 8 tabs to everyone. Skills radar (`#/radar`) and Method (`#/method`) exist without tabs.
- Sign-in is optional: it appears only when `GET /api/me` returns `enabled: true` (Replit login).
- Landing has "Find my jobs" and "Not ready? Try an example".

## Target flow

```
Signed out:  Landing  [Home | How Varity works]   button: Get started
                 ↓
             1. Choose your Google account (Gmail; app hosted on Replit)
                 ↓
             2. CV pop-up, no close button: Drop your CV | Use a sample CV
                 ↓
Signed in:   [CV & routes | Today | Pathway | Signals | Job forecast]   (original screens)
             CV & routes → Generate my CV → My CV pop-up
```

## Changes

### Added
- Signed-out header with Home and How Varity works.
- **Get started** button (landing hero, and at the end of How Varity works).
- Google account step after Get started.
- CV pop-up: upload a CV file, or pick a sample CV (reuses `/api/profile/example`).
- **Generate my CV** button on CV & routes, opening the My CV pop-up (Close / Esc to return).
- Signed-in user with a profile skips the landing (already true in `currentScreen()`).

### Changed
- How Varity works (landing tab) = the Flow map, renamed, followed by the current How Varity works page.
- Header Sign in button (signed out) opens the same Google step.

### Removed
- "Find my jobs" button (replaced by Get started).
- "Not ready? Try an example" link (moved into the CV pop-up as the sample CV).
- Flow map and How Varity works tabs after sign-in.
- My CV tab (now the pop-up). `#/cv` should open CV & routes with the pop-up open, so links like "Open CV builder" on Today and Pathway keep working.

### Kept as is
- Landing: hero text, route map with train, What you get, Departures board (real data), "Which skills are rising? / Can you trust the numbers?" links, closing line.
- Header "Signals: offline snapshot of …" and the footer data note.
- Every signed-in screen: CV & routes, Today, Pathway, Signals, Job forecast, the My CV content (inside the pop-up), plus Skills radar and Method (reached by links, as today).

## Hidden risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | **Google sign-in vs Replit login.** The app signs in through Replit's login (`/api/login`), which shows Replit's page first; the user picks Google there. Going straight to Google's account picker needs the app's own Google sign-in (OAuth client), separate from Replit hosting. | High | Decide before building: accept Replit's page, or add Google OAuth. Hosting on Replit works either way. |
| 2 | **Login is off on local copies.** `/api/me` reports login disabled on the local server and any deploy without it. A hard sign-in gate locks the backup demo (`localhost:8000`) out. | High | If `ACCOUNT.enabled` is false, Get started goes straight to the CV pop-up. |
| 3 | **CV pop-up has no close button.** A failed upload (bad file, server down) traps the user. | Medium | Show the error in the pop-up; keep "Use a sample CV" always available. |
| 4 | **Sign-in redirect clears memory.** `signIn()` leaves the page and returns via `returnTo`. | Medium | Decide whether to show the pop-up from `hasKey()` after `loadMe()` resolves, not from a flag. |
| 5 | **Pop-up flashes for returning users** if it is decided before `/api/me` answers. | Medium | Wait for `loadMe()` (the app already waits on a bare URL). |
| 6 | **Links to `#/flow` and `#/cv`.** Today and Pathway have "Open CV builder" links to `#/cv` (`screens.js:176,611`). | Medium | Alias `#/flow` → `#/how`; `#/cv` → CV & routes with the pop-up open. |
| 9 | **My CV inside a pop-up.** The app redraws `<main>` on every change (`rerender()`); a pop-up drawn inside it would close or lose chat focus. The CV chat also needs room. | Medium | Draw the pop-up outside `<main>`, large (near full screen; full screen on phones), with focus kept inside and Esc to close. |
| 7 | **Demo materials.** `docs/submission/demo-checklist.md` says "eight Varity screens"; the video script opens with the landing and Find my jobs. | Medium | Update wording and the opening shot; screen timestamps stay valid since screens are unchanged. |
| 8 | **Several frontend copies** (`verity`, `verity-cv`, `verity-planner`, `verity-cv-agent`, `UI 2`). | Medium | Confirm which folder Replit deploys before building. |

## Build order

1. `index.html`: two navs (signed out / signed in), toggled by `hasKey()` after `loadMe()`.
2. `landing.js`: Get started replaces Find my jobs and Try an example; How tab = Flow map + How page.
3. Google step: wire Get started to `signIn()` (or Google OAuth, per risk 1); skip when login is off.
4. My CV pop-up + Generate my CV button; remove the My CV tab; alias `#/cv`.
5. CV upload pop-up, reusing the existing upload and example calls.
6. Alias `#/flow` → `#/how`; update demo checklist and video script.
7. Browser check: fresh visitor, sample CV, real upload, login on and off, returning user, phone width.
