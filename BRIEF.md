# XMUM SDC Hackathon 2026: Brief

Source: the organisers' Drive folder "SDC Hackathon 2026 - Participant Resources", read 20 Oct 2026. All 8 PDFs are read.
Drive: https://drive.google.com/drive/folders/1xw7c2aN8N-at8hPEULzkcU76e_FFb0Ef
Precedence: the T&C override both handbooks. Discord messages cannot change the T&C, but the organiser can change the schedule, format, judging and prizes by announcement.

## Our team
- **Domain 1: Aiversecity Future-Ready Workforce** (assigned, locked).
- **Team name: Hokkien Mee Is Purple.** File names: `SDC2026_HokkienMeeIsPurple_Preliminary.pdf`, `SDC2026_HokkienMeeIsPurple_TechDeclaration.pdf` (confirm spacing rule in the submission video).
- 2 members: the user plus Goh Sheng Kuan.
- Answered 22 Oct: RunPod proof is NOT needed if no GPU is used. Workshop recordings exist; both members must watch them before ticking the readiness checklist. Mentor booking is done.
- Project: **Verity**. Repo https://github.com/TayEeZhan/varity (private until submission), local clone `C:\Users\eezha\verity`. Build plan `tasks/todo.md`, data contract `docs/data-contract.md`.
- Split: Ee Zhan = skill engine (HN demand backfill, forecast + intervals + backtest, scenarios, role match, pathway). Sheng Kuan = live signal fetchers, CV intake, UI pages, docs drafts.
- Note: the preliminary score does not carry forward. The final uses a different rubric, which is shared with finalists only.

## Timeline (MYT)
| When | What |
|---|---|
| 19 Oct, 8 PM | Preliminary round opens; problem statements released (the build clock starts here; the repo must be created after this) |
| 19 to 25 Oct | Online mentoring (first come, first served; booking announced on Discord) |
| **25 Oct, 7:59:59 AM** | **Preliminary submission deadline. No late submissions. Submissions freeze after it.** |
| 25 to 28 Oct | Judging |
| 28 Oct, 8 PM | Up to 15 finalists per domain announced, plus confirmation forms |
| 29 Oct, 12 PM | Finalists confirm (attendance form plus visitor pass). Missing it counts as withdrawal; a reserve team (rank 16) gets until 8 PM |
| 28 to 30 Oct | Phase 2, online "Upgrading Round": finalists refine using mentor feedback |
| **31 Oct, 08:00** | **24-hour physical hackathon at XMUM** (registration 08:00, opening 09:30, hacking from 10:30; physical mentoring) |
| **1 Nov, 07:59:59 AM** | Final deliverables due |
| **1 Nov** | Pitching 09:40 to 12:40 and 13:40 to 15:40 (parallel tracks), tabulation, closing 16:00 to 18:30. The handbook also says "6:00 to 8:30 PM" on p.20 (conflict) |

## Domains (randomly assigned, locked, no cap per domain)
**Domain 1: Aiversecity Future-Ready Workforce** (SDG 4.3, 4.4, 8.2, 8.5). Aiversecity is also the Title Sponsor.
- HMW: an AI tool that tracks AI progress, predicts rising and falling skills and jobs, matches people to future roles, and builds reskilling pathways with SDG links.
- Must have: profile intake (CV / form); an AI-trend signal layer from at least 1 updatable, dated source (hard-coded lists do not count); explainable role matching with a match score and skills gap; an ordered reskilling pathway with time estimates and free or low-cost resources (HRD Corp); SDG tags; at least 2 scenarios (moderate vs fast disruption), labelled as estimates.
- Rules: public, open or synthetic data only (no real CVs); name the LLM used; cite a source for every recommendation; never invent jobs, courses or statistics; support human judgement, do not replace it.
- Demo: the trend-signal layer feeding the matching, live.

**Domain 2: Orbyte Smart SME Challenge** (Alpha Red Solutions; SDG 8.2, 8.3, optionally 10 or 12)
- HMW: a reliable, easy-to-learn automation for the Orbyte hub that removes one recurring burden for Malaysian micro and small businesses, with people kept in control.
- Journey: trigger, connected data, decision logic, human approval, outcome plus activity log.
- Must have: one clear SME problem; the core automated journey; accuracy and ease of learning; role-based visibility, approval and an audit log (these may be simulated); fit with the Orbyte hub; a measurable benefit (time saved, errors avoided) plus SDG.
- Rules: do not rebuild Orbyte's existing HR and admin features; synthetic data only; explain PDPA handling; no real payments, statutory filings or legal advice. No API or sandbox is provided.

## Judging
- Preliminary (domain briefs and slides): Innovation & Creativity 30% · Problem-Solution Fit 25% · Feasibility of Build 25% · Clarity of Proposal 20%. The T&C say weights are "determined solely by the Organiser", so treat these as provisional.
- Feasibility needs the key feature running live, the GitHub repo, a named hardest risk and its fallback.
- Tie-break order (Participant Handbook p.22): Technical Execution, then Problem-Solution Fit, then Impact & Feasibility, then Innovation, then Presentation & Pitch, then Design & UX.
- Decisions are final, with no appeals. The organiser may disqualify a team after verification, whatever its score.

## Preliminary deliverables (one submission per team, at sdchack.my)
1. Product Requirement Doc. Use the "Submission Template" (actually the Phase 1 proposal): `SDC2026_TeamName_Preliminary.pdf`
2. Pitch deck slides
3. Live prototype link (a video or mock-up does not count)
4. Tech & Tools Declaration: `SDC2026_TeamName_TechDeclaration.pdf`
5. GitHub repo: private while building, public at submission and through judging. It needs an Apache 2.0 LICENSE, the committee accounts added as collaborators, a continuous commit history and no secrets.
6. Pitch video, 5 to 7 min, on YouTube. Keep the slides generic and focus on the system demo. Over time costs 1 point per 30 s.

A submission is incomplete if any one of these is missing: working prototype, functional UI, pitch. Do not exaggerate what the prototype can do (T&C p.26). Broken links are the team's own risk.

Proposal sections: team info; problem context (250 words); AI solution (300 words); tech stack plus block diagram, including any sponsor GenAI or cloud used; design-thinking and deployment (200 words); SDG impact table (exact sub-target, numeric baseline, KPI, % target, sources cited); readiness checklist; IP declaration; signature.

Tech declaration: architecture (200 words); libraries, versions and licences; APIs with access tier; cloud plan and region; AI models; datasets (with personal-data flag); AI dev tools with extent (minor / moderate / major) plus how the team reviewed them (100 words); sponsor resources; privacy (150 words); limitations (150 words); compliance checklist; signature. Never leave a field blank: write "None".

## Final-round deliverables (by 1 Nov 07:59:59)
Updated PRD (what changed and why), updated Tech Declaration, Final Solution Report, final .pptx, live prototype link plus any test logins, GitHub link, and a backup pitch video on YouTube (used only if the live demo fails).
Pitch: 10 min plus 5 min Q&A; over time costs 1 point per 30 s. Bring your own laptop with HDMI or a USB-C to HDMI adapter. Dress smart casual or formal.
Final round: a pre-built-looking repo with one big late commit "will result in disqualification" (the preliminary wording is "may").

## Compulsory tools and proof
- **Replit: compulsory** as part of the solution; other tools are fine alongside it. Replit Core (worth US$20) per participant. Proof, from the team's own account: a live deployment URL, a project link with history, or credit used.
- **RunPod: compulsory for any GPU work** (training, fine-tuning, inference). US$25 per team for the preliminary round. Proof: a dashboard screenshot showing Pod ID, GPU type and runtime, or the serverless endpoint URL.
- Credits arrive through the sdchack.my portal (the team lead has access). No other sponsor API or cloud is mentioned.
- Paid APIs and cloud are the team's own cost.
- The readiness checklist says all members completed the mandatory GenAI, Database and Cloud Deployment workshops. Neither handbook lists these workshops; check Discord.

## AI, originality and integrity
- AI is permitted, even encouraged. The team stays responsible for the generated code, licences and security.
- The core problem understanding, design and technical decisions must come from the team. Any member may be asked to explain any part, including the core algorithm. Failing to explain it can be flagged as lacking original input.
- A substantially AI-generated project with minimal original input risks deductions or DQ. The organiser may investigate heavy AI use.
- AI code written during the event from your own prompts is not "pre-existing work", but it must be declared.
- Pre-existing code is allowed only as a supporting part (auth, utilities, UI, logging, config). Declare it. The core idea and major features must be new.
- Open-source code is OK with attribution. Plagiarism of "work, ideas, or code" without attribution means **immediate DQ**.
- No outsourcing. Outsiders and mentors may not code, design or prepare slides.
- The organiser may check repo creation dates and commits, and request evidence. Refusing to cooperate is itself a breach.

## Penalties
The organiser picks one or more, at its discretion: a warning, mark deduction, loss of sponsor awards, cancelled finalist status, DQ, prize revoked, a future ban.
**Immediate DQ:** plagiarism, false or fabricated information, or being in two teams (all affected teams are disqualified).
Other causes: undeclared tools or AI, missing Replit or RunPod proof, a private repo at judging, changes after the deadline, a pre-built repo.

## Team, money, eligibility
- 1 to 5 members, cross-university allowed. Foundation, diploma or bachelor students at Malaysian higher-education institutions. No member changes after registration.
- The team leader receives all official notices and must stay reachable. Everyone must be on Discord, and a missed announcement is no excuse.
- The fee (RM40 or RM50) is non-refundable. The RM25 commitment deposit is refunded after the event for a valid submission (prototype, full repo, docs). It is withheld for withdrawal, DQ, or a no-show at the final without 48 h notice.
- Prize pool up to RM16,000 across the domains (Champion, 1st and 2nd Runner-up, etc.). Winners may need ID and bank details, and pay their own taxes. Prizes can be revoked.

## IP and data
- The team keeps the IP. The organiser gets a non-exclusive licence to judge, archive and showcase the work. To keep confidential parts out of the showcase, give written notice before the final.
- **By default, your name, email, phone and institution go to Aiversecity, with auto-enrolment in its ORION programme.** To opt out, email xmumai@gmail.com; this does not affect judging. Photos and video may be used for publicity unless you object in writing first.

## Physical final logistics (XMUM)
- Rooms: briefing A4#G07; hacking A3#506, 508, 509, 511, 517, 518; mentoring and sleep A3#512 and A3#505; ceremony at the A1 Tan Hua Choon Auditorium; food on the A3 ground floor; help desk on A3 level 5. The pitch rooms conflict: A4#113 and A5#119 (p.9) vs A3#516 and A3#517 (p.20).
- Parking is in the A Block basement, entering by the Southern or Eastern Gate. Register your vehicle at least 48 h ahead. No transport is provided.
- Download models and datasets in advance: no multi-GB downloads on campus Wi-Fi.
- Bring: student ID, laptop, charger, extension cord, sleeping bag, jacket and toiletries. Showers and rest areas are provided. Under-18s need parental consent.
- Banned: alcohol, drugs, weapons, hazardous chemicals, and interfering with other teams.

## Contacts
Discord https://discord.gg/p72amSbw7X (official) · WhatsApp community · sdc.xmumhack@gmail.com · xmumai@gmail.com (data opt-outs) · IG @sdc_xmumhack · sdchack.my. Report misconduct through a Discord ticket.

## Videos (user to watch and report back)
| # | Video | Location | Size |
|---|---|---|---|
| 1 | Must Watch: Drive Guide | root of folder | 26 MB |
| 2 | SDC_Submission_Files_Tutorial.mp4 | 4. Participant Guideline > 2. Video Tutorials Needed > 1. Submission Guidance | 21 MB |
| 3 | SDC_GitHub_Submission_Guide.mp4 | same folder as #2 | 14 MB |
| 4 | Apache 2.0 License Tutorial A (Direct) | 4 > 2 > 2. Apache 2.0 Tutorial | 23 MB |
| 5 | Apache 2.0 License Tutorial B (Manual) | same folder as #4 | 25 MB |
| 6 | 1. Summary Submission | 4 > 2 > 3. Mentorship Booking & Submission Method | 48 MB |
| 7 | 2. Detailed Submission | same folder as #6 | 492 MB |
| 8 | 2. SDC Hackathon Online Orientation Recording | 5. Online Orientation Briefing | 245 MB |
"6. Workshop Recordings" is empty for now.

## Opening-ceremony Q&A (user's notes)
- Open-source code online: allowed if the source is declared.
- Pitch video: keep the slides generic, focus on the system demo.
- Replit: compulsory.
- Avoid: complete AI plagiarism; you must explain what you did.
- Light Replit use: fine, as long as there is proof of use.

## Open questions
- Team name (for file names `SDC2026_TeamName_*.pdf`).
- Committee GitHub accounts to add as collaborators (probably in video #3).
- Mentorship booking method (videos #6 and #7, or Discord).
- The mandatory GenAI / Database / Cloud workshops: dates, and whether everyone has done them.
- The 1 Nov pitch time and pitch rooms (the handbook conflicts with itself).
- Contents of the GitHub sample zip (Drive preview shows only `handler.py`).
