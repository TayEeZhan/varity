/* Varity data.
 * Offline snapshots (real, dated output of the backend; app.js replaces them with the live API on load):
 *   SIGNAL_RUN, STORIES, SKILLS: signals run 20261022T050908-ab9c76 (GET /api/signals).
 *   FORECAST: data/role_forecast.json as of 2026-10 (GET /api/roles/forecast).
 * Nothing about the user (profile, routes, match scores, pathway, tasks) is stored here: it all comes from the API.
 */

const SIGNAL_RUN = {
  generatedAt: "22 Oct 2026, 13:09 MYT",
  runId: "20261022T050908-ab9c76",
  storyCount: 348,
  rankedBy: "deterministic formula",
};

const STORIES = [
  { rank: 1, score: 73.0, tier: "Worth a look", category: "Security incident", date: "21 Oct",
    title: "Patch the Planet: global response coordination as agents uncover critical vulnerabilities",
    url: "https://openai.com/index/coordinated-disclosure-of-critical-vulnerabilities",
    sources: ["OpenAI News", "Hacker News"],
    why: ["official source (OpenAI News)", "2 independent reports", "security issue"] },
  { rank: 2, score: 67.1, tier: "Worth a look", category: "Research", date: "19 Oct",
    title: "S-Agent 2.0: Spatial Reasoning with a General Coding Agent",
    url: "https://arxiv.org/abs/2610.28354",
    sources: ["Hugging Face Daily Papers"],
    why: ["research source", "trending 10.3σ on Hugging Face Daily Papers"] },
  { rank: 3, score: 67.1, tier: "Worth a look", category: "Product feature", date: "21 Oct",
    title: "OpenAI models are coming to Google Cloud",
    url: "https://openai.com/index/openai-models-google-cloud",
    sources: ["OpenAI News", "Hacker News"],
    why: ["official source (OpenAI News)", "2 independent reports"] },
  { rank: 4, score: 66.3, tier: "Worth a look", category: "API / pricing change", date: "19 Oct",
    title: "GitHub Copilot models deprecated on October 19, 2026",
    url: "https://github.blog/changelog/2026-10-19-github-copilot-models-deprecated-on-october-19-2026",
    sources: ["GitHub Changelog"],
    why: ["official source (GitHub Changelog)", "breaking change"] },
  { rank: 5, score: 64.1, tier: "Worth a look", category: "Research", date: "19 Oct",
    title: "PAR: Progress-Aligned Recurrence for Length Generalization in State Tracking",
    url: "https://arxiv.org/abs/2610.27628",
    sources: ["Hugging Face Daily Papers"],
    why: ["research source", "trending 18.0σ on Hugging Face Daily Papers"] },
  { rank: 6, score: 63.8, tier: "Worth a look", category: "Product feature", date: "21 Oct",
    title: "Claude Duet",
    url: "https://claude.com/product/claude-duet",
    sources: ["Hacker News", "The Verge AI"],
    why: ["2 independent reports", "trending 4.0σ on Hacker News", "model-name match"] },
  { rank: 7, score: 63.6, tier: "Worth a look", category: "Research", date: "19 Oct",
    title: "Matrix-Game 4.0: Harnessing Video Models for Real-Time Playable Game Worlds",
    url: "https://arxiv.org/abs/2610.27999",
    sources: ["Hugging Face Daily Papers"],
    why: ["research source", "trending 21.8σ on Hugging Face Daily Papers"] },
  { rank: 8, score: 63.6, tier: "Worth a look", category: "Security incident", date: "20 Oct",
    title: "Upcoming Critical PHP Security Release",
    url: "https://php.net/archive/2026.php",
    sources: ["Hacker News"],
    why: ["trending 5.7σ on Hacker News", "security issue"] },
  { rank: 9, score: 62.0, tier: "Worth a look", category: "Research", date: "19 Oct",
    title: "Cache Engineering for Agents",
    url: "https://arxiv.org/abs/2610.28577",
    sources: ["Hugging Face Daily Papers", "arXiv"],
    why: ["research source (arXiv)", "2 independent reports", "trending 4.1σ on Hugging Face Daily Papers"] },
  { rank: 10, score: 61.4, tier: "Worth a look", category: "Policy / regulation", date: "19 Oct",
    title: "Copilot model policy API for enterprise, orgs, and teams",
    url: "https://github.blog/changelog/2026-10-19-copilot-model-policy-api-for-enterprise-orgs-and-teams",
    sources: ["GitHub Changelog"],
    why: ["official source (GitHub Changelog)"] },
];

/* weekly: oldest → this week (5 weeks). momentum = (this week − avgBefore) / max(avgBefore, 1). */
const SKILLS = [
  { skill: "LLM application development", weekly: [1, 3, 4, 16, 57], avgBefore: 6.0, momentum: 8.5 },
  { skill: "Deep learning frameworks", weekly: [1, 1, 1, 0, 35], avgBefore: 0.75, momentum: 34.25 },
  { skill: "LLM serving and inference", weekly: [4, 2, 3, 5, 32], avgBefore: 3.5, momentum: 8.143 },
  { skill: "AI security", weekly: [1, 0, 0, 2, 16], avgBefore: 0.75, momentum: 15.25 },
  { skill: "Systems programming", weekly: [0, 0, 2, 0, 15], avgBefore: 0.5, momentum: 14.5 },
  { skill: "Cloud and DevOps", weekly: [5, 1, 2, 0, 14], avgBefore: 2.0, momentum: 6.0 },
  { skill: "Python development", weekly: [0, 2, 2, 10, 14], avgBefore: 3.0, momentum: 3.0 },
  { skill: "Frontend development", weekly: [0, 0, 0, 4, 13], avgBefore: 1.0, momentum: 12.0 },
  { skill: "Model fine-tuning", weekly: [0, 1, 0, 0, 9], avgBefore: 0.25, momentum: 8.75 },
  { skill: "Data engineering", weekly: [0, 1, 0, 2, 5], avgBefore: 0.75, momentum: 4.25 },
];

/* Pathway map lines. Colours follow the transit-line roles in styles.css; the names come from the pathway stages. */
const LINES = {
  apps: { id: "apps", letter: "N", name: "No-regret line", skill: "skills most of your best-fit roles need", y: 180 },
  serve: { id: "serve", letter: "D", name: "Demand line", skill: "skills job posts ask for now", y: 280 },
  guard: { id: "guard", letter: "F", name: "Future line", skill: "rising or AI-complement skills", y: 80 },
};

/* Role forecast: offline copy of data/role_forecast.json (engine/role_forecast.py, as of 2026-10).
   app.js replaces it with GET /api/roles/forecast on load. */
const FORECAST = {"schema_version": 1, "generated_at": "2026-10-22T18:46:30Z", "as_of": "2026-10", "partial_month": true, "interval": {"label": "80% target band", "level": 0.8, "model": "naive3", "window_origins": 24, "q_h12": 1.5486797822399663, "model_scores_h12_pp": {"naive": 1.6307, "naive3": 1.5776}, "n_roles_pooled": 8, "earliest_supported_as_of": "2023-11"}, "notes": ["trend label is observed (last 12 months against the 12 before), not a forecast.", "The band is pooled over the ranked roles, so it rests on few roles; see data/role_backtest.json for how often it covered held-out outcomes.", "Share of HN hiring posts is a sample of tech hiring, not a count of jobs."], "data_window": {"from": "2019-01", "to": "2026-10"}, "excluded_roles": [{"role_id": "analytics_engineer", "name": "Analytics Engineer", "reason": "Not ranked: too few posts to learn a profile"}], "roles": {"ai_app_engineer": {"name": "AI/LLM Application Engineer", "status": "ok", "note": null, "share_now": {"value": 0.06460296096904442, "mentions": 48, "posts": 743, "months": ["2026-08", "2026-09", "2026-10"]}, "level_now": 0.0654859974824403, "forecast_moderate": {"value_12m": 0.0654859974824403, "low": 0.0443293757268802, "high": 0.09572839610825869}, "band_width_pp": 5.139902038137849, "trend": {"label": "Rising", "p": 0.007728571790836767, "share_last12": 0.06327409800753904, "share_prev12": 0.049565661727133364, "mentions_last12": 235, "posts_last12": 3714, "mentions_prev12": 194, "posts_prev12": 3914}, "sources": [{"name": "Ask HN: Who is hiring? (August 2026)", "url": "https://news.ycombinator.com/item?id=49156683", "date": "2026-08-03"}, {"name": "Ask HN: Who is hiring? (September 2026)", "url": "https://news.ycombinator.com/item?id=49522897", "date": "2026-09-01"}, {"name": "Ask HN: Who is hiring? (October 2026)", "url": "https://news.ycombinator.com/item?id=49922569", "date": "2026-10-01"}, {"name": "Verity role backtest (data/role_backtest.json)", "url": "data/role_backtest.json", "date": "2026-10-22"}], "as_of": "2026-10", "partial_month": true}, "backend_engineer": {"name": "Backend Engineer", "status": "ok", "note": null, "share_now": {"value": 0.10228802153432032, "mentions": 76, "posts": 743, "months": ["2026-08", "2026-09", "2026-10"]}, "level_now": 0.10377049666729066, "forecast_moderate": {"value_12m": 0.10377049666729066, "low": 0.08279260331307539, "high": 0.129314348188633}, "band_width_pp": 4.65217448755576, "trend": {"label": "Rising", "p": 0.016783346836068417, "share_last12": 0.10581583198707593, "share_prev12": 0.09351047521716914, "mentions_last12": 393, "posts_last12": 3714, "mentions_prev12": 366, "posts_prev12": 3914}, "sources": [{"name": "Ask HN: Who is hiring? (August 2026)", "url": "https://news.ycombinator.com/item?id=49156683", "date": "2026-08-03"}, {"name": "Ask HN: Who is hiring? (September 2026)", "url": "https://news.ycombinator.com/item?id=49522897", "date": "2026-09-01"}, {"name": "Ask HN: Who is hiring? (October 2026)", "url": "https://news.ycombinator.com/item?id=49922569", "date": "2026-10-01"}, {"name": "Verity role backtest (data/role_backtest.json)", "url": "data/role_backtest.json", "date": "2026-10-22"}], "as_of": "2026-10", "partial_month": true}, "data_engineer": {"name": "Data Engineer", "status": "ok", "note": null, "share_now": {"value": 0.02826379542395693, "mentions": 21, "posts": 743, "months": ["2026-08", "2026-09", "2026-10"]}, "level_now": 0.029652523165115484, "forecast_moderate": {"value_12m": 0.029652523165115484, "low": 0.01551716881567153, "high": 0.05593289191935492}, "band_width_pp": 4.0415723103683385, "trend": {"label": "No clear change", "p": 0.06556479847085941, "share_last12": 0.0395799676898223, "share_prev12": 0.050076647930505876, "mentions_last12": 147, "posts_last12": 3714, "mentions_prev12": 196, "posts_prev12": 3914}, "sources": [{"name": "Ask HN: Who is hiring? (August 2026)", "url": "https://news.ycombinator.com/item?id=49156683", "date": "2026-08-03"}, {"name": "Ask HN: Who is hiring? (September 2026)", "url": "https://news.ycombinator.com/item?id=49522897", "date": "2026-09-01"}, {"name": "Ask HN: Who is hiring? (October 2026)", "url": "https://news.ycombinator.com/item?id=49922569", "date": "2026-10-01"}, {"name": "Verity role backtest (data/role_backtest.json)", "url": "data/role_backtest.json", "date": "2026-10-22"}], "as_of": "2026-10", "partial_month": true}, "data_scientist": {"name": "Data Scientist", "status": "ok", "note": null, "share_now": {"value": 0.026917900403768506, "mentions": 20, "posts": 743, "months": ["2026-08", "2026-09", "2026-10"]}, "level_now": 0.028819139489821528, "forecast_moderate": {"value_12m": 0.028819139489821528, "low": 0.015729048262922405, "high": 0.05222509249964885}, "band_width_pp": 3.649604423672645, "trend": {"label": "No clear change", "p": 0.3959374703300835, "share_last12": 0.019116855142703285, "share_prev12": 0.022738886050076648, "mentions_last12": 71, "posts_last12": 3714, "mentions_prev12": 89, "posts_prev12": 3914}, "sources": [{"name": "Ask HN: Who is hiring? (August 2026)", "url": "https://news.ycombinator.com/item?id=49156683", "date": "2026-08-03"}, {"name": "Ask HN: Who is hiring? (September 2026)", "url": "https://news.ycombinator.com/item?id=49522897", "date": "2026-09-01"}, {"name": "Ask HN: Who is hiring? (October 2026)", "url": "https://news.ycombinator.com/item?id=49922569", "date": "2026-10-01"}, {"name": "Verity role backtest (data/role_backtest.json)", "url": "data/role_backtest.json", "date": "2026-10-22"}], "as_of": "2026-10", "partial_month": true}, "fullstack_developer": {"name": "Full-stack Web Developer", "status": "ok", "note": null, "share_now": {"value": 0.11709286675639301, "mentions": 87, "posts": 743, "months": ["2026-08", "2026-09", "2026-10"]}, "level_now": 0.11720169414075135, "forecast_moderate": {"value_12m": 0.11720169414075135, "low": 0.08838997795902978, "high": 0.15382024320024704}, "band_width_pp": 6.543026524121726, "trend": {"label": "Falling", "p": 0.00841310624648893, "share_last12": 0.14862681744749595, "share_prev12": 0.17577925396014307, "mentions_last12": 552, "posts_last12": 3714, "mentions_prev12": 688, "posts_prev12": 3914}, "sources": [{"name": "Ask HN: Who is hiring? (August 2026)", "url": "https://news.ycombinator.com/item?id=49156683", "date": "2026-08-03"}, {"name": "Ask HN: Who is hiring? (September 2026)", "url": "https://news.ycombinator.com/item?id=49522897", "date": "2026-09-01"}, {"name": "Ask HN: Who is hiring? (October 2026)", "url": "https://news.ycombinator.com/item?id=49922569", "date": "2026-10-01"}, {"name": "Verity role backtest (data/role_backtest.json)", "url": "data/role_backtest.json", "date": "2026-10-22"}], "as_of": "2026-10", "partial_month": true}, "ml_engineer": {"name": "ML Engineer", "status": "ok", "note": null, "share_now": {"value": 0.039030955585464336, "mentions": 29, "posts": 743, "months": ["2026-08", "2026-09", "2026-10"]}, "level_now": 0.0409209765792869, "forecast_moderate": {"value_12m": 0.0409209765792869, "low": 0.028013838473502275, "high": 0.05941147467503911}, "band_width_pp": 3.1397636201536834, "trend": {"label": "No clear change", "p": 0.1647592194044774, "share_last12": 0.045234248788368334, "share_prev12": 0.05109862033725089, "mentions_last12": 168, "posts_last12": 3714, "mentions_prev12": 200, "posts_prev12": 3914}, "sources": [{"name": "Ask HN: Who is hiring? (August 2026)", "url": "https://news.ycombinator.com/item?id=49156683", "date": "2026-08-03"}, {"name": "Ask HN: Who is hiring? (September 2026)", "url": "https://news.ycombinator.com/item?id=49522897", "date": "2026-09-01"}, {"name": "Ask HN: Who is hiring? (October 2026)", "url": "https://news.ycombinator.com/item?id=49922569", "date": "2026-10-01"}, {"name": "Verity role backtest (data/role_backtest.json)", "url": "data/role_backtest.json", "date": "2026-10-22"}], "as_of": "2026-10", "partial_month": true}, "mobile_developer": {"name": "Mobile Developer", "status": "ok", "note": null, "share_now": {"value": 0.024226110363391656, "mentions": 18, "posts": 743, "months": ["2026-08", "2026-09", "2026-10"]}, "level_now": 0.024892095905092993, "forecast_moderate": {"value_12m": 0.024892095905092993, "low": 0.009227726904786763, "high": 0.06539221989622336}, "band_width_pp": 5.616449299143659, "trend": {"label": "No clear change", "p": 0.3809693685017445, "share_last12": 0.02665589660743134, "share_prev12": 0.025038323965252938, "mentions_last12": 99, "posts_last12": 3714, "mentions_prev12": 98, "posts_prev12": 3914}, "sources": [{"name": "Ask HN: Who is hiring? (August 2026)", "url": "https://news.ycombinator.com/item?id=49156683", "date": "2026-08-03"}, {"name": "Ask HN: Who is hiring? (September 2026)", "url": "https://news.ycombinator.com/item?id=49522897", "date": "2026-09-01"}, {"name": "Ask HN: Who is hiring? (October 2026)", "url": "https://news.ycombinator.com/item?id=49922569", "date": "2026-10-01"}, {"name": "Verity role backtest (data/role_backtest.json)", "url": "data/role_backtest.json", "date": "2026-10-22"}], "as_of": "2026-10", "partial_month": true}, "platform_devops_engineer": {"name": "Platform/DevOps Engineer", "status": "ok", "note": null, "share_now": {"value": 0.0901749663526245, "mentions": 67, "posts": 743, "months": ["2026-08", "2026-09", "2026-10"]}, "level_now": 0.09146522242602984, "forecast_moderate": {"value_12m": 0.09146522242602984, "low": 0.06622406817521995, "high": 0.1250387230395601}, "band_width_pp": 5.881465486434015, "trend": {"label": "No clear change", "p": 0.20836031799040683, "share_last12": 0.10285406569736133, "share_prev12": 0.09504343382728667, "mentions_last12": 382, "posts_last12": 3714, "mentions_prev12": 372, "posts_prev12": 3914}, "sources": [{"name": "Ask HN: Who is hiring? (August 2026)", "url": "https://news.ycombinator.com/item?id=49156683", "date": "2026-08-03"}, {"name": "Ask HN: Who is hiring? (September 2026)", "url": "https://news.ycombinator.com/item?id=49522897", "date": "2026-09-01"}, {"name": "Ask HN: Who is hiring? (October 2026)", "url": "https://news.ycombinator.com/item?id=49922569", "date": "2026-10-01"}, {"name": "Verity role backtest (data/role_backtest.json)", "url": "data/role_backtest.json", "date": "2026-10-22"}], "as_of": "2026-10", "partial_month": true}}};

/* User flow drawn as a transit map on a 1200 × 470 diagram. */
const FLOW = {
  stations: [
    { id: "f1", n: 1, line: "ride", x: 80, y: 120, label: "Landing", screen: null,
      does: "Reads the one-line promise and a live sample of today's top signals.", sees: "“Learn what's next, before it's late.” and one button: Start with your CV." },
    { id: "f2", n: 2, line: "ride", x: 210, y: 120, label: "Sign in with Google", screen: null, built: false,
      does: "Signs in once. The same Google account later receives the daily tasks.", sees: "Google consent for basic profile and Google Tasks." },
    { id: "f3", n: 3, line: "ride", x: 340, y: 120, label: "Upload CV", screen: "profile",
      does: "Drops a PDF CV, or picks the synthetic sample.", sees: "Parsing progress, then extracted skills." },
    { id: "f4", n: 4, line: "ride", x: 470, y: 120, label: "CV analysis", screen: "profile",
      does: "Checks each extracted skill against the quote it came from and fixes mistakes.", sees: "Origin station: role, years, skills with evidence." },
    { id: "f5", n: 5, line: "ride", x: 600, y: 120, label: "Choose a route", screen: "profile", interchange: true,
      does: "Compares target roles by match, stops left and outlook, then picks one.", sees: "Journey planner: three routes with skills you have and the gap." },
    { id: "f6", n: 6, line: "ride", x: 730, y: 120, label: "Pathway built", screen: "pathway", built: false,
      does: "Reviews the ordered stops. Reordering or skipping a stop is not built.", sees: "The route map with weeks, minutes, resources and SDG tags." },
    { id: "f7", n: 7, line: "loop", x: 860, y: 250, label: "Today", screen: "today", interchange: true,
      does: "Opens Varity, or just Google Tasks, each morning.", sees: "The next stops that fit your weekly hours, each with minutes and the signal behind it." },
    { id: "f8", n: 8, line: "loop", x: 1040, y: 250, label: "Push to Google Tasks", screen: "today", built: false,
      does: "Sends today's stops to a dated Google Tasks list in one click.", sees: "Confirmation with the list name, and an undo." },
    { id: "f9", n: 9, line: "loop", x: 1120, y: 340, label: "Learn", screen: "today",
      does: "Works through the stops on phone or laptop.", sees: "Free or free-trial resources open in a new tab." },
    { id: "f10", n: 10, line: "loop", x: 1000, y: 430, label: "Tick off", screen: "today", built: false,
      does: "Ticks stops in Varity. Sync with Google Tasks is not built.", sees: "The station fills in on the line and the route progress moves." },
    { id: "f11", n: 11, line: "loop", x: 760, y: 430, label: "Signals refresh", screen: "signals", interchange: true,
      does: "Nothing: the trend layer re-ranks AI updates overnight.", sees: "New service notices and skill momentum." },
    { id: "f12", n: 12, line: "loop", x: 560, y: 340, label: "Re-plan", screen: "today", built: false,
      does: "Would read a yellow service-change band and keep or revert the change. Not built.", sees: "What changed and why; cancelled stops stay visible." },
    { id: "f13", n: 13, line: "explore", x: 600, y: 30, label: "Job forecast", screen: "forecast",
      does: "Checks which roles are rising or falling before picking a route.", sees: "Share of hiring posts now, a 12-month range and a trend label." },
    { id: "f14", n: 14, line: "explore", x: 330, y: 340, label: "Signals board", screen: "signals",
      does: "Browses ranked AI updates and why each one ranks where it does.", sees: "Service notices with sources, dates and scores." },
  ],
  paths: {
    ride: "M 80 120 H 730 L 860 250",
    loop: "M 620 250 H 1060 Q 1120 250 1120 310 V 370 Q 1120 430 1060 430 H 620 Q 560 430 560 370 V 310 Q 560 250 620 250 Z",
    explore1: "M 600 30 V 120",
    explore2: "M 330 340 H 560",
  },
};
