# JobStreet Malaysia source: feasibility result (step 8)

Status: **blocked. No scraper was built.** Checked on 2026-10-22.

## What we checked

All requests used the User-Agent `Verity hackathon project (XMUM SDC 2026)`, no login, no cookies, one request at a time.

| Request | Result |
|---|---|
| `GET https://my.jobstreet.com/robots.txt` | 200, 858 bytes |
| `GET https://my.jobstreet.com/jobs?keywords=software+engineer` | **403**, header `Cf-Mitigated: challenge`, page title "Just a moment..." (Cloudflare challenge page) |
| `GET https://my.jobstreet.com/software-engineer-jobs` | **403**, same Cloudflare challenge |

The site answers a plain, honest request with a bot challenge. A real search result was never returned. We did not try another User-Agent, a headless browser, cookies or a challenge solver. That would bypass bot protection, and the rule for this step is to stop.

Because the page was blocked, we could not check how the results are delivered (server-rendered HTML or a JSON call).

## robots.txt (User-agent `*`, the group that applies to us)

```
Disallow: */job/
Disallow: *?
Disallow: /graphql
Disallow: /api/jobsearch/
Disallow: */profile/me/
Disallow: */profiles/search*
Allow: */profiles/search$
Allow: */profiles/search?tracking=ILC-profile-search-header$
Allow: *?advertiserid
Allow: *?keywords
```

What this means for us (longest matching rule wins, as in RFC 9309):

- Job detail pages (`*/job/`) are disallowed. We would not fetch them anyway.
- The JSON search endpoint `/api/jobsearch/` and `/graphql` are disallowed. We would not use them.
- Any URL with a query string is disallowed (`*?`), except those that start `?keywords` or `?advertiserid`.
- So the only allowed search route is the HTML page `https://my.jobstreet.com/jobs?keywords=<query>&page=<n>`. Path-style pages (`/software-engineer-jobs`) are allowed only without a query string, so they have no page 2.
- Our User-Agent is not named in any group, so `User-agent: *` applies. The named AI crawlers (GPTBot, CCBot, anthropic-ai and others) have their own stricter group. We are not one of them, and we do not present ourselves as one.

So robots.txt allows the allowed route in principle. The Cloudflare challenge blocks it in practice.

## Why we stopped

The step says: if the site blocks plain requests (403, CAPTCHA, challenge page), stop and report. The site did exactly that. The team's statement of permission does not change this: a permission that lives in an email does not tell Cloudflare to let our requests through, and passing the challenge from a script is bypassing bot protection.

## Conflict with the existing project docs

- `docs/data-contract.md` lists allowed sources as `hn_hiring`, `hn_story`, `github`, `arxiv`, `hf`, `rss` and says: "No Bluesky, X, LinkedIn or JobStreet: personal data and terms of service."
- `docs/build-plan.md` (P2) says: "We do not scrape LinkedIn, JobStreet or X: that breaks their terms and touches personal data."

If the team gets a working route, both lines must change in the same pull request, and the Tech Declaration must cite the written permission.

## Options for the team (the user decides)

1. **Ask JobStreet / SEEK for a sanctioned route.** The written permission should name the route: a data export, a partner feed, or a Cloudflare allow-list for the User-Agent above. Permission to scrape without a route that works is not enough.
2. **Use a file the permission-giver sends.** If they send a CSV or JSON export, `engine/jobstreet.py` can read that file. The tagging, snapshot CSV and app line described in the plan work the same way. Nothing is scraped.
3. **Use a different Malaysian demand source** that publishes a public feed or API with clear terms.
4. **Drop step 8.** HN "Who is hiring" stays the only demand source, and the Method tab keeps saying it is US-heavy.

## What would be built if a route opens (for reference)

- Queries: "software engineer", "developer", "data engineer", "data scientist", "devops", "machine learning". At most 5 result pages each.
- Pace: one request every 3 seconds or slower, timeout 30 s, retries with backoff, and a stop on any 403 or challenge page.
- Keep only: listing id, title, posted date, location, work type, classification, and the teaser text shown in the results. No company contact details, recruiter names, emails or phone numbers.
- Raw responses stay in `data/raw/jobstreet/<date>/` (gitignored).
- Commit only aggregates: `data/jobstreet_my_snapshots.csv` with `snapshot_date, skill, mentions, n_listings, share, queries, pages`. One dated snapshot per run. There is no history backfill, so this is a snapshot, not a trend.

## Permission note

The team states it has written permission from the target websites and from the hackathon organisers. We have not seen it. The user keeps it for the Tech Declaration, and the declaration must cite it.

## Recheck on 2026-10-23 (branch `feat/my-jobs`)

One request, only the path that robots.txt allows (`/jobs?keywords=`), same User-Agent, no cookies, no login.

| Request | Result |
|---|---|
| `GET https://my.jobstreet.com/robots.txt` | 200. Same group as above: `Allow: *?keywords` is the longest matching rule for `/jobs?keywords=software+engineer`, so the path is allowed. |
| `GET https://my.jobstreet.com/jobs?keywords=software+engineer` | **403**, header `Cf-Mitigated: challenge`. Still a Cloudflare challenge. |

Result: still blocked. No collector was built and the site was not tried again. The recheck is recorded in the feasibility table in `docs/malaysia-data.md`. The options above are unchanged. Two Malaysian boards that do serve results to a plain request (Hiredly, Jobstore) have collectors in `engine/my_jobs.py`; see `docs/malaysia-data.md` for their terms notes.

Note for the merge: this file also exists on branch `feat/jobstreet-my`. Both branches add it, so keep one copy and its recheck section.
