"""Orchestration: RSS -> fetch -> clean -> TTS -> site/ files."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from . import config
from .clean import extract_sentences
from .feed import build_feed
from .fetch import PostRef, fetch_post_html, list_recent_posts
from .tts import synthesize

log = logging.getLogger("pipeline")


def load_index(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_index(path: Path, index: list[dict]) -> None:
    index.sort(key=lambda e: e["published"], reverse=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")


def select_pending(posts: list[PostRef], index: list[dict], backfill: int) -> list[PostRef]:
    """Posts not yet in index, oldest first.

    First run is capped to the `backfill` newest posts. Later runs only look at posts
    published on/after the oldest indexed post, so the remaining older RSS entries are
    never pulled in; a failed post inside that window is retried.
    """
    done = {e["id"] for e in index}
    pending = [p for p in posts if p.log_no not in done]  # newest first
    if not index:
        pending = pending[:backfill]
    else:
        floor = min(e["published"] for e in index)
        pending = [p for p in pending if p.published >= floor]
    return list(reversed(pending))


def process_post(post: PostRef, api_key: str, posts_dir: Path) -> dict:
    html = fetch_post_html(post.log_no)
    sentences = extract_sentences(html, title=post.title)
    result = synthesize(sentences, api_key=api_key)
    posts_dir.mkdir(parents=True, exist_ok=True)
    (posts_dir / f"{post.log_no}.mp3").write_bytes(result.mp3)
    meta = {
        "id": post.log_no,
        "title": post.title,
        "published": post.published,
        "url": post.url,
        "duration": result.duration,
        "sentences": [{"text": t, "start": s} for t, s in zip(sentences, result.starts)],
    }
    (posts_dir / f"{post.log_no}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return {
        "id": post.log_no,
        "title": post.title,
        "published": post.published,
        "duration": result.duration,
        "bytes": len(result.mp3),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Convert new blog posts to audio.")
    ap.add_argument("--limit", type=int, default=None, help="max posts to process this run")
    ap.add_argument("--backfill", type=int, default=config.DEFAULT_BACKFILL, help="posts to take on first run")
    ap.add_argument("--log-no", default=None, help="process only this post id (re-processes if exists)")
    ap.add_argument("--dry-run", action="store_true", help="list pending posts, do nothing")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    api_key = os.environ.get("GOOGLE_TTS_API_KEY", "")
    if not api_key and not args.dry_run:
        log.error("GOOGLE_TTS_API_KEY not set")
        return 2

    index = load_index(config.INDEX_PATH)
    posts = list_recent_posts()
    if args.log_no:
        pending = [p for p in posts if p.log_no == args.log_no]
    else:
        pending = select_pending(posts, index, args.backfill)
    if args.limit is not None:
        pending = pending[-args.limit :] if args.limit > 0 else []
    log.info("%d post(s) pending", len(pending))
    if args.dry_run:
        for p in pending:
            log.info("would process %s %s", p.log_no, p.title)
        return 0

    failed: list[str] = []
    for p in pending:
        try:
            log.info("processing %s %s", p.log_no, p.title)
            entry = process_post(p, api_key, config.POSTS_DIR)
            index = [e for e in index if e["id"] != entry["id"]] + [entry]
            save_index(config.INDEX_PATH, index)
            log.info("done %s (%.0fs audio)", p.log_no, entry["duration"])
        except Exception:
            log.exception("failed %s", p.log_no)
            failed.append(p.log_no)
        time.sleep(config.REQUEST_DELAY_SEC)

    config.FEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.FEED_PATH.write_text(build_feed(index, config.SITE_BASE_URL), encoding="utf-8")
    if failed:
        log.error("failed posts: %s", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
