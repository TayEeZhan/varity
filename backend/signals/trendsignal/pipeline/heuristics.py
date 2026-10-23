"""Rule-based enrichment. Used when no Claude credentials exist, the LLM budget is spent,
or the LLM output fails validation. Deliberately conservative: it never invents numbers."""

from __future__ import annotations

import re

from trendsignal.models import Enrichment, Entity
from trendsignal.pipeline.similarity import key_terms

SEMVER_RE = re.compile(r"\bv?(\d+)\.(\d+)(?:\.(\d+))?(?:[-.]?(rc|alpha|beta|a|b|dev|nightly|preview|pre)\d*)?\b", re.I)
MODEL_NAME_RE = re.compile(r"\b(gpt|claude|gemini|gemma|llama|mistral|mixtral|qwen|deepseek|phi|grok|sonnet|opus|haiku|o\d)\b[- ]?\d*", re.I)
NIGHTLY_RE = re.compile(r"\b(trunk|nightly|ciflow)/|\b[0-9a-f]{12,}\b", re.I)
HOWTO_RE = re.compile(
    r"^(how (to|we|i)\b|building\b|build\b|fine-tun|deploy|getting started|a guide|guide to|step-by-step|introduction to)"
    r"|\b(using|with|on) (amazon|aws)\b",
    re.I,
)
KNOWN_ORGS = frozenset(
    "openai anthropic google deepmind meta microsoft nvidia mistral hugging face huggingface amazon aws apple"
    " xai deepseek alibaba github ibm intel amd oracle salesforce databricks".split()
)

CATEGORY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("security_incident", re.compile(r"\bcve-\d|vulnerab|exploit|security (flaw|issue|advisory|update|release)|breach"
                                     r"|malware|backdoor|credential steal|compromised|supply[- ]chain attack|\brce\b", re.I)),
    ("model_release", re.compile(r"(introduc|launch|releas|announc|unveil|open[- ]sourc|meet )\w*\b.{0,60}\b(model|llm|gpt|claude|gemini|llama|mistral|qwen|deepseek|gemma)", re.I)),
    ("api_pricing_change", re.compile(r"\bpric(e|es|ing)\b|deprecat|\bsunset|rate limits?|end of life|\beol\b", re.I)),
    ("funding_business", re.compile(r"\braises?\b|\bfunding\b|series [a-f]\b|valuation|acquir|acquisition|\bipo\b|layoffs?", re.I)),
    ("policy_regulation", re.compile(r"regulat|\blaw\b|\bpolicy\b|senate|congress|eu ai act|executive order|lawsuit|\bcourt\b", re.I)),
    ("benchmark", re.compile(r"benchmark|leaderboard|state[- ]of[- ]the[- ]art|\bsota\b", re.I)),
    ("opinion", re.compile(r"^(ask|tell) hn|\bi think\b|\bopinion\b|thoughts on|the case (for|against)|\bessay\b|\bwhy (you|we|i)\b", re.I)),
)

WHY_TEMPLATES = {
    "model_release": "A new model can change which tools and APIs are worth using; check its availability and limits.",
    "research": "Research like this often shows up in tools months later; skim the abstract to see if it touches your work.",
    "product_feature": "A platform you may use gained a feature; check whether it replaces something you built yourself.",
    "dev_tool_release": "A tool developers depend on shipped a release; read the changelog before you upgrade.",
    "api_pricing_change": "Pricing or deprecation changes can break budgets or code; check whether your usage is affected.",
    "security_incident": "Security issues can affect code you run; check whether you use the affected component.",
    "policy_regulation": "Rules on AI use can change what you are allowed to build or ship.",
    "funding_business": "Industry moves hint at where hiring and tools are heading, but rarely need action today.",
    "benchmark": "Benchmarks shift which models look best; treat single results with caution.",
    "opinion": "An opinion piece: useful context, not news you need to act on.",
}


def parse_version(title: str) -> tuple[int, int, int, bool] | None:
    match = SEMVER_RE.search(title)
    if not match:
        return None
    major, minor = int(match.group(1)), int(match.group(2))
    patch = int(match.group(3) or 0)
    return major, minor, patch, bool(match.group(4))


CONFIDENCE_RELEASE_FEED = 0.95
CONFIDENCE_TITLE_RULE = 0.85
CONFIDENCE_BODY_RULE = 0.6
CONFIDENCE_SOURCE_DEFAULT = 0.6  # research tier with no other signal
CONFIDENCE_DEFAULT = 0.3  # nothing matched: "product_feature" is a guess
BREAKING_RE = re.compile(r"breaking change|deprecat|removed support|end of life|migration required", re.I)


def classify_with_confidence(title: str, text: str, tier: str, is_release_feed: bool) -> tuple[str, float]:
    """Rules match the title only; body text is too noisy (tutorials mention models, pricing, laws).
    The one exception is security, where missing an advisory costs more than a false alarm.
    Confidence says how strongly a rule matched: title match > body match > default guess."""
    lead = text[:600]
    rules = {category: pattern for category, pattern in CATEGORY_RULES}
    if rules["security_incident"].search(title):
        return "security_incident", CONFIDENCE_TITLE_RULE
    if rules["security_incident"].search(lead):
        return "security_incident", CONFIDENCE_BODY_RULE
    if is_release_feed:
        return "dev_tool_release", CONFIDENCE_RELEASE_FEED
    for category, pattern in CATEGORY_RULES:
        if category != "opinion" and pattern.search(title):
            return category, CONFIDENCE_TITLE_RULE
    if parse_version(title) and re.search(r"release|released|changelog", f"{title} {lead}", re.I):
        return "dev_tool_release", CONFIDENCE_BODY_RULE
    if tier == "B":
        return "research", CONFIDENCE_SOURCE_DEFAULT
    if rules["opinion"].search(title):
        return "opinion", CONFIDENCE_TITLE_RULE
    return "product_feature", CONFIDENCE_DEFAULT


def classify(title: str, text: str, tier: str, is_release_feed: bool) -> str:
    return classify_with_confidence(title, text, tier, is_release_feed)[0]


def release_level(title: str) -> str:
    """major / minor / patch / pre-release / none, from the version number in a title."""
    if NIGHTLY_RE.search(title):
        return "pre-release"
    version = parse_version(title)
    if version is None:
        return "none"
    _major, minor, patch, pre = version
    if pre:
        return "pre-release"
    if patch:
        return "patch"
    return "minor" if minor else "major"


def content_flags(title: str, text: str) -> dict[str, bool]:
    """Keyword flags for the feature vector. Title plus the start of the body."""
    rules = {category: pattern for category, pattern in CATEGORY_RULES}
    return {
        "is_security": bool(rules["security_incident"].search(f"{title} {text[:600]}")),
        "is_breaking": bool(BREAKING_RE.search(f"{title} {text[:1500]}")),
        "is_pricing": bool(rules["api_pricing_change"].search(title)),
        "is_howto": bool(HOWTO_RE.search(title)),
        "model_name_hit": bool(MODEL_NAME_RE.search(title)),
    }


def magnitude(category: str, title: str, tier: str, upvotes: float) -> tuple[int, str]:
    if category == "dev_tool_release":
        if NIGHTLY_RE.search(title):
            return 1, "nightly or CI build"
        version = parse_version(title)
        if version is None:
            return 2, "release without a parseable version"
        major, minor, patch, pre = version
        if pre:
            return 1, "pre-release (rc/beta/nightly)"
        if patch:
            return 2, f"patch release {major}.{minor}.{patch}"
        if minor:
            return 3, f"minor release {major}.{minor}"
        return 4, f"major release {major}.0"
    if category == "model_release":
        return (4, "new model announced by an official source") if tier == "A" else (3, "model release reported second-hand")
    if category == "security_incident":
        return (4, "security issue with a CVE or critical rating") if re.search(r"cve|critical", title, re.I) else (3, "security issue")
    if category == "api_pricing_change":
        return (4, "official pricing or deprecation change") if tier == "A" else (3, "reported pricing or deprecation change")
    if category == "research":
        return (3, "paper with strong community interest") if upvotes >= 50 else (2, "new paper")
    if category in ("policy_regulation", "benchmark"):
        return 3, category.replace("_", " ")
    if category == "product_feature":
        if HOWTO_RE.search(title):
            return 2, "how-to or tutorial post"
        return (3, "feature announced by an official source") if tier == "A" else (2, "feature or product news")
    if category == "funding_business":
        return 2, "business news"
    return 1, "opinion or discussion"


def extract_entities(title: str, dev_terms: tuple[str, ...]) -> tuple[Entity, ...]:
    entities: list[Entity] = []
    for term in sorted(key_terms(title)):
        if MODEL_NAME_RE.fullmatch(term) or MODEL_NAME_RE.match(term):
            kind = "model"
        elif term in KNOWN_ORGS:
            kind = "org"
        elif term in dev_terms:
            kind = "library"
        else:
            kind = "topic"
        entities.append(Entity(name=term, type=kind))
    return tuple(entities[:6])


def audience_for(category: str, text: str) -> tuple[str, ...]:
    lowered = text.lower()
    roles = []
    if category in ("model_release", "research", "benchmark") or re.search(r"pytorch|cuda|training|inference|model", lowered):
        roles.append("ml_engineer")
    if re.search(r"\b(api|sdk|server|python|backend|database)\b", lowered):
        roles.append("backend")
    if re.search(r"\b(react|next\.js|javascript|typescript|css|frontend|browser)\b", lowered):
        roles.append("frontend")
    if re.search(r"\b(kubernetes|docker|cloud|aws|gcp|azure|devops|deploy)\b", lowered):
        roles.append("devops")
    if category == "security_incident" or "security" in lowered:
        roles.append("security")
    if re.search(r"\b(sql|data pipeline|analytics|spark|dataset)\b", lowered):
        roles.append("data")
    if category in ("model_release", "research", "benchmark", "dev_tool_release"):
        roles.append("student")
    return tuple(dict.fromkeys(roles)) or ("student",)


def first_sentences(text: str, count: int = 2, limit: int = 280) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    joined = " ".join(sentences[:count]).strip()
    if len(joined) <= limit:
        return joined
    cut = joined[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{cut}…"


def heuristic_enrichment(title: str, text: str, tier: str, is_release_feed: bool,
                         upvotes: float, dev_terms: tuple[str, ...]) -> Enrichment:
    category = classify(title, text, tier, is_release_feed)
    level, reason = magnitude(category, title, tier, upvotes)
    breaking = bool(BREAKING_RE.search(f"{title} {text[:1500]}"))
    return Enrichment(
        category=category,
        entities=extract_entities(title, dev_terms),
        change_magnitude=level,
        magnitude_reason=reason,
        audience=audience_for(category, f"{title} {text[:1500]}"),
        is_breaking_change=breaking,
        tldr=first_sentences(text) or title,
        why_it_matters=WHY_TEMPLATES.get(category, WHY_TEMPLATES["product_feature"]),
        evidence_quotes=(title,),
        enriched_by="heuristic",
    )
