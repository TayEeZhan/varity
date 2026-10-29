# Daily refresh on Replit (build step 4: "constantly updates")

What this sets up:

1. A **Scheduled Deployment** runs `python -m engine.scheduled` every day at 09:00 Malaysia time. It downloads the newest Hacker News "Who is hiring?" thread, rebuilds the scores, and saves the result in **Replit App Storage**.
2. The scheduled job is the refresh path: it saves the newest result to the store, and nothing in the web app refreshes data by hand.

If App Storage is empty, broken, or older than the committed data, a reader of the store falls back to the committed data. Nothing breaks.

> Labels in the Replit UI change from time to time. Wherever this page says "verify this label in your Replit UI", look for the closest match and tell me if it differs, so I can fix this page. Do not guess.

## What was added in the code

| File | Role |
|---|---|
| `engine/store.py` | Saves and loads snapshots. `LocalStore` (a folder, for tests and local runs) and `ReplitStore` (App Storage). |
| `engine/scheduled.py` | The job. Exit code 0 = good, 1 = failed. Prints one JSON line. |
| `engine/live.py` | Reads the newest stored snapshot (only if newer than the committed data) and builds the banner text. |
| `requirements.txt` | New line: `replit-object-storage==1.0.2` (checked against the OSV advisory database on 22 Oct 2026: no advisories for it or for the packages it installs). |

Layout in the bucket (only files this feature writes; nothing else is touched):

```
latest.json                       <- points to the newest snapshot, written last
snapshots/<UTC time>/skill_scores.json
                     demand_monthly.csv
                     hn_threads.csv
                     ai_context_monthly.csv
                     role_demand_monthly.csv, role_trends.json,
                     role_backtest.json, role_forecast.json   <- role forecast (Phase 1)
                     meta.json    <- fetched_at, posts before/after, thread id, roles_updated, generated_at, code commit
```

The newest 14 snapshots are kept. Older ones are deleted. If a job fails half way, `latest.json` is not changed, so visitors keep the last good data.

## Part 1. Merge and redeploy first

1. Get the new code to Replit. The Phase 1 role-refresh code is not on GitHub yet, so a Pull does not bring it. Either push it (your call) and Pull in Replit (Git tool, "Pull"; verify this label in your Replit UI), or copy the changed files listed in `HANDOFF.md` into the Replit workspace.
3. Publish the app again, so it installs the new package from `requirements.txt` (the build command is `pip install -r requirements.txt`).

## Part 2. Create the App Storage bucket

"App Storage" was called "Object Storage" before. Verify this label in your Replit UI.

1. Open the Replit workspace of the Verity app.
2. Open the tools list (search "App Storage" in the search box at the top of the workspace, or find it in the left tool list; verify this label in your Replit UI).
3. Click the button to create a bucket (verify this label in your Replit UI, it may say "Create bucket" or "Create new bucket"). The name does not matter. Use `verity-snapshots`.
4. Confirm the bucket is the app's **default bucket**. The Python package uses the default bucket when no bucket id is given. After you create the bucket, the file `.replit` should get a block like this (verify the exact key names in your `.replit`):

   ```
   [objectStorage]
   defaultBucketID = "replit-objstore-..."
   ```

   If there is no such block, open the bucket in the App Storage tool and look for a setting that makes it the default (verify this label in your Replit UI). As a fallback, copy the bucket id from the App Storage page and add a Secret `VERITY_BUCKET` with that id (see Part 4).

## Part 3. Create the Scheduled Deployment

1. In the workspace, click **Publish** (verify this label in your Replit UI; it was called "Deploy" before).
2. Choose the type **Scheduled** (verify this label in your Replit UI).
3. Fill in the form. These are the values; the field names may differ a little (verify the field names in your Replit UI):

   | Field | Value |
   |---|---|
   | Schedule | Daily at 09:00 Malaysia time. As a cron expression in UTC: `0 1 * * *` (09:00 MYT is 01:00 UTC; Malaysia has no daylight saving). If the form takes plain English, type "every day at 1:00 AM UTC". Replit shows the cron it understood. Check that it says `0 1 * * *`. |
   | Run command | `python -m engine.scheduled` |
   | Build command | `pip install -r requirements.txt` |
   | Timeout | The default is fine. The job takes about 7 seconds. |

   Check which time zone the schedule form uses (verify in your Replit UI). If it uses UTC, `0 1 * * *` is right. If it uses your own time zone, use 09:00 and ignore the cron above.
4. Click the button that creates or publishes the deployment (verify this label in your Replit UI).

**Possible limit (verify):** Replit may allow only one deployment type for each app. If the form does not let you add a Scheduled deployment next to the Autoscale one, tell me before you change anything. Option: create a second Replit app from the same GitHub repo for the job only and give it the same bucket. Do not delete the Autoscale deployment.

## Part 4. Secrets

The job needs **no secret** to fetch the data: the Hacker News data is public.

Only add these if a check below tells you to (workspace Secrets tool, "Secrets"; verify this label in your Replit UI; and check that the deployments can see the secret):

| Secret | Value | When |
|---|---|---|
| `VERITY_STORE` | `replit` | The job log says `"store": "local"`. This forces App Storage. |
| `VERITY_BUCKET` | the bucket id | The job fails with "cannot reach the Replit bucket" or "no default bucket". |

## Part 5. Run it once by hand

Do this before you wait for 09:00.

**Option A, in the workspace Shell** (the shell tool in the workspace; verify this label in your Replit UI):

```
python -m engine.scheduled
```

A good run prints one line like this (and no traceback):

```
{"duration_s": 7.1, "fetched_at": "2026-10-23T01:00:05Z", "month": "2026-10", "ok": true, "posts_after": 271, "posts_before": 266, "snapshot_id": "20261023T010006Z", "snapshots_kept": 1, "source": "scheduled", "store": "replit", "thread_id": 49922569}
```

Check: `"ok": true` and `"store": "replit"`. If it says `"store": "local"`, the data went to a disk that is thrown away. Add the secret `VERITY_STORE=replit` and run again.

Note: I could not check whether the workspace and the published app share one bucket (verify). If the banner in Part 6 does not appear after a shell run, use Option B.

**Option B, from the deployment page.** Open the Scheduled deployment (verify the place in your Replit UI: Publish, then the deployment's page). Look for a button that runs the job now (verify this label in your Replit UI; it may be named "Run now" or "Test run", or it may not exist). If it does not exist, wait for the next 09:00, or temporarily set the schedule to a few minutes ahead and set it back.

## Part 6. Check that it worked

1. Check the job log (Part 7) shows `"ok": true` and `"roles_updated": true`.
2. Wait up to 10 minutes (the web app checks the store every 10 minutes), then open the role forecast screen. The header should end with `· updated YYYY-MM-DD · N posts so far this month`. Without that text, the app still shows the committed data: `GET /api/roles/forecast` returns `"source": "committed"` in `meta`.
3. Optional: open the App Storage page. You should see `latest.json` and a `snapshots/` folder.

The web app also runs the same job itself every day at 06:30 (scheduler job `forecast_refresh`). On Autoscale it only runs when an instance is awake, so the Scheduled Deployment is the reliable path. Two runs a day are harmless: each one switches `latest.json` only after a full upload.

## Part 7. Look at the logs

1. Open the Scheduled deployment page and open its logs (verify this label in your Replit UI; it may be a "Logs" tab).
2. Each run prints a progress line on stderr and one JSON line on stdout. A failed run ends with `"ok": false` and the run is marked as failed.

| `stage` in the JSON | Meaning | What to do |
|---|---|---|
| `store` | App Storage could not be used (package missing or no bucket). Nothing was fetched. | Check that the deployment installed `replit-object-storage` (build log), then Part 2 and the secrets in Part 4. |
| `refresh` | Hacker News could not be fetched, or the scores could not be rebuilt. | Usually a short network problem. Wait for the next run. The old data stays. |
| `save` | Fetch worked but the upload failed. | Check the bucket still exists. `latest.json` was not changed. |

A failed run never changes what visitors see: they keep the last good snapshot.

## Notes

- The job never writes into the committed `data/` folder. It works in a temporary folder and uploads the result.
- When you commit new data to `data/` later (newer than the stored snapshot), the app shows the committed data again until the next job run. The app compares `generated_at` of the two.
- Cost: one 7-second job per day and a few small files (under 1 MB each snapshot).
