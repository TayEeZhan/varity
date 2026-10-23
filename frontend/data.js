/* Varity prototype data.
 * REAL: SIGNAL_RUN, STORIES and SKILLS are a snapshot of the signals backend (run 20261022T050908-ab9c76).
 *   app.js replaces them with live data from GET /api/signals on load; this copy is the offline fallback.
 * SYNTHETIC: PROFILE, ROUTES, PATHWAY, TODAY and FORECAST are demo data for the prototype.
 *   Resource links point at real, free material; every number in them is illustrative.
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

/* Pathway lines. Colours follow the transit-line roles in styles.css. */
const LINES = {
  apps: { id: "apps", letter: "A", name: "Apps line", skill: "LLM application development", y: 180 },
  guard: { id: "guard", letter: "G", name: "Guard line", skill: "AI security", y: 80 },
  serve: { id: "serve", letter: "S", name: "Serving line", skill: "LLM serving and inference", y: 280 },
};

const PROFILE = {
  name: "Junior backend developer",
  file: "sample-cv-backend-junior.pdf",
  years: "1.5 years",
  model: "Planned: Claude Sonnet 5.5 extracts skills and quotes; a fixed formula scores the match",
  skills: [
    { name: "Python / Django", level: "Working", evidence: "Built and maintained 14 REST endpoints in Django for an internal booking system." },
    { name: "PostgreSQL", level: "Working", evidence: "Wrote migrations and tuned slow queries; cut report load time from 9 s to 2 s." },
    { name: "REST API design", level: "Working", evidence: "Designed versioned endpoints consumed by the mobile team." },
    { name: "Docker", level: "Basic", evidence: "Containerised the booking API for the staging environment." },
    { name: "React", level: "Basic", evidence: "Fixed UI bugs in the admin dashboard (React, TypeScript)." },
    { name: "Prompting LLM APIs", level: "Basic", evidence: "Prototyped a ticket-summary script with an LLM API during a hack week." },
  ],
};

const ROUTES = [
  { id: "llm-app", role: "LLM application engineer", match: 62, stops: 9, weeks: "≈ 7 weeks", hours: "≈ 5 h a week",
    lines: ["apps", "guard", "serve"], outlook: "Rising",
    have: ["Python / Django", "PostgreSQL", "REST API design", "Prompting LLM APIs"],
    gap: ["Embeddings & vector search", "RAG pipelines", "RAG evaluation", "Prompt-injection defence", "Caching & latency"] },
  { id: "mlops", role: "ML platform / MLOps engineer", match: 48, stops: 14, weeks: "≈ 11 weeks", hours: "≈ 5 h a week",
    lines: ["serve", "apps"], outlook: "Rising",
    have: ["Python / Django", "Docker", "PostgreSQL"],
    gap: ["Kubernetes basics", "Model serving with vLLM", "Experiment tracking", "GPU cost monitoring", "CI for models"] },
  { id: "ai-sec", role: "AI security engineer", match: 35, stops: 17, weeks: "≈ 14 weeks", hours: "≈ 5 h a week",
    lines: ["guard", "apps"], outlook: "Rising",
    have: ["Python / Django", "REST API design"],
    gap: ["Threat modelling", "OWASP LLM Top 10", "Red-teaming LLMs", "Secure SDLC", "Incident response"] },
];

/* Station x positions are on a 1280-wide diagram; y comes from the line. */
const PATHWAY = [
  { id: "p1", line: "apps", x: 80, week: 1, status: "done", title: "Prompting fundamentals", mins: 90,
    resource: "Anthropic interactive prompt engineering tutorial", url: "https://github.com/anthropics/prompt-eng-interactive-tutorial", cost: "Free", sdg: "4.4" },
  { id: "p2", line: "apps", x: 190, week: 1, status: "done", title: "LLM APIs from Python", mins: 120,
    resource: "Hugging Face LLM Course, chapter 1", url: "https://huggingface.co/learn/llm-course", cost: "Free", sdg: "4.4" },
  { id: "p3", line: "apps", x: 300, week: 2, status: "current", title: "Embeddings & pgvector", mins: 150,
    resource: "pgvector README (you already know Postgres)", url: "https://github.com/pgvector/pgvector", cost: "Free", sdg: "4.4" },
  { id: "g1", line: "guard", x: 330, week: 2, status: "next", title: "OWASP LLM Top 10", mins: 60,
    resource: "OWASP Top 10 for LLM Applications", url: "https://genai.owasp.org/", cost: "Free", sdg: "8.2" },
  { id: "p4", line: "apps", x: 410, week: 3, status: "next", title: "Build a RAG pipeline", mins: 240,
    resource: "LangChain RAG tutorial", url: "https://python.langchain.com/docs/tutorials/rag/", cost: "Free", sdg: "4.4" },
  { id: "p5", line: "apps", x: 520, week: 3, status: "next", title: "Prompt-injection defence", mins: 120, interchange: "guard",
    resource: "OWASP LLM01: Prompt Injection", url: "https://genai.owasp.org/llmrisk/llm01-prompt-injection/", cost: "Free", sdg: "8.2" },
  { id: "s1", line: "serve", x: 600, week: 4, status: "next", title: "Serve a model with vLLM", mins: 180,
    resource: "vLLM quickstart", url: "https://docs.vllm.ai/en/latest/getting_started/quickstart.html", cost: "Free", sdg: "8.2" },
  { id: "p6", line: "apps", x: 630, week: 4, status: "next", title: "Evaluate RAG with Ragas", mins: 150,
    resource: "Ragas documentation", url: "https://docs.ragas.io/", cost: "Free", sdg: "4.4" },
  { id: "p7", line: "apps", x: 750, week: 5, status: "next", title: "Caching & latency", mins: 120, interchange: "serve",
    resource: "Paper: Cache Engineering for Agents (signal #9)", url: "https://arxiv.org/abs/2610.28577", cost: "Free", sdg: "8.2" },
  { id: "g2", line: "guard", x: 790, week: 5, status: "next", title: "Red-team your RAG app", mins: 150,
    resource: "OWASP GenAI Security Project guides", url: "https://genai.owasp.org/", cost: "Free", sdg: "8.5" },
  { id: "p8", line: "apps", x: 870, week: 6, status: "next", title: "Agents & tool calling", mins: 180,
    resource: "Hugging Face Agents Course", url: "https://huggingface.co/learn/agents-course", cost: "Free", sdg: "4.4" },
  { id: "s2", line: "serve", x: 930, week: 6, status: "next", title: "Observability & cost", mins: 90,
    resource: "OpenTelemetry GenAI semantic conventions", url: "https://opentelemetry.io/docs/specs/semconv/gen-ai/", cost: "Free", sdg: "8.2" },
  { id: "p9", line: "apps", x: 990, week: 7, status: "next", title: "Capstone: ship a RAG app", mins: 360,
    resource: "Deploy it on Replit (your own project)", url: "https://replit.com/", cost: "Free tier", sdg: "8.5" },
];

const TODAY = {
  date: "Thursday 23 October",
  replan: {
    when: "Re-planned overnight at 03:10",
    text: "GitHub retired several Copilot models on 19 Oct, so yesterday's “Compare Copilot models” stop is cancelled. The OWASP stop moved up because AI security rose to 16 mentions this week (it averaged 0.75 a week before).",
  },
  tasks: [
    { id: "t1", station: "p3", line: "apps", mins: 40, title: "Store 100 embeddings in your local Postgres with pgvector",
      resource: "pgvector README", url: "https://github.com/pgvector/pgvector",
      why: "LLM application development: 57 mentions this week vs 6.0 a week before", source: "Skill momentum, 22 Oct" },
    { id: "t2", station: "g1", line: "guard", mins: 20, title: "Read LLM01 Prompt Injection and list two attacks your booking API could face",
      resource: "OWASP Top 10 for LLM Applications", url: "https://genai.owasp.org/llmrisk/llm01-prompt-injection/",
      why: "Signal #1, “Patch the Planet” (OpenAI News + Hacker News, 21 Oct)", source: "Score 73.0" },
    { id: "t3", station: "p7", line: "serve", mins: 15, title: "Skim the abstract and figures of “Cache Engineering for Agents”",
      resource: "arXiv 2610.28577", url: "https://arxiv.org/abs/2610.28577",
      why: "Signal #9 (Hugging Face Daily Papers + arXiv, 19 Oct) feeds your Caching & latency stop", source: "Score 62.0" },
  ],
  cancelled: [
    { id: "x1", line: "apps", mins: 25, title: "Compare Copilot models for code review",
      reason: "“GitHub Copilot models deprecated on October 19, 2026” (GitHub Changelog, signal #4)" },
  ],
};

/* Projected change in tech job postings over 12 months, in percent. SYNTHETIC estimates. */
const FORECAST = [
  { role: "LLM application engineer", moderate: 28, fast: 46, band: 14, driver: "LLM application development: 57 mentions this week", real: true },
  { role: "AI security engineer", moderate: 22, fast: 38, band: 16, driver: "AI security: 16 mentions vs 0.75 a week before", real: true },
  { role: "ML platform / MLOps engineer", moderate: 18, fast: 27, band: 12, driver: "LLM serving and inference: 32 mentions this week", real: true },
  { role: "Data engineer", moderate: 6, fast: 4, band: 10, driver: "Data engineering: 5 mentions this week", real: true },
  { role: "Backend developer (CRUD APIs)", moderate: -6, fast: -17, band: 12, driver: "Assumption: coding agents absorb routine endpoint work", real: false },
  { role: "Front-end developer (template work)", moderate: -9, fast: -21, band: 13, driver: "Assumption: UI generation inside IDEs", real: false },
  { role: "Manual QA tester", moderate: -14, fast: -30, band: 15, driver: "Assumption: AI test generation", real: false },
];

/* User flow drawn as a transit map on a 1200 × 470 diagram. */
const FLOW = {
  stations: [
    { id: "f1", n: 1, line: "ride", x: 80, y: 120, label: "Landing", screen: null,
      does: "Reads the one-line promise and a live sample of today's top signals.", sees: "“Learn what's next, before it's late.” and one button: Start with your CV." },
    { id: "f2", n: 2, line: "ride", x: 210, y: 120, label: "Sign in with Google", screen: null,
      does: "Signs in once. The same Google account later receives the daily tasks.", sees: "Google consent for basic profile and Google Tasks." },
    { id: "f3", n: 3, line: "ride", x: 340, y: 120, label: "Upload CV", screen: "profile",
      does: "Drops a PDF CV, or picks the synthetic sample.", sees: "Parsing progress, then extracted skills." },
    { id: "f4", n: 4, line: "ride", x: 470, y: 120, label: "CV analysis", screen: "profile",
      does: "Checks each extracted skill against the quote it came from and fixes mistakes.", sees: "Origin station: role, years, skills with evidence." },
    { id: "f5", n: 5, line: "ride", x: 600, y: 120, label: "Choose a route", screen: "profile", interchange: true,
      does: "Compares target roles by match, stops left and outlook, then picks one.", sees: "Journey planner: three routes with skills you have and the gap." },
    { id: "f6", n: 6, line: "ride", x: 730, y: 120, label: "Pathway built", screen: "pathway",
      does: "Reviews the ordered stops; can reorder or skip any of them.", sees: "The route map with weeks, minutes, free resources and SDG tags." },
    { id: "f7", n: 7, line: "loop", x: 860, y: 250, label: "Today", screen: "today", interchange: true,
      does: "Opens Varity, or just Google Tasks, each morning.", sees: "3 to 5 next stops, each with minutes and the signal behind it." },
    { id: "f8", n: 8, line: "loop", x: 1040, y: 250, label: "Push to Google Tasks", screen: "today",
      does: "Sends today's stops to a dated Google Tasks list in one click.", sees: "Confirmation with the list name, and an undo." },
    { id: "f9", n: 9, line: "loop", x: 1120, y: 340, label: "Learn", screen: "today",
      does: "Works through the stops on phone or laptop.", sees: "Free resources open in a new tab." },
    { id: "f10", n: 10, line: "loop", x: 1000, y: 430, label: "Tick off", screen: "today",
      does: "Ticks stops in Varity or in Google Tasks; both stay in sync.", sees: "The station fills in on the line and the route progress moves." },
    { id: "f11", n: 11, line: "loop", x: 760, y: 430, label: "Signals refresh", screen: "signals", interchange: true,
      does: "Nothing: the trend layer re-ranks AI updates overnight.", sees: "New service notices and skill momentum." },
    { id: "f12", n: 12, line: "loop", x: 560, y: 340, label: "Re-plan", screen: "today",
      does: "Reads the yellow service-change band, then keeps or reverts the change.", sees: "What changed and why; cancelled stops stay visible." },
    { id: "f13", n: 13, line: "explore", x: 600, y: 30, label: "Job forecast", screen: "forecast",
      does: "Checks which roles rise or fall under two scenarios before picking a route.", sees: "Moderate vs fast disruption, labelled as estimates." },
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
