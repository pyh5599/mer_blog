"""Podcast-style RSS feed built from index.json entries."""
from __future__ import annotations

from datetime import datetime
from email.utils import format_datetime
from xml.sax.saxutils import escape

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"


def _hms(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _rfc822(iso: str) -> str:
    return format_datetime(datetime.fromisoformat(iso))


def build_feed(index: list[dict], base_url: str) -> str:
    base_url = base_url.rstrip("/")
    items = []
    for e in index:
        url = f"{base_url}/posts/{e['id']}.mp3"
        items.append(
            "<item>"
            f"<title>{escape(e['title'])}</title>"
            f'<guid isPermaLink="false">{e["id"]}</guid>'
            f"<link>{escape(base_url)}/#{e['id']}</link>"
            f"<pubDate>{_rfc822(e['published'])}</pubDate>"
            f'<enclosure url="{url}" type="audio/mpeg" length="{int(e.get("bytes", 0))}"/>'
            f"<itunes:duration>{_hms(float(e['duration']))}</itunes:duration>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<rss version="2.0" xmlns:itunes="{ITUNES}"><channel>'
        "<title>메르의 블로그 (오디오)</title>"
        f"<link>{escape(base_url)}/</link>"
        "<language>ko</language>"
        "<description>메르의 블로그 글을 TTS로 읽어줍니다.</description>"
        "<itunes:author>메르</itunes:author>" + "".join(items) + "</channel></rss>"
    )
