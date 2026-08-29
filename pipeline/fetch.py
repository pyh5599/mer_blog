"""Naver blog RSS parsing and post HTML fetching."""
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

import requests

from . import config


@dataclass(frozen=True)
class PostRef:
    log_no: str
    title: str
    published: str  # ISO 8601 with offset
    url: str


def _iso(pubdate: str) -> str:
    return parsedate_to_datetime(pubdate).isoformat()


def parse_rss(xml_text: str) -> list[PostRef]:
    root = ET.fromstring(xml_text)
    posts = []
    for item in root.iter("item"):
        guid = (item.findtext("guid") or "").strip()
        log_no = guid.rstrip("/").rsplit("/", 1)[-1]
        if not log_no.isdigit():
            continue
        posts.append(
            PostRef(
                log_no=log_no,
                title=(item.findtext("title") or "").strip(),
                published=_iso(item.findtext("pubDate") or ""),
                url=config.POST_PUBLIC_URL.format(log_no=log_no),
            )
        )
    return posts


def _get(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=config.REQUEST_TIMEOUT)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def list_recent_posts() -> list[PostRef]:
    return parse_rss(_get(config.RSS_URL))


def fetch_post_html(log_no: str) -> str:
    return _get(config.POST_URL.format(blog_id=config.BLOG_ID, log_no=log_no))
