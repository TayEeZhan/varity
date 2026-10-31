# Test workflow: Project and Cert stations

Live site: https://verity--eezhan0805.replit.app
Secrets needed in Replit: `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `KD_API_KEY`. Republish after you add one.

## 1. Set up the profile

1. Sign in.
2. Upload `docs/testing/sample-cv-backend.txt` (a synthetic CV).
3. Save the skills. Expect: Python, FastAPI, SQL, PostgreSQL, Docker, AWS, Git, GitHub Actions, Linux and others.
4. Pick the target role **Backend Engineer**.

Why this role: the CV has PostgreSQL and Docker but not Go, Kubernetes or Terraform. So the Project stop shows projects that close a real gap.

## 2. Project list and the "why" line

1. Open **Pathway**. Find the **Project** stop.
2. Expect projects such as these (the order follows the gain formula, so it can differ):
   - Deploy a service to Kubernetes with Terraform (closes Kubernetes, Terraform)
   - REST API in Go with PostgreSQL and tests (closes Go)
   - Sales warehouse on the Olist e-commerce dataset
   - Fix a good-first-issue in Apache Airflow
3. Each row has a "Why:" line. Reload after 30 seconds.
   - Pass: the line changes to an AI sentence that names the skill (for example "Go").
   - Still the template: the AI key is not read. Not a blocker; the template is safe.

## 3. Test A: hard checks stop the review (no AI cost)

1. Board **Sales warehouse on the Olist e-commerce dataset**.
2. Click **I agree** on the review terms.
3. Repo link: `https://github.com/TayEeZhan/varity`. Submit.
4. Expect: repo found, "unverified owner", a commit count, then **CI: "No GitHub Actions run found"**. Status: hard fail. No AI review runs.
   - "GitHub 403 / rate limit" instead: `GITHUB_TOKEN` is not read.

## 4. Test B: the full 3-model review

1. Board **REST API in Go with PostgreSQL and tests**. This cancels the Olist project (expected: it shows as cancelled with a reason).
2. Repo link: `https://github.com/evrone/go-clean-template`. Submit.
3. Expect all hard checks to pass, then "Reviewing code against your 3 items". Wait 1 to 2 minutes and reload.
4. Expected result (mixed, because this repo is not a short-link service):

| Item | Likely result |
|---|---|
| Go handlers create and resolve short links | fail |
| Links are stored in PostgreSQL with a unique index on the code | probably fail |
| A Dockerfile builds a small image of the service | pass, cites a line in `Dockerfile` |

5. Open an item. Expect 3 votes (Claude Haiku, GPT-5.4 mini, DeepSeek V4 Flash), each with a reason and a `file:line`.
   - "Review delayed": a model did not answer. Check `KD_API_KEY` and `ANTHROPIC_API_KEY`.
6. Click **Dispute** on a failed item. Note: "See the handler in internal/controller". Expect only that item to be voted again.
7. Click **Re-check** with no new commits. Expect: "push your fixes to GitHub first".
8. If an item failed on a skill that is not on the route, expect a **Keep / Revert** offer to add a stop.

Cost: about 9 AI calls for one review, a few cents.

## 5. Certs

1. On the **Cert** stop, click **Add to plan** on **AWS Certified Solutions Architect – Associate**.
2. Click **I passed** and paste a link that is not a Credly badge, for example `https://example.com/badge`.
   Expect: refused, nothing is certified.
3. Certified path: paste a real Credly badge link for that cert, from a teammate who has it, and sign in as that teammate.
   Expect: "Certified", and the Why panel shows the syllabus skills as Certified.
   A badge for a different cert, an expired badge, or a different earner name is not certified.

## 6. Match %

- Tick a Pathway task for a skill you do not have: that skill counts as Learned (0.5), so the match % rises a little.
- A passed project or a certified cert gives full credit (1.0) for its skills. A one-time note explains why a match % can change.

## What to send back if something looks wrong

A screenshot of the check list or the item votes, the role and the repo link you used.
