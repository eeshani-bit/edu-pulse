#!/usr/bin/env python3
"""
Edu Pulse: fetches higher-education news from the feeds in config.json,
tags each item with topics, and writes news.json for the website.

Run locally:   pip install feedparser && python fetch_news.py
"""

import hashlib
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"
OUTPUT_PATH = ROOT / "news.json"
USER_AGENT = "Mozilla/5.0 (compatible; EduPulse/1.0; personal news reader)"

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


# ---------- helpers ----------

def clean_text(raw: str) -> str:
    text = html.unescape(TAG_RE.sub(" ", raw or ""))
    return SPACE_RE.sub(" ", text).strip()


def keyword_pattern(keyword: str) -> re.Pattern:
    """Short keywords (AI, UGC, fee) must match whole words.
    Longer ones match from the start of a word, so 'rank' catches 'rankings'."""
    escaped = re.escape(keyword.lower())
    if len(keyword) <= 3:
        return re.compile(rf"\b{escaped}\b")
    return re.compile(rf"\b{escaped}")


def build_matchers(categories: dict) -> dict:
    return {name: [keyword_pattern(k) for k in kws] for name, kws in categories.items()}


def categorise(title: str, summary: str, matchers: dict) -> list:
    """Title hit = 2 points, summary hit = 1 point. Keep topics scoring 2+ (max 3)."""
    t, s = title.lower(), summary.lower()
    scores = {}
    for name, patterns in matchers.items():
        score = 0
        for p in patterns:
            if p.search(t):
                score += 2
            elif p.search(s):
                score += 1
        if score >= 2:
            scores[name] = score
    ranked = sorted(scores, key=scores.get, reverse=True)[:3]
    return ranked or ["General"]


def looks_indian(text: str, patterns: list) -> bool:
    low = text.lower()
    return any(p.search(low) for p in patterns)


def entry_date(entry) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def item_id(url: str, title: str) -> str:
    return hashlib.sha1(f"{url}|{title}".encode("utf-8")).hexdigest()[:16]


def normalise_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


# ---------- main ----------

def fetch_source(source: dict, settings: dict, matchers: dict, india_patterns: list):
    parsed = feedparser.parse(source["url"], agent=USER_AGENT)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(str(parsed.get("bozo_exception", "feed could not be read")))

    is_google_news = "news.google.com" in source["url"]
    items = []

    for entry in parsed.entries[: settings["max_items_per_feed"]]:
        title = clean_text(entry.get("title", ""))
        link = entry.get("link", "")
        if not title or not link:
            continue

        # Google News appends " - Publisher" to titles and names the real source separately.
        source_name = source["name"]
        if is_google_news:
            publisher = ""
            if entry.get("source"):
                publisher = clean_text(entry["source"].get("title", ""))
            if publisher:
                suffix = f" - {publisher}"
                if title.endswith(suffix):
                    title = title[: -len(suffix)].strip()
                # Keep the publisher as the visible source for topic searches
                source_name = publisher
            summary = ""  # Google News summaries are just link lists
        else:
            summary = clean_text(entry.get("summary", ""))
            if len(summary) > 300:
                summary = summary[:297].rsplit(" ", 1)[0] + "..."
            if normalise_title(summary) == normalise_title(title):
                summary = ""

        region = source["region"]
        if region == "Global" and looks_indian(f"{title} {summary}", india_patterns):
            region = "India"

        items.append(
            {
                "id": item_id(link, title),
                "title": title,
                "url": link,
                "source": source_name,
                "region": region,
                "published": entry_date(entry).isoformat(),
                "summary": summary,
                "topics": categorise(title, summary, matchers),
            }
        )
    return items


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    settings = config["settings"]
    matchers = build_matchers(config["categories"])
    india_patterns = [keyword_pattern(k) for k in config["india_keywords"]]

    # Start from what we already have, so history builds up over time.
    existing = []
    if OUTPUT_PATH.exists():
        try:
            existing = json.loads(OUTPUT_PATH.read_text(encoding="utf-8")).get("items", [])
        except json.JSONDecodeError:
            existing = []

    fresh, report = [], []
    for source in config["sources"]:
        try:
            got = fetch_source(source, settings, matchers, india_patterns)
            fresh.extend(got)
            report.append((source["name"], len(got), "ok"))
        except Exception as exc:  # one broken feed must never stop the run
            report.append((source["name"], 0, f"FAILED: {exc}"))

    # Merge, dedupe by id and by near-identical title, drop old items.
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings["max_age_days"])
    merged, seen_ids, seen_titles = [], set(), set()
    for item in sorted(fresh + existing, key=lambda i: i["published"], reverse=True):
        norm = normalise_title(item["title"])
        if item["id"] in seen_ids or norm in seen_titles:
            continue
        if datetime.fromisoformat(item["published"]) < cutoff:
            continue
        seen_ids.add(item["id"])
        seen_titles.add(norm)
        merged.append(item)
    merged = merged[: settings["max_items_total"]]

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "categories": list(config["categories"].keys()) + ["General"],
        "items": merged,
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")

    # Summary shows up in the GitHub Actions log, so you can see which feeds broke.
    print(f"\nWrote {len(merged)} items to {OUTPUT_PATH.name}\n")
    width = max(len(name) for name, _, _ in report)
    for name, count, status in report:
        print(f"  {name.ljust(width)}  {str(count).rjust(3)}  {status}")
    ok = sum(1 for _, _, s in report if s == "ok")
    print(f"\n{ok}/{len(report)} sources worked.")

    # Only fail the run if *nothing* worked (e.g. no internet), so a bad feed doesn't block updates.
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
