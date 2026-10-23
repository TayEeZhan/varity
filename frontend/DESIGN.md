# Design: Varity (Transit Map)

Your career shown as a transit network. The pathway is a line you ride, skills are its stations, a future role is the terminus, and AI updates are service notices. The grammar comes from Vignelli/Beck metro diagrams and subway signage. The surface is Operate mode: the task comes first, and signage provides the character.

## Colour

Strategy: restrained. The ground is white and the ink black. Line colours carry meaning and never decorate.

| Token | Value | Role |
|---|---|---|
| `--paper` | `#ffffff` | Page ground |
| `--paper-2` | `#f2f3f1` | Selected row, hover, current route |
| `--ink` | `#121212` | Text, sign band, primary button, station strokes |
| `--ink-2` / `--ink-3` | `#45464a` / `#66676b` | Secondary and tertiary text (both ≥ 4.5:1 on white) |
| `--rule` | `#d6d7d4` | Row dividers |
| `--apps` | `#0039a6` | Apps line (LLM application development) |
| `--guard` | `#00843a` | Guard line (AI security) |
| `--serve` | `#ff6319` | Serving line (LLM serving & inference); black letter on its bullet |
| `--ride` / `--loop` / `--explore` | `#0039a6` / `#ee352e` / `#808183` | Flow-map lines: first ride, daily loop, explore (dotted) |
| `--signal` | `#fccc0a` | Reserved for service changes (re-plans), "You are here", active tab, text selection |
| `--rise` / `--fall` | `#00843a` / `#c8102e` | Forecast direction; `--fall` also for the CANCELLED stamp |

## Type

One family throughout: **Schibsted Grotesk** (Google Fonts) at weights 400–800. The scale is fixed rem with a ratio of about 1.2: 0.75 / 0.8125 / 0.9375 (body) / 1.125 / 1.375 / 2.125. Headings are 800 weight at −0.02em. Tabular numerals are applied only to numeric cells (minutes, scores, match, forecast values) because body-wide `tnum` widens punctuation in this face.

## Components

- **Sign band (header):** a black band with a thin white top stripe, holding plain white tab labels. The active tab carries a 5px yellow underline.
- **Route bullet:** a 26/20px circle holding the line letter (A, G, S). Today keys each letter to its line.
- **Stations:** white dot with a 3px black stroke. Done stations are filled black. The current station gets a yellow halo plus a pulse ring. An interchange is a white capsule spanning both lines; the terminus is a tall capsule.
- **Service-change band:** a full-width yellow field with a black "Service change" plate and Keep/Revert actions. Re-planned stops are never removed: they stay struck through with a red CANCELLED stamp and the dated reason.
- **Timetable rows:** bullet · minutes · title / resource link / "Why today" citation · round tick button.
- **Buttons:** 42px pill with a 2px black border. Primary is filled black, and each screen has at most one primary button.
- **Section rules:** headings sit on a 3px black rule (sign grammar). These elements are never rounded.
- **Synthetic/real labels:** a dashed chip marks synthetic data and a solid chip marks real pipeline data. Every screen carries one.

## Motion

Transitions run 150–300ms with `cubic-bezier(0.16,1,0.3,1)`. The signature interaction: hovering or focusing a station lights its line and dims the rest, and on the pathway map the matching list row lights too. The forecast scenario switch re-places and re-sorts the bars on one shared axis. The push button shows a one-shot fill. All motion is disabled under `prefers-reduced-motion`.

## Layout

Max width 1280px. Gutters are 32px, 20px at ≤960px and 16px at ≤640px. Diagrams scroll sideways on narrow screens and show a swipe hint, and the Today strip auto-scrolls to the current station. Two-column screens collapse to one column at 960px.
