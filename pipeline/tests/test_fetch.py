from pathlib import Path

from pipeline.fetch import parse_rss

FIX = Path(__file__).parent / "fixtures"


def test_parse_rss_returns_posts_newest_first():
    posts = parse_rss((FIX / "rss.xml").read_text(encoding="utf-8"))
    assert len(posts) == 50
    first = posts[0]
    assert first.log_no == "224394691017"
    assert first.title == "중국이 외국인을 들여다 보는 법"
    assert first.published == "2026-08-30T08:05:08+09:00"
    assert first.url == "https://blog.naver.com/ranto28/224394691017"
