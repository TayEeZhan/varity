# SDG links from job-post sectors

Status: built on branch `feat/sdg-sectors`. Code: `engine/sdg.py`. Data: `data/sdg_sectors.json` (patterns),
`data/role_sdg.json` and `data/skill_sdg.json` (aggregates). Tests: `tests/test_sdg.py`.

## Why

The brief asks for an SDG link that is "meaningful rather than decorative". A hand-picked tag on a skill
("Python = SDG 4.4") does not change what a user does. The same role, for example Data Engineer, can serve very
different goals, depending on what the employer does. A job post says what the company does. So we measure it:
for each role and skill, what share of its real job posts come from employers in a sector that is tied to an SDG.
A user who says "I want to work on health" then sees which roles and which skills lead there, with numbers.

## Method

1. **Sectors.** `data/sdg_sectors.json` has 8 sectors. Each has SDG targets and word-boundary regex patterns over
   post text: climate and clean energy (7.2, 13.2), health and life sciences (3.8, 3.b), education (4.3, 4.4),
   financial inclusion (8.10, 1.4), agriculture and food (2.3, 2.4), government and civic tech (16.6, 16.7),
   accessibility and disability inclusion (10.2), sustainable cities and mobility (11.2, 11.1).
   The patterns are team judgement. They are conservative on purpose: a wrong tag costs more than a missed one.
   Bare words that are often used in other ways are not patterns ("grid", "carbon", "school", "transit",
   "farm", "mobility", "urban", "disability"). The pattern needs a context word ("power grid", "carbon credits",
   "public transit", "people with disabilities").
2. **Text rules before matching** (`strip_perks`):
   - lines about equal opportunity and discrimination are removed;
   - a line that starts with Benefits, Perks, "We offer" or similar is removed;
   - after a short header such as "Benefits:", the bullet lines and short plain lines are removed, until a long line,
     a sentence that ends with a full stop, or a new header;
   - inline "Benefits: ...", "Perks include ..." and "we offer ..." parts are cut (up to a `|` or the end of the line).
3. **List guard.** A sector word inside a list is usually a customer list or a tag list ("serving pharma, energy and
   retail", "rockets, medical devices, robotics"). Such a match is ignored, unless another term of the same sector
   is next to it ("hospitals, clinics and labs" still counts).
4. **Role posts.** Same rules as `engine/roles.py`: top-level HN posts with text, not deleted; role title patterns from
   `data/roles.json`; only SINGLE-ROLE posts (a post that names 2 or more roles tells little about either).
   **Skill posts** are all posts that mention the skill (`engine/tagging.py`).
5. **Shares.** For the last 12 months (up to `as_of`) and the 12 months before: `share = posts in sector / posts`.
   The **baseline** is the same share over all posts. `lift = share / baseline share`.
   Each cell also has: counts, a 95% Wilson interval, `employers_recent` and `reliable`.
6. **Reliable** = at least 30 posts for the role (or skill), at least 3 different employers tagged in the sector, and
   (checked when the file is read, `MIN_SECTOR_POSTS` in `engine/sdg.py`, team judgement) at least 10 of the role's posts in
   the sector. A cell with 4 sector posts out of 31 is therefore rough, whatever the `reliable` flag in the file says.
   A rough cell says why: only N role posts, only N posts in the sector, or only N employers.
   HN posters repeat the same post every month, so one employer can fill 10 posts. The employer count uses the first
   segment of the first line of the post, in memory only. The files hold the count, never the key.
7. **Privacy.** The outputs hold counts, shares, thread ids and thread URLs (2 example threads per cell). No post text,
   no company names, no per-post links. A test checks this.

Build: `python -m engine.sdg --raw-dir <folder with the raw HN thread JSON files>`
(about 2 minutes: it scans the last 24 months, about 7,600 posts, once for roles and skills).

## How it changes a user's choices

Two hooks. The journey UI calls them; this module does not touch `app.py`.

- `rerank_for_goal(match_roles_output, role_sdg, goal_sector)`
  Keeps the match order. Adds to each role "X% of its posts are in <sector> (baseline Y%), Zx the baseline".
  It also gives a second order, "by fit for your goal":
  `goal_fit_score = rank_score * (1 + 0.15 * min(max(lift - 1, 0), 3))`.
  The 0.15 weight and the cap of 3 are **team judgement**, not fitted. Only a reliable over-representation raises
  the score. Nothing is lowered, nothing is hidden, and low-match roles stay in their own list.
- `plan_sdg_summary(plan, role, role_sdg, goal_sector=None)`
  Plan-level sentences built only from numbers in the plan and in `role_sdg.json`: SDG 4.4 (skills added, hours),
  SDG 8.5 (role demand trend), and with a goal: "N% of <role> posts in the last 12 months came from <sector>
  employers (SDG x.y), against Z% of all posts (a of b posts)." A cell that is not reliable says so.

Example on the real data (a user with Python, SQL and PostgreSQL, goal "health"): Backend Engineer ranks first
by match, with 7.9% of its posts in health against a 10% baseline (0.8x, below average). AI/LLM Application Engineer
(15.7% of its posts, 1.6x) gets multiplier 1.09, which is too small to pass Backend Engineer, so both orders are the
same. With goal "climate" no cell of her seven roles has the 10 sector posts needed, so the order is also unchanged:
Data Scientist has 4 of 31 posts in climate (6.1x) and stays rough. On the committed data none of the example profiles
changes order for any sector; the feature shows the numbers and keeps the order unless a cell is strong enough.

## Precision (hand check)

For each sector I read 20 random tagged posts (36 months of posts, about 11,600 posts; the sample is of posts, so an
employer that reposts counts more than once) and judged: does the post say the employer works in, or sells mainly to,
this sector? Samples were taken after the first round of fixes. Treat each figure as +/- about 13 points (n = 20).

| Sector | Estimated precision | Tagged posts, last 12 months | Different employers |
|---|---|---|---|
| Climate and clean energy | about 90% | 79 | 49 |
| Health and life sciences | about 90% | 371 | 218 |
| Education | about 95% | 45 | 32 |
| Financial inclusion | about 85% | 16 | 5 |
| Agriculture and food | about 90% | 28 | 14 |
| Government and civic tech | about 85% | 66 | 43 |
| Accessibility and disability inclusion | about 90% of posts, but few employers | 4 | 4 |
| Sustainable cities and mobility | about 65% | 6 | 4 |

What the checks found and fixed (each fix has a test): "learning platform" matched "machine learning platform";
"EMR" matched AWS EMR; "remittance" matched "remittance of funds"; "election" matched "leader election";
"sustainable development" matched cities; "digital accessibility" and "HIPAA" appear in job requirements, not in
company descriptions; "government" appeared in customer lists and in "government clearance".
Effect of the text rules on the 36-month sample (posts tagged, before and after perks and legal lines, then after the
list guard): health 1200, 1174, 1045; government 264, 263, 232; climate 375, 375, 351.
The perks rule alone is small (26 posts in health), because most perks lines say "health insurance", which is not a
pattern. The list guard does more work.

## Limits

- **HN only, and a skewed sample.** HN "Who is hiring?" over-represents US start-ups and software companies. It is not
  the Malaysian job market. Read the shares as "among HN posts", not "in the economy".
- **Sector is inferred from words** in the company description, by regex. It is not a company database. A post that
  never says what the company does gets no sector. Recall is low on purpose.
- **Small sectors are thin.** Financial inclusion, accessibility and cities have 4 to 16 posts and 4 to 5 employers in
  the whole last year. They do not support a role-level claim. They stay in the file for completeness; the
  `reliable` flag keeps them out of the re-ranking. Only health, government, climate and education have enough
  employers for most roles.
- **Reposts.** One employer can post every month. The `reliable` rule counts employers, but the shares still count
  posts (the same rule as the demand series).
- **Small n per role.** Data Scientist has 31 single-role posts in the last 12 months, Mobile Developer 48 and
  Analytics Engineer 6 (not ranked). Look at `n_recent`, the interval and `reliable`.
- **Association, not impact.** "Hires for climate" does not mean the job reduces emissions. The link is to the
  employer's sector, not to the effect of the work.
- **Weights are judgement.** The 0.15 weight, the cap of 3, the 30 posts, the 10 sector posts and the 3 employers are chosen by the team.
- **Precision is a hand estimate** from 20 posts per sector by one reader. Recall was not measured.
- **Partial month.** The last month in the window can be partial (as in `role_trends.json`).
