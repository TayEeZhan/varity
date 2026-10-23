"""Collector registry: adapter name (sources.yaml) -> collector function."""

from trendsignal.collectors.arxiv import collect_arxiv
from trendsignal.collectors.base import Collector
from trendsignal.collectors.bluesky import collect_bluesky
from trendsignal.collectors.hf_papers import collect_hf_papers
from trendsignal.collectors.hn import collect_hn
from trendsignal.collectors.rss import collect_rss
from trendsignal.collectors.threads import collect_threads
from trendsignal.collectors.x_api import collect_x

ADAPTERS: dict[str, Collector] = {
    "rss": collect_rss,
    "arxiv": collect_arxiv,
    "hf_papers": collect_hf_papers,
    "hn": collect_hn,
    "bluesky": collect_bluesky,
    "x_api": collect_x,
    "threads": collect_threads,
}
