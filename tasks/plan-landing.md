# Plan: Varity landing page with a passing high-speed train (24 Oct 2026)

Status: DRAFT for your review. Nothing is built into the app yet. The 3 previews are on branch `preview/landing` and will NOT be merged.

## 1. Previews (open in your own browser while my local server runs)
| | Variant | Link | Idea | My notes |
|---|---|---|---|---|
| A | Platform edge | http://localhost:8000/previews/a-platform.html | Huge job-first headline; under it a station platform (yellow tactile strip); a train sweeps across every ~11 s | Strongest "speed rail" feel; simplest; train is decoration only |
| B | Line map | http://localhost:8000/previews/b-linemap.html | A metro line "Your CV → Jobs you fit → Skills gap → Your route → Hired"; a train rides it and stops at each station; live "Departures this month" board from the job forecast | Explains the product with the animation itself; live data. Bug: headline overflows on phones |
| C | Departure hall | http://localhost:8000/previews/c-departures.html | Black departure-board sign with split-flap headline "Next departure: a job you can get"; train passes behind the sign | Most theatrical; flap text is large (breaks the type scale) |

**My recommendation: B's line map as the hero, plus A's platform train as the background pass-by.** B tells the story (CV → job) in one picture, and its live departure board is real data, which judges like. A's sweeping train adds the "speed rail at the back" you asked for without covering text.

## 2. Skills: what I will use, how, and where
| Skill | Use? | What for | Where in the work |
|---|---|---|---|
| **impeccable** | Yes, main driver | Its shape → critique → animate → polish → harden passes | Shape the chosen variant into the real page; critique pass before review; harden pass (responsive, empty/error states) |
| **frontend-design** (official) | Yes | Distinctive, non-templated direction within DESIGN.md | Already used by the 3 preview builders; used again for the final hero composition |
| **ecc:motion-foundations / motion-patterns** | Yes | Transform/opacity-only animation, easing, timing, `prefers-reduced-motion` | The train pass-by and the station-to-station ride (CSS `offset-path` + keyframes) |
| **ecc:make-interfaces-feel-better** | Yes | Final detail pass: spacing, hit areas, focus states, text wrapping | Last polish before the PR |
| **ecc:frontend-a11y** + **ecc:accessibility** | Yes | WCAG 2.2 AA: contrast, keyboard, decorative SVG `aria-hidden`, reduced motion, readable station list | Audit before the PR |
| **taste-skill** | Partly | Only its pre-flight anti-slop checklist (the file is 1,200 lines; I won't load all of it) | Review step |
| **ecc:browser-qa** (with the built-in browser) | Yes | Screenshots at 375 / 768 / 1280, reduced-motion check, no horizontal scroll | Verification |
| **ecc:seo** | Small | Page title, meta description, Open Graph tags for the share link | `index.html` head |
| high-end-visual-design | No | Its "expensive" defaults (soft shadows, glass, rounded cards) clash with DESIGN.md's flat signage | — |
| minimalist-ui | No | Warm monochrome + pastels clash with the white/ink + line colours | — |
| industrial-brutalist-ui | No | Terminal/degradation look is off-brand | — |
| redesign-existing-projects | No | This is a new page, not a redesign | — |
| img2threejs (3D train) | No | Heavy Three.js dependency and slow on phones for a decorative train; SVG does it in a few KB | — |
| hyperframes / motion-doctrine / cut-the-curve | No | Video-production tools, not web UI | — |

## 3. What changes, and where
| File | Change |
|---|---|
| `frontend/landing.js` (new) | `renderLanding()` returns `{ html, bind }` like the other screens; fetches `/api/roles/forecast` and `/api/signals` for the live board and status line |
| `frontend/landing.css` (new) | Hero, line map, train, platform strip, departure board, reduced-motion rules |
| `frontend/app.js` | Add `landing` screen; `DEFAULT_SCREEN` becomes `landing` for first-time visitors (no saved profile); returning users still land on Today. Add "Home" to the sign band (wordmark click) |
| `frontend/index.html` | Load the 2 new files; title/meta/OG tags |
| `frontend/DESIGN.md` | Add the train and landing components (so the design file stays the source of truth) |
| `frontend/previews/` | Deleted before merge |
| docs | One line in README and the demo checklist: the demo starts on the landing page |

Copy (job-first, from the mentor notes): headline "Find the jobs you can get, and the stops to get there." CTA: one primary **Find my jobs** → CV & routes; secondary **Try an example**; **Sign in** stays in the band.

## 4. Rules I will keep
- No typed numbers: the board and status line show only API values, and hide on error.
- Train is decorative (`aria-hidden`); the station list exists as real text; `prefers-reduced-motion` parks the train.
- Transform/opacity animation only; no new library; works at 375 px with no sideways page scroll.
- Coordinate with Sheng Kuan: `app.js` / `index.html` are shared, so I branch from the newest main and keep edits small.

## 5. Verify
Backend tests unchanged (no backend change). Browser check at 375 / 768 / 1280 and with reduced motion; Opus review of the diff; PR; you review; merge on your go.

## 6. Your decisions
1. Which variant (A, B, C, or my B + A mix)?
2. Should first-time visitors land on it automatically, or only via the wordmark?
3. Any copy you want changed?
