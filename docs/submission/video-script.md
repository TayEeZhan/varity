# Varity pitch video: solo script

One presenter (Tay Ee Zhan). Target about 6:40, inside the 5–7 minute limit (about 150 words a minute).
Deck: https://claude.ai/artifact/S2wLJMTcXwLLqC78ESTqTM (23 slides). **Bold** = do this on screen. [X] = read the number off the screen.

---

## Part 1 · Problem and solution (0:00–0:55)

**Slide 1 · Cover (0:00–0:12)**
Hi, I'm Ee Zhan from team Hokkien Mee Is Purple, (university removed). This is Varity.

**Slide 2 · Problem statement (0:12–0:35)**
AI is advancing so fast that the skills you need keep piling up. In one year, AI went from solving 4.4% to 71.7% of real coding problems. By 2030, 39% of core skills will change, and AI skills are growing fastest. Computer science is hit hardest: AI could cover 94% of computer and maths tasks, more than any other field, and programmers are the most exposed job of all. People who can't keep up fall off track: employment of 22-to-25-year-olds in exposed jobs is already 19% below trend.

**Slide 3 · Our solution (0:35–0:55)**
Varity lets you catch up, close the gap and reach the job you want, all at once. Catch up: see which skills AI is making essential, tested on nearly 50,000 dated job posts and live AI news. Close the gap: get your exact gap for the job you choose, turned into a dated daily plan with free resources. Reach the job: your match rises as you learn, and you get a new CV that proves it.

## Part 2 · User flow (0:55–1:12)

**Slide 4 · User flow (0:55–1:12)**
The journey has four stops, straight from the Domain 1 brief: tell us about yourself, see the Skills Radar, get matched, follow a pathway. Then our own extra stop: prove it, with a new CV. You decide at every stop.

## Part 3 · Live demo (1:12–4:05)

**Slide 5 · Live demo (1:12–1:17)**
Let's see it live on Replit, with a synthetic CV.

**Slide 6 → browser · Demo 1: job suggestions (1:17–2:30)**
- **Landing → "Find my jobs" → upload the synthetic CV.** "Claude reads my CV, but every skill must come with a quote from it. If the quote isn't there word for word, code throws the skill out."
- **Untick one skill, save.** "I stay in charge: I untick anything wrong."
- **Scroll the job suggestions.** "These job suggestions are ranked by an AI advisor using our data: my match score, demand trends and my skills gap. The AI can only move a role two places, and every reason shows its source and date. Here: [X]% match, what I already have, and what I'm missing."
- **Open "Destination", pick a role.** "But I don't have to take the AI's advice. I can pick any role I want myself, and it's pinned on top with its own plan."
- **Flip Expected → If AI speeds up.** "And two scenarios, not one guess: 'If AI speeds up' adds a labelled estimate."

**Slide 7 → browser · Demo 2: job forecast (2:30–3:05)**
- **Open Job forecast.** "This is the job forecast. For each of eight tech roles: its share of hiring posts today, a forecast twelve months ahead with its range, and a Rising or Falling label."
- **Point at a post count link.** "Every number links back to the Hacker News threads it came from, with a date. And it says 'estimate', because it is one."

**Slide 8 → browser · Demo 3: pathway to CV (3:05–4:05)**
- **Pathway.** "My skills gap becomes a dated plan in three stages. Each stop takes 45 minutes or less and uses a free, link-checked resource."
- **Today: tick two stops.** "Here are today's stops, my progress, and one click sends them to Google Tasks."
- **Mark a skill learned.** "When I finish a skill, I mark it learned, and my match goes up to [X]%."
- **★ Generate CV.** "And our extra feature, beyond the brief: Generate CV. A new CV for my target role, with a list of what changed. Every job, date and skill is checked against my original CV. Nothing is invented."

## Part 4 · Backend (4:05–6:05)

**Slide 9 · The AI points. Code proves. (4:05–4:15)**
One rule runs the backend: the AI points, code proves. If there's no API key or a call fails, code takes over and the app still works.

**Slide 10 · Every AI model we use (4:15–4:35)**
Here is every AI model in Varity. Claude Haiku does four user-facing jobs: reading the CV, re-ranking job suggestions, coaching the pathway and writing the new CV. For the news feed, Haiku labels stories, Claude Sonnet writes the brief, and the Jev model gives a second opinion. A jury of Anthropic, OpenAI and Google models works offline only. Forecasts and scores never use a model.

**Slide 11 · F1 Intake (4:35–4:43)**
Intake: we redact contact details first, and code keeps only skills whose quotes are really in the CV.

**Slide 12 · F2 Trend signals (4:43–4:55)**
Trends come from two sources we update: every Hacker News hiring thread since 2019, and an AI news pipeline. And it never goes stale: a live timer goes online every 15 minutes to re-fetch and re-rank the news, and a daily auto-refresh for job posts is built and switches on next. When the data changes, your plan updates and tells you why.

**Slide 13 · Forecast evidence (4:55–5:07)**
We tested the forecast on 616 past cases. The simple model beat the trend models and our own machine learning, so the simple one ships.

**Slide 14 · AI jury (5:07–5:20)**
An independent three-model AI jury graded our news ranker. It found urgent security news was buried. Our fix raised ranking quality from 0.37 to 0.53. Jev scored 0.25, so it stays a second opinion.

**Slide 15 · F3 Matching (5:20–5:27)**
The match score fits on one line: 70% skill match plus 30% outlook, with weights learned from real job posts.

**Slide 16 · Job role suggestions (5:27–5:42)**
For job suggestions, code scores the roles and writes the reasons. Claude re-ranks within two places and writes one line. Code verifies it. And the user has the last word: accept a suggestion, or pick your own destination.

**Slide 17 · F4 Pathway (5:42–5:48)**
The pathway uses only 77 link-checked free resources. If a skill has no resource, it gets no task. We never invent a course.

**Slide 18 · F5 SDG (5:48–5:54)**
Every skill and role is tagged with SDG targets. We check which sectors actually hire for each role.

**Slide 19 · F6 Uncertainty (5:54–5:59)**
Two scenarios and a tested range. Every estimate is labelled.

**Slide 20 · ★ Generate CV architecture (5:59–6:05)**
In Generate CV, Claude only rewrites. Code picks the skills and checks every claim.

## Part 5 · Future and close (6:05–6:40)

**Slide 21 · Scaling direction (6:05–6:22)**
Next stops. More industries: the same engine works for health, clean energy or finance, with their own skills and roles, starting with all 66 of Malaysia's critical occupations. And a direct link to job search apps: once you're ready, go straight to live openings for your role, from ready to applied in one place.

**Slide 22 · Impact (6:22–6:32)**
In Phase 2 we'll measure three SDG targets with real users: 50% finish a plan step, 80% pick a role, and 60% add a rising skill.

**Slide 23 · Close (6:32–6:40)**
Tell us the role you want. We'll show you the route. Varity is live now at the link on screen. Thank you.

---

## Recording tips
- Record the demo in one take on the deployed URL. Have a synthetic CV from `demo-cvs/` ready.
- If the CV read is slow, cut the wait when you edit, or use "Try an example", which needs no model.
- If you run long, shorten slides 14 and 17–19 to one sentence each. If you run short, spend the spare time on the job-suggestion demo.
