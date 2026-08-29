import json
from unittest.mock import patch

from pipeline import run, tts
from pipeline.fetch import PostRef


def _p(i):
    return PostRef(log_no=str(i), title=f"t{i}", published="2026-08-30T08:05:08+09:00", url=f"u{i}")


def test_select_pending_backfill_when_index_empty():
    posts = [_p(i) for i in range(50, 0, -1)]  # newest first: 50..1
    sel = run.select_pending(posts, index=[], backfill=30)
    assert [p.log_no for p in sel] == [str(i) for i in range(21, 51)]  # oldest first


def test_select_pending_skips_done_and_ignores_backfill_when_index_nonempty():
    posts = [_p(i) for i in range(50, 0, -1)]
    index = [{"id": str(i)} for i in range(50, 45, -1)]  # 50..46 done
    sel = run.select_pending(posts, index=index, backfill=3)
    assert [p.log_no for p in sel] == [str(i) for i in range(1, 46)]


def test_process_post_writes_files(tmp_path):
    post = _p(7)
    with patch.object(run, "fetch_post_html", return_value="<html/>"), patch.object(
        run, "extract_sentences", return_value=["하나.", "둘."]
    ), patch.object(run, "synthesize", return_value=tts.SynthResult(b"MP3", [0.0, 1.5], 3.0)):
        entry = run.process_post(post, api_key="k", posts_dir=tmp_path)
    assert (tmp_path / "7.mp3").read_bytes() == b"MP3"
    meta = json.loads((tmp_path / "7.json").read_text(encoding="utf-8"))
    assert meta["sentences"] == [{"text": "하나.", "start": 0.0}, {"text": "둘.", "start": 1.5}]
    assert meta["title"] == "t7" and meta["duration"] == 3.0
    assert entry == {"id": "7", "title": "t7", "published": post.published, "duration": 3.0, "bytes": 3}


def test_main_continues_after_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "k")
    monkeypatch.setattr(run.config, "SITE_DIR", tmp_path)
    monkeypatch.setattr(run.config, "POSTS_DIR", tmp_path / "posts")
    monkeypatch.setattr(run.config, "INDEX_PATH", tmp_path / "index.json")
    monkeypatch.setattr(run.config, "FEED_PATH", tmp_path / "feed.xml")
    monkeypatch.setattr(run.config, "REQUEST_DELAY_SEC", 0)
    posts = [_p(2), _p(1)]

    def fake_process(post, api_key, posts_dir):
        if post.log_no == "1":
            raise RuntimeError("boom")
        return {"id": post.log_no, "title": post.title, "published": post.published, "duration": 1.0, "bytes": 1}

    with patch.object(run, "list_recent_posts", return_value=posts), patch.object(
        run, "process_post", side_effect=fake_process
    ):
        code = run.main([])
    assert code == 1
    index = json.loads((tmp_path / "index.json").read_text())
    assert [e["id"] for e in index] == ["2"]
    assert (tmp_path / "feed.xml").exists()
