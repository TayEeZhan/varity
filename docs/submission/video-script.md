# Varity pitch video: solo script

One presenter (Tay Ee Zhan). Target 6:30, inside the 5–7 minute limit. About 150 words a minute.
Deck: https://claude.ai/artifact/S2wLJMTcXwLLqC78ESTqTM (22 slides). **Bold** = do this on screen. [X] = read the number off the screen.

---

## Part 1 · Problem (0:00–1:10)

**Slide 1 · Cover (0:00–0:15)**
Hi, I'm Ee Zhan from team Hokkien Mee Is Purple, (university removed). This is Varity: you tell it the job you want, and it gives you the route there, one stop at a time.

**Slide 2 · AI moves in months (0:15–0:35)**
In 2023, AI solved 4.4% of real coding problems. One year later, 71.7%. The length of task it can finish doubles about every seven months. Degrees run on a four-year cycle. A student starting today graduates into a different job.

**Slide 3 · Juniors hit first (0:35–0:55)**
And it hits the youngest first: employment of 22-to-25-year-olds in AI-exposed jobs is 19% below trend. In Malaysia, 56% of professionals already use AI at work, but only 26% have any formal training, and MOSTI says 600,000 workers must reskill within three to five years.

**Slide 4 · The gap (0:55–1:10)**
The research tells you *what* is changing. Nothing tells *you* what to learn next for the role you want. And hype hides the signal: half of all hiring posts now say "AI", yet demand for the LLM skill itself shows no clear change.

## Part 2 · User flow (1:10–1:30)

**Slide 5 · User flow (1:10–1:30)**
Varity follows the Domain 1 journey. Tell us about yourself. See the Skills Radar. Get matched. Follow a pathway. And our own extra stop: prove it, with a new CV. You decide at every stop.

## Part 3 · Live demo (1:30–4:00)

**Slide 6 · Live demo (1:30–1:35)**
Let's ride the line, on the live Replit app, with a synthetic CV.

**Slide 7 → switch to the browser · Demo part 1 (1:35–2:50)**
- **Landing → "Find my jobs".** "Here's the landing page."
- **Upload the synthetic CV.** "Claude Haiku reads it, but every skill must come with a quote from the CV. If the quote isn't there word for word, code throws the skill out."
- **Untick one skill, save.** "I'm in charge: I untick what's wrong."
- **Pick a Destination role.** "Say I want to be an AI application engineer."
- **Walk one route card.** "My match is [X]%. Here's what I already have, and my skills gap. Each reason has its source and date, and here's the SDG target this role serves."
- **Flip Moderate → Fast.** "Two scenarios, not one guess. Fast AI disruption adds a labelled estimate; nothing pretends to be certain."

**Slide 8 → browser · Demo part 2 (2:50–4:00)**
- **Pathway.** "My gap becomes a dated plan in three stages, each stop 45 minutes or less, with a free, link-checked resource."
- **Today: tick two stops.** "Today's stops, a progress bar, and one click sends them to Google Tasks."
- **Mark a skill learned.** "When I finish a skill, I mark it learned, and watch: my match goes up to [X]%."
- **★ Generate CV.** "Our extra feature, beyond the brief: Generate CV. Here's a new CV for my target role, and a list of what changed. Every job, date and skill is checked against my original CV and profile. Nothing is invented."
- **Signals and Skills radar.** "And this is the live trend layer: AI news re-ranked every 15 minutes, every source dated."

## Part 4 · Backend (4:00–5:45)

**Slide 9 · The AI points. Code proves. (4:00–4:15)**
One rule runs the whole backend: the AI points, code proves. Claude works in four places, and code checks every answer. No key or an error? Code takes over and the app still works.

**Slide 10 · F1 Intake (4:15–4:25)**
Intake: we redact contact details, Claude returns skills with quotes, and code keeps only quotes found in the CV.

**Slide 11 · F2 Trend signals (4:25–4:40)**
The trend layer has two updatable sources: every Hacker News hiring thread since 2019, nearly 50,000 posts, and an AI news pipeline. When the data changes, your plan re-plans and tells you why.

**Slide 12 · Forecast evidence (4:40–4:55)**
We backtested the forecast on 616 held-out cases. The simple model beat the trend models and our own machine learning, so the simple one ships. Our band held 94% of real values.

**Slide 13 · AI jury (4:55–5:10)**
We graded the news ranker with an independent three-model AI jury. It found urgent security news was buried; our fix raised ranking quality from 0.37 to 0.53. The Jev model scored 0.25, so by our own rule it stays a second opinion.

**Slide 14 · F3 Matching (5:10–5:18)**
Matching is one explainable line: 70% skill match plus 30% outlook, with weights learned from real job posts.

**Slide 15 · F4 Pathway (5:18–5:26)**
The pathway uses only 77 link-checked, free resources. No resource, no task. We never invent a course.

**Slide 16 · F5 SDG (5:26–5:34)**
Every skill and role carries an SDG target, and we measure which sectors actually hire for each role, so the link means something.

**Slide 17 · F6 Uncertainty (5:34–5:40)**
Two scenarios and a tested range, every estimate labelled.

**Slide 18 · ★ Generate CV architecture (5:40–5:45)**
And our extra: Claude only rewrites; code picks the skills and checks every claim.

## Part 5 · Close (5:45–6:30)

**Slide 19 · Problems solved (5:45–6:00)**
So: you know which skills to learn, you see your real gap, your plan stays current, and your learning finally reaches your CV.

**Slide 20 · Hardest risks (6:00–6:10)**
Our hardest risk is reliable trend data. We use a free public source back to 2019, show the date of the last good data, and say plainly that it is US-heavy.

**Slide 21 · Impact (6:10–6:20)**
In Phase 2 we'll measure three SDG targets with real users: 50% finish a plan step, 80% pick a role, 60% add a rising skill.

**Slide 22 · Close (6:20–6:30)**
Tell us the role you want. We'll show you the route. Varity is live now at the link on screen. Thank you.

---

## Recording tips
- Record the demo in one take on the deployed URL. Have a synthetic CV from `demo-cvs/` ready.
- If the CV read is slow, cut the wait in editing, or use "Try an example" (no model needed).
- Running long? Shorten slide 13 to one sentence and say slides 14–17 in one breath each. Running short? Spend the spare time on the demo.
