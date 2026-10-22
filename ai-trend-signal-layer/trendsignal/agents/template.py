"""Deterministic brief built straight from the database. The fallback whenever the Editor
agent is unavailable or fails verification, and the reference for what the agent may say."""

from __future__ import annotations

from trendsignal.agents.verifier import URL_RE, StoryFacts
from trendsignal.queries import StoryView

CATEGORY_LABELS = {
    "model_release": "Model release", "research": "Research", "product_feature": "Product",
    "dev_tool_release": "Tool release", "api_pricing_change": "Pricing / deprecation",
    "security_incident": "Security", "policy_regulation": "Policy", "funding_business": "Business",
    "benchmark": "Benchmark", "opinion": "Opinion",
}


def story_facts(view: StoryView) -> StoryFacts:
    text = " ".join([
        view.title, view.tldr, view.why_it_matters, " ".join(view.reasons), " ".join(view.entities),
        CATEGORY_LABELS.get(view.category, view.category), " ".join(s.name for s in view.sources),
        f"{view.time_to_understand_min} min", f"{view.importance:.1f}", f"{view.importance:.0f}",
        " ".join(f"{v:.2f}" for v in view.features.values()), str(len(view.sources)),
    ])
    return StoryFacts(id=view.id, urls=frozenset(s.url for s in view.sources) | {view.url}, text=text)


def _plain(text: str) -> str:
    """Inline links in summaries are not source links, so the brief leaves them out."""
    return " ".join(URL_RE.sub("", text).split())


def _must_know_block(rank: int, view: StoryView) -> list[str]:
    ref = f"[S{view.id}]"
    label = CATEGORY_LABELS.get(view.category, view.category)
    return [
        f"{rank}. **[{label}] {view.title}** · ⏱ {view.time_to_understand_min} min {ref}",
        f"   {_plain(view.tldr)} {ref}",
        f"   *Why it matters to you:* {view.why_it_matters} {ref}",
        f"   *Why it ranked here:* {' · '.join(view.reasons)} {ref}",
        f"   [Read the source]({view.url}) {ref}",
        "",
    ]


def render_brief(title: str, kind: str, groups: dict[str, list[StoryView]]) -> str:
    lines = [f"# {title}", ""]
    must_know = groups.get("must_know", [])
    if kind == "weekly":
        lines.append("## 🗓️ The week's most important stories")
        lines.append("")
        for rank, view in enumerate(must_know, start=1):
            lines.extend(_must_know_block(rank, view))
        return "\n".join(lines).strip() + "\n"

    if must_know:
        lines += ["## 🔴 Must-know", ""]
        for rank, view in enumerate(must_know, start=1):
            lines.extend(_must_know_block(rank, view))
    else:
        lines += ["## 🔴 Must-know: nothing cleared the bar today", ""]

    worth = groups.get("worth_a_look", [])
    if worth:
        lines += ["## 🟠 Worth a look", ""]
        for view in worth:
            summary = _plain(view.tldr)
            summary = f" {summary}" if summary and summary != view.title else ""
            lines.append(f"- **{view.title}** · ⏱ {view.time_to_understand_min} min.{summary} [S{view.id}]")
        lines.append("")

    emerging = groups.get("emerging", [])
    if emerging:
        lines += ["## 🟡 Emerging: social posts only, not yet confirmed", ""]
        for view in emerging:
            lines.append(f"- {view.title} [S{view.id}]")
        lines.append("")

    minor = groups.get("minor", [])
    if minor:
        lines += [f"## ⚪ Minor: {len(minor)} smaller updates are in the feed", ""]
    return "\n".join(lines).strip() + "\n"
