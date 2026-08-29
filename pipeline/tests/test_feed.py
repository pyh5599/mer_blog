import xml.etree.ElementTree as ET

from pipeline.feed import build_feed


def test_feed_has_items_with_enclosures():
    index = [{"id": "1", "title": "A & B", "published": "2026-08-30T08:05:08+09:00", "duration": 61.4, "bytes": 1234}]
    xml = build_feed(index, "https://u.github.io/mer_blog")
    root = ET.fromstring(xml)
    item = root.find("channel/item")
    assert item.findtext("title") == "A & B"
    enc = item.find("enclosure")
    assert enc.get("url") == "https://u.github.io/mer_blog/posts/1.mp3"
    assert enc.get("type") == "audio/mpeg" and enc.get("length") == "1234"
    assert item.findtext("{http://www.itunes.com/dtds/podcast-1.0.dtd}duration") == "00:01:01"
