# Malaysian demand data

Verity's demand series is Hacker News "Who is hiring?". It is US-heavy. This step adds a small Malaysian cross-check from public job-board result pages, and the official MyCOL shortage list.

Checked on 2026-10-23. Code: `engine/my_jobs.py`. Tests: `tests/test_my_jobs.py`.

## Rules we follow

The organisers said building scrapers is allowed. That does not remove a site's own protections, so these rules are in the code:

- `robots.txt` is read and obeyed for every URL. We use our own RFC 9309 matcher (`RobotsRules`): the standard-library `urllib.robotparser` ignores the `*` and `$` wildcards that job sites use, so it would allow `Disallow: *?`. A test shows this.
- If a site answers with a challenge (403, header `cf-mitigated`, title "Just a moment...", CAPTCHA marker), we record it and stop that site for the run. No CAPTCHA solving, no challenge solving, no headless browser, no rotating User-Agent, no proxy, no login.
- At most 1 request per 3 seconds per host. Timeout 30 s. Up to 3 retries with backoff (5 s, 10 s, 20 s) on network errors and 5xx. Never a retry on 401/403/429.
- User-Agent: `Verity hackathon project (XMUM SDC 2026)`.
- No personal data. We never read employer, recruiter or contact fields. Emails, phone numbers, messaging links and "Contact: ..." phrases are stripped from titles, teasers and locations.
- Raw responses go to `data/raw/my_jobs/<site>/<date>/` (gitignored). Only aggregates are committed.
- A site whose terms forbid, or do not clearly allow, automated access needs the flag `--permission-confirmed`. The flag means: the written permission from that site is on file. See "Permission" below.

## Feasibility table

All requests: plain `requests`, one request at a time, 3 s apart per host, robots checked first.

| Site | robots.txt rules that apply to us | Result page we asked for | HTTP / challenge | Where the results are | Terms (automated access) | Verdict |
|---|---|---|---|---|---|---|
| my.jobstreet.com | Group `*`. `Allow: *?keywords` beats `Disallow: *?`, so `/jobs?keywords=` is allowed. `/api/jobsearch/`, `/graphql`, `*/job/` are disallowed. | `/jobs?keywords=software+engineer` (once) | **403, `Cf-Mitigated: challenge`** | Unknown: the page is never served | Not read (the host serves a challenge) | **Blocked. Skip.** Same as the first check, see `docs/jobstreet.md` |
| www.hiredly.com (redirects to my.hiredly.com) | No group names us or `*` (only Googlebot, Bingbot, GPTBot and similar are named). Per RFC 9309 that means no restriction for us. | `/jobs-in-software-engineer` (keyword page) | 200, no challenge | In the page HTML: Next.js `__NEXT_DATA__` JSON block, 30 jobs per page. The page's own `?search-term=` URL ignores the keyword on the server, so we use the `/jobs-in-<keyword>` path, which the site itself uses. We call no other endpoint. | **Unverified.** `/terms-and-conditions` exists but its text is rendered by JavaScript and is not in the HTML we get | **Collector built** (`Hiredly`) |
| myfuturejobs.gov.my | Group `*`: `/wp-json/` and `/?rest_route=` disallowed. | Home page, then `candidates.myfuturejobs.gov.my` | 200, no challenge | Not in HTML. The job search is an Angular app on `candidates.myfuturejobs.gov.my` that loads results from a JSON API. That host has no real robots.txt (it returns the app's HTML for `/robots.txt`). The app bundle also references ALTCHA (a proof-of-work CAPTCHA). We did not call the API. | No terms page found at the usual URLs | **Skip.** JSON only, undocumented API, possible CAPTCHA. Worth an email to the agency |
| www.maukerja.my | Group `*`: `/jobs/`, `/search/*`, `/job/read/`, `/api/*` and more disallowed. | Home page `/` (allowed) | **403, `Cf-Mitigated: challenge`** | Not served | Not read (challenge) | **Blocked. Skip.** Search paths are also disallowed |
| glints.com/my | Group `*`: `*/opportunities/jobs/explore?*` disallowed, so keyword search URLs are not allowed. | `/my/jobs` (no query string, allowed) | 200, no challenge | In page HTML (`__NEXT_DATA__`, 30 jobs), but it is the unfiltered list for Malaysia: no keyword, and page 2 needs a query string that robots disallows | **Forbids**: "prohibited in using screen scraping, data mining, robots or similar data gathering and extraction tools ... except with our prior written consent" (`/my/about/terms`) | **Skip.** Keyword search is disallowed and terms forbid it |
| nodeflair.com (Malaysia) | Group `*`: only `/api/v2` disallowed. | `/jobs?countries[]=Malaysia` | 200, no challenge | Not in HTML. The page is a shell. Results load from `/api/v2`, which robots disallows. | `/terms-of-service`: no scraping clause. It bans tools that "crash, delay, damage or otherwise interfere" with the site | **Skip.** The only data route is a disallowed endpoint |
| malaysia.indeed.com | Group `*`: `/jobs?q=...` allowed (`Allow: /`). `/viewjob`, `/rc/`, `/job/`, `/company/*` disallowed. Pages with `&start=` (page 2 and later) are disallowed except for a few exact patterns. | `/jobs?q=software+engineer` (once) | **403, `Cf-Mitigated: challenge`** | Not served | Not read (challenge) | **Blocked. Skip.** |
| www.ricebowl.my | Same file as Maukerja: `/jobs/`, `/search/*` disallowed. | Home page `/` | **403, `Cf-Mitigated: challenge`** | Not served | Not read (challenge) | **Blocked. Skip.** |
| www.jobstore.com (/my) | Group `*` (three blocks, merged): `Allow: /`. Only `*/index.php/`, `*/jobseeker/...`, `*/login/...` disallowed. | `/my/jobs/q-software-engineer.html`, `?page=2` and `?page=3` | 200, no challenge | In the page HTML: job cards (`post-card-N`), 15 per page. Each card also holds its own description in a `data-full` attribute of the same page. | **Forbids without written permission**: Section D.4 of `/privacy-terms-centre/general-terms`: "Access the Site using automated bots, scrapers, crawlers, or spiders without Jobstore's express written permission." | **Collector built** (`JobStore`), needs written permission |

Summary: two of nine sites serve results to a plain, honest request and allow the path in robots.txt (Hiredly, Jobstore). Four are behind a Cloudflare challenge (JobStreet, Maukerja, Indeed, Ricebowl). Three have no usable route (Glints, NodeFlair, MyFutureJobs). The challenges were seen once per site and never retried.

Hiredly's terms text could not be read from the HTML. Treat it as unverified until someone reads the terms in a browser.

## Official open data

- **MyCOL** (Malaysia Critical Occupations List): found. TalentCorp publishes the MyMahir MyCOL 2024/2025 as a public PDF (`https://www.talentcorp.com.my/mycol/`). 66 occupations in shortage; 10 are tech-relevant. Parsed into `data/mycol.json`, mapped to our 9 roles in `data/mycol_role_map.json`. See below.
- **data.gov.my / OpenDOSM**: no occupation- or skill-level vacancy dataset found in the catalogue. The catalogue has labour-force tables (employment and unemployment by month, quarter, state, sector), not vacancies by occupation. DOSM publishes vacancy figures as PDF releases: the quarterly "Employment" report (jobs, vacancies and vacancy rate by sector and skill level, from a survey of private businesses) and "Job Vacancies Advertised Online" (big-data job market insights, latest Q1 2026). Neither is parsed here. They give context numbers, not skills.

## MyCOL files

`data/mycol.json`: `source` (publisher, year `2024/2025`, landing page, PDF URL, how it was read), `occupations` (10 entries: `occupation`, `masco_code`, `year`, `source_url`, `pdf_page_spread`, `job_titles_in_scope`), `notes`, and `reviewed_not_included` (4 media/hardware occupations we read and left out, each with the reason).

The occupation names and MASCO codes are in page images in the PDF, so they were read from rendered pages by eye. Check a few against the PDF before quoting them.

`data/mycol_role_map.json`: `mappings` (`masco_code`, `occupation`, `role_id`, `strength` = `direct` or `partial`, `reason`), `unmapped` (with reasons), and `roles_without_mycol_signal`. It is team judgement, not an official crosswalk, and the file says so (`"judgement": true`).

What it shows: MyCOL names software developers, data professionals, database, systems and network administrators, cybersecurity and ICT managers as scarce. It gives no occupation for ML engineers, AI engineers or mobile developers. Verity has no security role, while MyCOL lists one.

MyCOL is a shortage list, not a vacancy count. Do not compare its numbers with job-ad shares.

## What the collectors keep

Per run, per site: 8 fixed queries (`software engineer`, `developer`, `data engineer`, `data scientist`, `devops`, `machine learning`, `AI engineer`, `mobile developer`), up to 3 result pages each. A page with no new listings stops that query. A listing found by two queries counts once.

Kept per listing (in memory, never written): listing id, title, posted date if shown, location, teaser.

| | Hiredly | Jobstore |
|---|---|---|
| URL | `https://my.hiredly.com/jobs-in-<query-slug>` (`?page=N`) | `https://www.jobstore.com/my/jobs/q-<query-slug>.html` (`?page=N`) |
| Listing id | `id` (UUID) | `data-id` (for example `l35685127`) |
| Posted date | `activeAt` (date part) | not shown, empty |
| Teaser | the site's short summary plus the skill chips of the card | first 400 characters of the card's description |

Skills: `tag_text()` on title plus teaser, with `data/taxonomy.json`. A listing counts once per skill. Roles: the `title_pattern` of each entry in `data/roles.json`, on the title only.

## Output files and format

Both files are CSV, UTF-8, header row, `\n` line ends. Each run appends one dated snapshot per site. A re-run on the same day for the same site replaces that site's rows for that day. A site that was stopped (challenge, robots, errors) writes nothing, so there are no partial snapshots.

`data/my_jobs_snapshots.csv`

| Column | Meaning |
|---|---|
| `snapshot_date` | ISO date of the run |
| `site` | `hiredly` or `jobstore` |
| `skill` | canonical name from `data/taxonomy.json` |
| `mentions` | unique listings whose title or teaser mention the skill |
| `n_listings` | unique listings collected from that site in that run |
| `share` | `mentions / n_listings`, 6 decimals |

Only skills with at least one mention get a row.

`data/my_roles_snapshots.csv`

| Column | Meaning |
|---|---|
| `snapshot_date`, `site` | as above |
| `role_id` | id from `data/roles.json` (all 9 roles in every snapshot, also with 0) |
| `n` | unique listings whose title matches the role pattern. A title can match two roles. |
| `share` | `n / n_listings` |

The files in the repository hold the header row only until a real collection is run (see "Status").

To compare with Hacker News: `python -m engine.my_jobs --compare` prints the top skills of the latest snapshot (sites pooled) next to the HN share of the last 3 months (`sum(mentions) / sum(n_posts)` from `data/demand_monthly.csv`).

## Limits

- **Snapshot only.** One day, no history, no backfill. Do not draw a trend line from it. A second run a week later starts a series.
- **Query-dependent.** The result depends on the 8 queries and on how each site ranks its results. A keyword page shows the site's chosen top listings, not a random sample of all jobs.
- **Teaser, not the full ad.** We count what the result page shows. Skills named only deep in the ad are missed. Hiredly's teaser is a short machine summary plus chips, so its skill shares are lower and differently shaped than Jobstore's.
- **Site coverage.** Two sites out of nine. Large boards (JobStreet, Indeed, Maukerja) are not covered because of their bot protection. Whether Hiredly and Jobstore over-represent some kinds of employers is not measured.
- **Different unit from HN.** HN counts one post per company hiring, often listing many roles. Here one listing is one role. A skill share is "share of listings", not "share of companies".
- **Duplicates.** Companies repost the same role with different ids. We dedup by site listing id only.
- **Page text is data.** Nothing from a page is run, followed or used as an instruction. The parsers only read fixed fields.
- **Fragile parsers.** Hiredly's `__NEXT_DATA__` shape and Jobstore's card markup can change. If a parser finds no listings, the run writes nothing for that site.

## Permission

Hiredly's terms could not be read. Jobstore's terms forbid automated access without express written permission. The team says it has written permission, but it was not shown to this build. `python -m engine.my_jobs` therefore refuses to run these sites unless `--permission-confirmed` is given. Give that flag only when the written permission is on file, and cite it in the Tech Declaration. Permission does not change what the code does about robots.txt or challenges.

## Status (2026-10-23)

- Collectors, parsers, tests: done. Parsers were checked against one real page per site fetched during the feasibility check (those raw pages are in the gitignored `data/raw/my_jobs/probe/`).
- **No real snapshot has been collected or committed.** The two CSV files hold only their header row. The run needs `--permission-confirmed`, and this build did not set that flag on its own because the permission was not verified.
- To collect: `python -m engine.my_jobs --sites hiredly,jobstore --permission-confirmed`. About 24 requests per site, at least 3 s apart, so about 2 minutes per site.

## Per-site notes (robots and terms, for the Tech Declaration)

- **JobStreet**: robots allows `/jobs?keywords=`, forbids `/api/jobsearch/`, `/graphql`, `*/job/`. Cloudflare challenge on every request. Terms not read.
- **Hiredly**: robots has no group for us. Terms page text is JavaScript-rendered, unverified. Server-rendered results; no private API called.
- **MyFutureJobs**: government portal, robots forbids `/wp-json/` on the main host. Job search is a single-page app on `candidates.myfuturejobs.gov.my` with a JSON API; the host has no real robots.txt. Not used.
- **Maukerja, Ricebowl**: same operator and the same robots file. `/jobs/` and `/search/*` are disallowed and the home page is behind a challenge.
- **Glints**: keyword search is disallowed by robots. Terms prohibit scraping without prior written consent.
- **NodeFlair**: robots disallows the `/api/v2` endpoint that feeds the listing page. Terms have no scraping clause.
- **Indeed**: robots allows the first results page, but the site serves a challenge. Terms not read.
- **Jobstore**: robots allows the results pages. Terms forbid bots and scrapers without express written permission.
