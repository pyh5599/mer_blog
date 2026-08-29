# 메르의 블로그 오디오 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버 블로그 `ranto28`의 글을 매일 자동으로 TTS mp3 + 문장 타임스탬프로 변환하고, Android Chrome에서 캡션과 함께 듣는 정적 PWA를 GitHub Pages에 배포한다.

**Architecture:** Python 파이프라인(`pipeline/`)이 RSS → HTML 크롤링 → 문장 정제 → Google TTS(SSML mark 타임포인트) → `site/posts/*.mp3|json` + `site/index.json` + `site/feed.xml`을 생성한다. GitHub Actions cron이 파이프라인을 돌리고 `site/`를 커밋한 뒤 Pages로 배포한다. 프론트는 vanilla HTML/JS 단일 페이지.

**Tech Stack:** Python 3.11, requests, beautifulsoup4, mutagen(mp3 길이), pytest; vanilla HTML/CSS/JS, Media Session API, Service Worker; GitHub Actions + Pages.

**Spec:** `docs/superpowers/specs/2026-08-30-mer-blog-audio-design.md`

## Global Constraints

- Blog ID `ranto28`, RSS `https://rss.blog.naver.com/ranto28.xml`, 본문 `https://blog.naver.com/PostView.naver?blogId=ranto28&logNo=<id>`
- TTS voice `ko-KR-Neural2-A`, REST `https://texttospeech.googleapis.com/v1beta1/text:synthesize?key=...`, env `GOOGLE_TTS_API_KEY`
- SSML 청크 4,500바이트 이하
- ffmpeg 사용 안 함: mp3 청크는 바이트 결합(CBR), 길이는 mutagen으로 측정
- 백필 기본 30개, `index.json` 최신순
- `site/`가 Pages 루트. 모든 프론트 경로는 상대 경로 (`./`)
- 로컬 venv: `.venv/bin/python`, `.venv/bin/pytest`

---

### Task 1: config + fetch (RSS, PostView)

**Files:**
- Create: `requirements.txt`, `pipeline/__init__.py`, `pipeline/config.py`, `pipeline/fetch.py`
- Test: `pipeline/tests/__init__.py`, `pipeline/tests/test_fetch.py` (fixture `pipeline/tests/fixtures/rss.xml` 이미 존재)

**Interfaces:**
- Produces: `PostRef(log_no: str, title: str, published: str, url: str)` dataclass; `parse_rss(xml_text) -> list[PostRef]`; `list_recent_posts() -> list[PostRef]`; `fetch_post_html(log_no) -> str`

- [ ] **Step 1: 테스트 작성**

```python
# pipeline/tests/test_fetch.py
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
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest pipeline/tests/test_fetch.py -v` → ImportError

- [ ] **Step 3: 구현**

```
# requirements.txt
requests>=2.31
beautifulsoup4>=4.12
mutagen>=1.47
pytest>=8
```

```python
# pipeline/config.py
import os
from pathlib import Path

BLOG_ID = "ranto28"
RSS_URL = f"https://rss.blog.naver.com/{BLOG_ID}.xml"
POST_URL = "https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"
POST_PUBLIC_URL = f"https://blog.naver.com/{BLOG_ID}/{{log_no}}"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
REQUEST_TIMEOUT = 20
REQUEST_DELAY_SEC = 1.5

LANGUAGE_CODE = "ko-KR"
VOICE_NAME = os.environ.get("TTS_VOICE", "ko-KR-Neural2-A")
SPEAKING_RATE = 1.0
MAX_SSML_BYTES = 4500
TTS_ENDPOINT = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "site"
POSTS_DIR = SITE_DIR / "posts"
INDEX_PATH = SITE_DIR / "index.json"
FEED_PATH = SITE_DIR / "feed.xml"
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://example.github.io/mer_blog").rstrip("/")
DEFAULT_BACKFILL = 30
```

```python
# pipeline/fetch.py
from dataclasses import dataclass
from datetime import datetime
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
        posts.append(PostRef(
            log_no=log_no,
            title=(item.findtext("title") or "").strip(),
            published=_iso(item.findtext("pubDate") or ""),
            url=config.POST_PUBLIC_URL.format(log_no=log_no),
        ))
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
```

- [ ] **Step 4: 통과 확인** — `.venv/bin/pytest pipeline/tests/test_fetch.py -v` → PASS
- [ ] **Step 5: Commit** — `git add requirements.txt pipeline && git commit -m "feat(pipeline): rss parsing and post fetch"`

---

### Task 2: clean — HTML → 문장 배열

**Files:**
- Create: `pipeline/clean.py`
- Test: `pipeline/tests/test_clean.py` (fixture `post_224394691017.html` 이미 존재)

**Interfaces:**
- Produces: `extract_sentences(html: str, title: str | None = None) -> list[str]`; `split_sentences(text) -> list[str]`; `EmptyPostError`

- [ ] **Step 1: 테스트 작성**

```python
# pipeline/tests/test_clean.py
from pathlib import Path
import pytest
from pipeline.clean import extract_sentences, split_sentences, EmptyPostError

FIX = Path(__file__).parent / "fixtures"
HTML = (FIX / "post_224394691017.html").read_text(encoding="utf-8")

def test_extract_real_post():
    s = extract_sentences(HTML, title="중국이 외국인을 들여다 보는 법")
    assert s[0] == "주말이라 일반적인 시사 내용입니다."
    assert s[1].startswith("1. 2026년 8월초")
    assert all("​" not in x for x in s)
    assert all(x.strip() == x and x for x in s)
    assert 40 <= len(s) <= 80

def test_title_line_removed():
    s = extract_sentences(HTML, title="중국이 외국인을 들여다 보는 법")
    assert "중국이 외국인을 들여다 보는 법" not in s

def test_captions_and_oglinks_excluded():
    html = '''<div class="se-main-container">
      <p class="se-text-paragraph"><span>본문 문장임.</span></p>
      <div class="se-caption"><p class="se-text-paragraph"><span>캡션 제외</span></p></div>
      <div class="se-oglink"><p class="se-text-paragraph"><span>링크 제외</span></p></div>
      <div class="se-table"><p class="se-text-paragraph"><span>표 제외</span></p></div>
    </div><div class="se-section-end"></div>'''
    assert extract_sentences(html) == ["본문 문장임."]

def test_legacy_editor_fallback():
    html = '<div id="postViewArea"><p>옛날 글임.</p><div>두번째 줄.</div></div>'
    assert extract_sentences(html) == ["옛날 글임.", "두번째 줄."]

def test_empty_raises():
    with pytest.raises(EmptyPostError):
        extract_sentences('<div class="se-main-container"></div>')

def test_split_sentences():
    assert split_sentences("첫 문장임. 둘째 문장임! 셋째?") == ["첫 문장임.", "둘째 문장임!", "셋째?"]
    assert split_sentences("1. 항목임. 2. 다음 항목임.") == ["1. 항목임.", "2. 다음 항목임."]
    assert split_sentences("금리가 3.5%로 올랐음.") == ["금리가 3.5%로 올랐음."]
    assert split_sentences('"인용문임." 그 다음.') == ['"인용문임."', "그 다음."]
    assert split_sentences("링크 https://x.com/abc 참고.") == ["링크 참고."]
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest pipeline/tests/test_clean.py -v` → ImportError

- [ ] **Step 3: 구현**

```python
# pipeline/clean.py
import re
from bs4 import BeautifulSoup

class EmptyPostError(Exception):
    pass

EXCLUDE_CLASSES = ("se-caption", "se-oglink", "se-table", "se-code")
_ZW = re.compile(r"[​‌‍﻿]")
_URL = re.compile(r"https?://\S+|www\.\S+")
_WS = re.compile(r"\s+")
_BOUNDARY = re.compile(r'[.?!][\"\')\]”’]*\s+(?!\d+\.\s)')

def normalize(text: str) -> str:
    text = _ZW.sub("", text)
    text = _URL.sub("", text)
    text = _WS.sub(" ", text).strip()
    return text

def split_sentences(text: str) -> list[str]:
    text = normalize(text)
    if not text:
        return []
    out, pos = [], 0
    for m in _BOUNDARY.finditer(text):
        end = m.end() - len(m.group().lstrip(".?!\"')]”’").lstrip()) if False else None
        # cut right after the punctuation+closing chars, before whitespace
        cut = m.start() + len(m.group().rstrip())
        out.append(text[pos:cut].strip())
        pos = m.end()
    out.append(text[pos:].strip())
    return [s for s in out if s]

def _paragraph_texts(soup: BeautifulSoup) -> list[str]:
    main = soup.select_one("div.se-main-container")
    if main is not None:
        for cls in EXCLUDE_CLASSES:
            for node in main.select(f".{cls}"):
                node.decompose()
        return [p.get_text(" ", strip=True) for p in main.select("p.se-text-paragraph")]
    legacy = soup.select_one("#postViewArea")
    if legacy is not None:
        return [n.get_text(" ", strip=True) for n in legacy.find_all(["p", "div"]) if not n.find(["p", "div"])]
    return []

def extract_sentences(html: str, title: str | None = None) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    sentences: list[str] = []
    for para in _paragraph_texts(soup):
        sentences.extend(split_sentences(para))
    if title and sentences and normalize(sentences[0]) == normalize(title):
        sentences = sentences[1:]
    if not sentences:
        raise EmptyPostError("no text paragraphs found")
    return sentences
```

주의: `split_sentences` 안의 `end = ...` 줄은 넣지 말 것 — `cut` 계산만 사용. (최종 코드는 아래 단순 버전)

```python
def split_sentences(text: str) -> list[str]:
    text = normalize(text)
    if not text:
        return []
    out, pos = [], 0
    for m in _BOUNDARY.finditer(text):
        cut = m.start() + len(m.group().rstrip())
        out.append(text[pos:cut].strip())
        pos = m.end()
    out.append(text[pos:].strip())
    return [s for s in out if s]
```

- [ ] **Step 4: 통과 확인** — `.venv/bin/pytest pipeline/tests/test_clean.py -v` → PASS. 실패하면 fixture 실제 문장 수 확인해 범위 조정.
- [ ] **Step 5: Commit** — `git commit -m "feat(pipeline): html to sentence extraction"`

---

### Task 3: tts — 청킹, Google TTS, 타임스탬프 결합

**Files:**
- Create: `pipeline/tts.py`
- Test: `pipeline/tests/test_tts.py`

**Interfaces:**
- Consumes: `config.MAX_SSML_BYTES`, `config.VOICE_NAME`, `config.TTS_ENDPOINT`
- Produces: `chunk_sentences(sentences, max_bytes) -> list[list[int]]` (문장 인덱스 그룹); `build_ssml(sentences, indices) -> str`; `synthesize(sentences, api_key, voice=None) -> SynthResult(mp3: bytes, starts: list[float], duration: float)`; `mp3_duration(data) -> float`; `estimate_starts(sentences, total) -> list[float]`

- [ ] **Step 1: 테스트 작성**

```python
# pipeline/tests/test_tts.py
import base64
from unittest.mock import patch
from pipeline import tts

def test_chunk_respects_byte_limit_and_keeps_order():
    sents = ["가" * 100] * 30  # each ~300 bytes utf-8
    chunks = tts.chunk_sentences(sents, max_bytes=1000)
    flat = [i for c in chunks for i in c]
    assert flat == list(range(30))
    for c in chunks:
        assert len(tts.build_ssml(sents, c).encode("utf-8")) <= 1000

def test_oversized_single_sentence_gets_own_chunk():
    sents = ["가" * 2000, "짧음"]
    chunks = tts.chunk_sentences(sents, max_bytes=1000)
    assert chunks == [[0], [1]]

def test_build_ssml_escapes_and_marks():
    ssml = tts.build_ssml(["A & B <c>", "둘"], [0, 1])
    assert '<mark name="s0"/>' in ssml and '<mark name="s1"/>' in ssml
    assert "&amp;" in ssml and "&lt;c&gt;" in ssml
    assert ssml.startswith("<speak>") and ssml.endswith("</speak>")

def test_estimate_starts_proportional():
    starts = tts.estimate_starts(["가" * 10, "가" * 30], total=8.0)
    assert starts == [0.0, 2.0]

def test_synthesize_accumulates_offsets():
    sents = ["가" * 100] * 6
    calls = []
    def fake_request(ssml, api_key, voice):
        calls.append(ssml)
        n = ssml.count("<mark")
        return b"MP3" + bytes([len(calls)]), [{"markName": f"s{i}", "timeSeconds": i * 1.0} for i in range(n)]
    with patch.object(tts, "_request", side_effect=fake_request), \
         patch.object(tts, "mp3_duration", return_value=10.0), \
         patch.object(tts.config, "MAX_SSML_BYTES", 1000):
        res = tts.synthesize(sents, api_key="k")
    assert len(calls) == 2
    assert res.starts == [0.0, 1.0, 2.0, 10.0, 11.0, 12.0]
    assert res.duration == 20.0
    assert res.mp3 == b"MP3\x01MP3\x02"

def test_synthesize_falls_back_when_no_timepoints():
    sents = ["가" * 10, "가" * 30]
    with patch.object(tts, "_request", return_value=(b"X", [])), \
         patch.object(tts, "mp3_duration", return_value=8.0):
        res = tts.synthesize(sents, api_key="k")
    assert res.starts == [0.0, 2.0]
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest pipeline/tests/test_tts.py -v` → ImportError

- [ ] **Step 3: 구현**

```python
# pipeline/tts.py
import base64
import io
import logging
import time
from dataclasses import dataclass
from xml.sax.saxutils import escape
import requests
from mutagen.mp3 import MP3
from . import config

log = logging.getLogger(__name__)

@dataclass
class SynthResult:
    mp3: bytes
    starts: list[float]
    duration: float

def _sentence_ssml(i: int, text: str) -> str:
    return f'<mark name="s{i}"/>{escape(text)}<break time="300ms"/>'

def build_ssml(sentences: list[str], indices: list[int]) -> str:
    return "<speak>" + "".join(_sentence_ssml(i, sentences[i]) for i in indices) + "</speak>"

def chunk_sentences(sentences: list[str], max_bytes: int | None = None) -> list[list[int]]:
    max_bytes = max_bytes or config.MAX_SSML_BYTES
    wrap = len("<speak></speak>".encode())
    chunks, cur, cur_bytes = [], [], wrap
    for i, s in enumerate(sentences):
        b = len(_sentence_ssml(i, s).encode("utf-8"))
        if cur and cur_bytes + b > max_bytes:
            chunks.append(cur)
            cur, cur_bytes = [], wrap
        cur.append(i)
        cur_bytes += b
    if cur:
        chunks.append(cur)
    return chunks

def mp3_duration(data: bytes) -> float:
    return float(MP3(io.BytesIO(data)).info.length)

def estimate_starts(sentences: list[str], total: float) -> list[float]:
    weights = [max(len(s), 1) for s in sentences]
    total_w = sum(weights)
    starts, acc = [], 0
    for w in weights:
        starts.append(round(total * acc / total_w, 3))
        acc += w
    return starts

def _request(ssml: str, api_key: str, voice: str) -> tuple[bytes, list[dict]]:
    body = {
        "input": {"ssml": ssml},
        "voice": {"languageCode": config.LANGUAGE_CODE, "name": voice},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": config.SPEAKING_RATE},
        "enableTimePointing": ["SSML_MARK"],
    }
    delay = 2.0
    for attempt in range(4):
        r = requests.post(config.TTS_ENDPOINT, params={"key": api_key}, json=body, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == 3:
                r.raise_for_status()
            log.warning("tts http %s, retry in %.0fs", r.status_code, delay)
            time.sleep(delay)
            delay *= 2
            continue
        r.raise_for_status()
        data = r.json()
        return base64.b64decode(data["audioContent"]), data.get("timepoints", [])
    raise RuntimeError("unreachable")

def synthesize(sentences: list[str], api_key: str, voice: str | None = None) -> SynthResult:
    voice = voice or config.VOICE_NAME
    starts: list[float] = []
    parts: list[bytes] = []
    offset = 0.0
    fallback = False
    for indices in chunk_sentences(sentences):
        ssml = build_ssml(sentences, indices)
        audio, timepoints = _request(ssml, api_key, voice)
        dur = mp3_duration(audio)
        by_mark = {tp["markName"]: float(tp["timeSeconds"]) for tp in timepoints}
        if len(by_mark) == len(indices):
            starts.extend(round(offset + by_mark[f"s{i}"], 3) for i in indices)
        else:
            fallback = True
            chunk_sents = [sentences[i] for i in indices]
            starts.extend(round(offset + s, 3) for s in estimate_starts(chunk_sents, dur))
        parts.append(audio)
        offset += dur
    if fallback:
        log.warning("timepoints missing for some chunks; used length-based estimate")
    return SynthResult(mp3=b"".join(parts), starts=starts, duration=round(offset, 3))
```

- [ ] **Step 4: 통과 확인** — `.venv/bin/pytest pipeline/tests/test_tts.py -v` → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(pipeline): google tts synthesis with sentence timepoints"`

---

### Task 4: feed.xml 생성

**Files:**
- Create: `pipeline/feed.py`
- Test: `pipeline/tests/test_feed.py`

**Interfaces:**
- Produces: `build_feed(index: list[dict], base_url: str) -> str` — index 항목은 `{id, title, published, duration}` (+ optional `bytes`)

- [ ] **Step 1: 테스트**

```python
# pipeline/tests/test_feed.py
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
```

- [ ] **Step 2: 실패 확인** → ImportError
- [ ] **Step 3: 구현**

```python
# pipeline/feed.py
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
            f"<guid isPermaLink=\"false\">{e['id']}</guid>"
            f"<link>{escape(base_url)}/#{e['id']}</link>"
            f"<pubDate>{_rfc822(e['published'])}</pubDate>"
            f"<enclosure url=\"{url}\" type=\"audio/mpeg\" length=\"{int(e.get('bytes', 0))}\"/>"
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
        "<itunes:author>메르</itunes:author>"
        + "".join(items) + "</channel></rss>"
    )
```

- [ ] **Step 4: 통과 확인**, **Step 5: Commit** — `git commit -m "feat(pipeline): podcast rss feed"`

---

### Task 5: run.py 오케스트레이션 + CLI

**Files:**
- Create: `pipeline/run.py`
- Test: `pipeline/tests/test_run.py`

**Interfaces:**
- Consumes: Task 1~4 전부
- Produces: `select_pending(posts, index, backfill) -> list[PostRef]` (오래된 것부터); `process_post(post, api_key, posts_dir) -> dict` (index entry); `main(argv) -> int`

- [ ] **Step 1: 테스트**

```python
# pipeline/tests/test_run.py
import json
from unittest.mock import patch
from pipeline.fetch import PostRef
from pipeline import run, tts

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
    with patch.object(run, "fetch_post_html", return_value="<html/>"), \
         patch.object(run, "extract_sentences", return_value=["하나.", "둘."]), \
         patch.object(run, "synthesize", return_value=tts.SynthResult(b"MP3", [0.0, 1.5], 3.0)):
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
    with patch.object(run, "list_recent_posts", return_value=posts), \
         patch.object(run, "process_post", side_effect=fake_process):
        code = run.main([])
    assert code == 1
    index = json.loads((tmp_path / "index.json").read_text())
    assert [e["id"] for e in index] == ["2"]
    assert (tmp_path / "feed.xml").exists()
```

- [ ] **Step 2: 실패 확인** → ImportError
- [ ] **Step 3: 구현**

```python
# pipeline/run.py
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
    done = {e["id"] for e in index}
    pending = [p for p in posts if p.log_no not in done]  # newest first
    if not index:
        pending = pending[:backfill]
    return list(reversed(pending))  # oldest first

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
    return {"id": post.log_no, "title": post.title, "published": post.published,
            "duration": result.duration, "bytes": len(result.mp3)}

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="max posts to process this run")
    ap.add_argument("--backfill", type=int, default=config.DEFAULT_BACKFILL)
    ap.add_argument("--log-no", default=None, help="process only this post id")
    ap.add_argument("--dry-run", action="store_true")
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
        pending = pending[-args.limit:]
    log.info("%d post(s) pending", len(pending))
    if args.dry_run:
        for p in pending:
            log.info("would process %s %s", p.log_no, p.title)
        return 0

    failed = []
    for p in pending:
        try:
            log.info("processing %s %s", p.log_no, p.title)
            entry = process_post(p, api_key, config.POSTS_DIR)
            index = [e for e in index if e["id"] != entry["id"]] + [entry]
            save_index(config.INDEX_PATH, index)
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
```

- [ ] **Step 4: 통과 확인** — `.venv/bin/pytest pipeline -v` 전체 PASS. `.venv/bin/python -m pipeline.run --dry-run` 실행해 "30 post(s) pending" 로그 확인.
- [ ] **Step 5: Commit** — `git commit -m "feat(pipeline): run orchestration and cli"`

---

### Task 6: 웹 앱 — 목록 + 플레이어 + 캡션

**Files:**
- Create: `site/index.html`, `site/style.css`, `site/app.js`
- Test: 수동. `site/posts/` 샘플 없이도 UI 확인하려면 `site/index.json`에 임시 항목 + 아무 mp3. 확인 후 임시 파일 삭제.

**Interfaces:**
- Consumes: `index.json` `[{id,title,published,duration}]`, `posts/<id>.json` `{title, sentences:[{text,start}], duration}`, `posts/<id>.mp3`

- [ ] **Step 1: index.html**

```html
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#1f2937">
<title>메르의 블로그</title>
<link rel="manifest" href="./manifest.webmanifest">
<link rel="icon" href="./icon.svg" type="image/svg+xml">
<link rel="stylesheet" href="./style.css">
</head>
<body>
<header class="bar">
  <button id="back" class="icon hidden" aria-label="목록으로">←</button>
  <h1 id="title">메르의 블로그</h1>
  <div class="font-ctl">
    <button id="font-down" class="icon" aria-label="글씨 작게">A−</button>
    <button id="font-up" class="icon" aria-label="글씨 크게">A+</button>
  </div>
</header>

<main id="list" class="view"></main>

<main id="player" class="view hidden">
  <article id="captions"></article>
  <footer class="controls">
    <input id="seek" type="range" min="0" max="1000" value="0" aria-label="재생 위치">
    <div class="times"><span id="cur">0:00</span><span id="dur">0:00</span></div>
    <div class="buttons">
      <button id="prev" class="icon" aria-label="이전 글">⏮</button>
      <button id="back15" class="icon" aria-label="15초 뒤로">↺15</button>
      <button id="play" class="icon big" aria-label="재생">▶</button>
      <button id="fwd15" class="icon" aria-label="15초 앞으로">↻15</button>
      <button id="rate" class="icon" aria-label="배속">1.0×</button>
    </div>
  </footer>
</main>

<div id="toast" class="hidden"></div>
<audio id="audio" preload="metadata"></audio>
<script src="./app.js"></script>
</body>
</html>
```

- [ ] **Step 2: style.css**

```css
:root {
  --bg: #ffffff; --fg: #111827; --muted: #6b7280; --card: #f3f4f6;
  --accent: #2563eb; --active-bg: #fef3c7; --bar: #1f2937; --bar-fg: #ffffff;
  --font: 22px;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #0f172a; --fg: #f1f5f9; --muted: #94a3b8; --card: #1e293b;
          --active-bg: #3b3a1f; --bar: #020617; }
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--bg); color: var(--fg);
  font-family: -apple-system, "Noto Sans KR", "Apple SD Gothic Neo", sans-serif; }
.hidden { display: none !important; }
.bar { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: 8px;
  padding: 12px 14px; background: var(--bar); color: var(--bar-fg);
  padding-top: max(12px, env(safe-area-inset-top)); }
.bar h1 { flex: 1; margin: 0; font-size: 17px; font-weight: 600; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.icon { background: transparent; border: 1px solid rgba(255,255,255,.35); color: inherit;
  border-radius: 8px; padding: 8px 12px; font-size: 16px; min-width: 44px; min-height: 44px; }
.font-ctl { display: flex; gap: 6px; }
#list { padding: 12px; display: grid; gap: 10px; }
.card { background: var(--card); border-radius: 12px; padding: 14px; cursor: pointer; }
.card h2 { margin: 0 0 6px; font-size: 18px; line-height: 1.35; }
.card .meta { color: var(--muted); font-size: 14px; display: flex; gap: 10px; }
.card .done { color: var(--accent); }
.progress { height: 4px; background: rgba(127,127,127,.25); border-radius: 2px; margin-top: 10px; }
.progress > div { height: 100%; background: var(--accent); border-radius: 2px; }
#player { display: flex; flex-direction: column; min-height: calc(100vh - 68px); }
#captions { flex: 1; padding: 20px 18px 45vh; font-size: var(--font); line-height: 1.7; }
#captions p { margin: 0 0 .7em; padding: 6px 10px; border-radius: 8px; color: var(--muted);
  transition: background .2s, color .2s; }
#captions p.active { background: var(--active-bg); color: var(--fg); font-weight: 600; }
#captions p.past { color: var(--muted); opacity: .6; }
.controls { position: fixed; bottom: 0; left: 0; right: 0; background: var(--bar); color: var(--bar-fg);
  padding: 10px 14px; padding-bottom: max(10px, env(safe-area-inset-bottom)); }
.controls input[type=range] { width: 100%; accent-color: var(--accent); }
.times { display: flex; justify-content: space-between; font-size: 13px; opacity: .8; }
.buttons { display: flex; justify-content: space-between; align-items: center; margin-top: 6px; }
.buttons .big { font-size: 26px; min-width: 64px; min-height: 56px; background: var(--accent); border: none; }
#toast { position: fixed; top: 70px; left: 50%; transform: translateX(-50%); background: #dc2626;
  color: #fff; padding: 10px 16px; border-radius: 8px; z-index: 3; }
```

- [ ] **Step 3: app.js**

```javascript
(() => {
  const $ = (id) => document.getElementById(id);
  const audio = $("audio");
  const FONT_SIZES = [18, 22, 26, 30];
  const RATES = [1.0, 1.2, 1.5, 2.0];
  const state = { index: [], current: null, sentences: [], activeIdx: -1, userScrollUntil: 0, rateIdx: 0 };

  const ls = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };
  const fmt = (s) => { s = Math.max(0, Math.floor(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  const toast = (msg) => { const t = $("toast"); t.textContent = msg; t.classList.remove("hidden"); setTimeout(() => t.classList.add("hidden"), 3000); };

  // ---- font size
  let fontIdx = ls.get("fontIdx", 1);
  const applyFont = () => { document.documentElement.style.setProperty("--font", FONT_SIZES[fontIdx] + "px"); ls.set("fontIdx", fontIdx); };
  $("font-up").onclick = () => { fontIdx = Math.min(FONT_SIZES.length - 1, fontIdx + 1); applyFont(); };
  $("font-down").onclick = () => { fontIdx = Math.max(0, fontIdx - 1); applyFont(); };
  applyFont();

  // ---- list view
  async function loadIndex() {
    const list = $("list");
    list.innerHTML = "<p style='padding:20px;color:var(--muted)'>불러오는 중…</p>";
    try {
      const r = await fetch("./index.json", { cache: "no-cache" });
      if (!r.ok) throw new Error(r.status);
      state.index = await r.json();
      renderList();
    } catch (e) {
      list.innerHTML = "<div class='card'><h2>불러오기 실패</h2><button id='retry' class='icon' style='border-color:var(--muted)'>다시 시도</button></div>";
      $("retry").onclick = loadIndex;
    }
  }
  function renderList() {
    const list = $("list");
    list.innerHTML = "";
    for (const e of state.index) {
      const pos = ls.get("pos:" + e.id, 0);
      const done = ls.get("done:" + e.id, false);
      const pct = done ? 100 : Math.min(100, Math.round(100 * pos / (e.duration || 1)));
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `<h2>${escapeHtml(e.title)}</h2>
        <div class="meta"><span>${e.published.slice(0, 10)}</span><span>${Math.round(e.duration / 60)}분</span>${done ? '<span class="done">✓ 들음</span>' : ""}</div>
        <div class="progress"><div style="width:${pct}%"></div></div>`;
      card.onclick = () => openPost(e.id);
      list.appendChild(card);
    }
  }
  const escapeHtml = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ---- player view
  async function openPost(id, autoplay = false) {
    const entry = state.index.find((e) => e.id === id);
    if (!entry) return;
    try {
      const r = await fetch(`./posts/${id}.json`);
      if (!r.ok) throw new Error(r.status);
      const meta = await r.json();
      state.current = entry; state.sentences = meta.sentences; state.activeIdx = -1;
    } catch (e) { toast("글을 불러오지 못했습니다"); return; }

    location.hash = id;
    $("title").textContent = entry.title;
    $("back").classList.remove("hidden");
    $("list").classList.add("hidden");
    $("player").classList.remove("hidden");
    const cap = $("captions");
    cap.innerHTML = "";
    state.sentences.forEach((s, i) => {
      const p = document.createElement("p");
      p.textContent = s.text; p.dataset.i = i;
      p.onclick = () => { audio.currentTime = s.start; audio.play(); };
      cap.appendChild(p);
    });
    window.scrollTo(0, 0);
    audio.src = `./posts/${id}.mp3`;
    audio.playbackRate = RATES[state.rateIdx];
    const pos = ls.get("pos:" + id, 0);
    audio.addEventListener("loadedmetadata", () => { if (pos > 0 && pos < audio.duration - 5) audio.currentTime = pos; }, { once: true });
    $("dur").textContent = fmt(entry.duration);
    setMediaSession(entry);
    if (autoplay) audio.play().catch(() => {});
  }
  function closePost() {
    savePos();
    audio.pause();
    location.hash = "";
    $("title").textContent = "메르의 블로그";
    $("back").classList.add("hidden");
    $("player").classList.add("hidden");
    $("list").classList.remove("hidden");
    renderList();
  }
  $("back").onclick = closePost;

  function savePos() {
    if (!state.current) return;
    ls.set("pos:" + state.current.id, audio.currentTime);
  }
  function neighbor(delta) {
    const i = state.index.findIndex((e) => e.id === state.current.id);
    return state.index[i + delta];
  }

  // ---- caption sync
  function findActive(t) {
    const s = state.sentences; let lo = 0, hi = s.length - 1, ans = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (s[mid].start <= t + 0.05) { ans = mid; lo = mid + 1; } else hi = mid - 1; }
    return ans;
  }
  function updateCaption() {
    const idx = findActive(audio.currentTime);
    if (idx === state.activeIdx) return;
    const ps = $("captions").children;
    if (state.activeIdx >= 0 && ps[state.activeIdx]) { ps[state.activeIdx].classList.remove("active"); ps[state.activeIdx].classList.add("past"); }
    state.activeIdx = idx;
    if (idx < 0) return;
    for (let i = idx; i < ps.length; i++) ps[i].classList.remove("past");
    ps[idx].classList.add("active");
    if (Date.now() > state.userScrollUntil) ps[idx].scrollIntoView({ block: "center", behavior: "smooth" });
  }
  let lastSave = 0;
  audio.addEventListener("timeupdate", () => {
    updateCaption();
    $("cur").textContent = fmt(audio.currentTime);
    if (audio.duration) $("seek").value = Math.round(1000 * audio.currentTime / audio.duration);
    if (Date.now() - lastSave > 5000) { savePos(); lastSave = Date.now(); }
  });
  audio.addEventListener("play", () => { $("play").textContent = "⏸"; });
  audio.addEventListener("pause", () => { $("play").textContent = "▶"; savePos(); });
  audio.addEventListener("ended", () => {
    ls.set("done:" + state.current.id, true); ls.set("pos:" + state.current.id, 0);
    const next = neighbor(1);
    if (next) openPost(next.id, true); else closePost();
  });
  audio.addEventListener("error", () => toast("오디오를 불러오지 못했습니다"));
  ["wheel", "touchmove"].forEach((ev) => window.addEventListener(ev, () => { state.userScrollUntil = Date.now() + 5000; }, { passive: true }));

  // ---- controls
  $("play").onclick = () => (audio.paused ? audio.play() : audio.pause());
  $("back15").onclick = () => { audio.currentTime = Math.max(0, audio.currentTime - 15); };
  $("fwd15").onclick = () => { audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 15); };
  $("prev").onclick = () => { const p = neighbor(-1); if (p) { savePos(); openPost(p.id, !audio.paused); } };
  $("rate").onclick = () => { state.rateIdx = (state.rateIdx + 1) % RATES.length; audio.playbackRate = RATES[state.rateIdx]; $("rate").textContent = RATES[state.rateIdx].toFixed(1) + "×"; ls.set("rateIdx", state.rateIdx); };
  state.rateIdx = ls.get("rateIdx", 0); $("rate").textContent = RATES[state.rateIdx].toFixed(1) + "×";
  $("seek").oninput = (e) => { if (audio.duration) audio.currentTime = audio.duration * e.target.value / 1000; };

  function setMediaSession(entry) {
    if (!("mediaSession" in navigator)) return;
    navigator.mediaSession.metadata = new MediaMetadata({ title: entry.title, artist: "메르의 블로그", artwork: [{ src: "./icon.svg", sizes: "any", type: "image/svg+xml" }] });
    const h = (a, f) => { try { navigator.mediaSession.setActionHandler(a, f); } catch {} };
    h("play", () => audio.play()); h("pause", () => audio.pause());
    h("seekbackward", () => $("back15").onclick()); h("seekforward", () => $("fwd15").onclick());
    h("nexttrack", () => { const n = neighbor(1); if (n) openPost(n.id, true); });
    h("previoustrack", () => $("prev").onclick());
    h("seekto", (d) => { if (d.seekTime != null) audio.currentTime = d.seekTime; });
  }

  // ---- boot
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("./sw.js").catch(() => {});
  loadIndex().then(() => { const id = location.hash.slice(1); if (id) openPost(id); });
  window.addEventListener("pagehide", savePos);
})();
```

- [ ] **Step 4: 로컬 확인** — `cd site && python3 -m http.server 8000`, Chrome 모바일 에뮬레이션으로 목록·재생·캡션 하이라이트·글씨 크기·이어듣기 확인. 임시 index.json/posts 넣었으면 삭제.
- [ ] **Step 5: Commit** — `git commit -m "feat(site): list, player, synced captions"`

---

### Task 7: PWA — manifest, service worker, 아이콘

**Files:**
- Create: `site/manifest.webmanifest`, `site/sw.js`, `site/icon.svg`

- [ ] **Step 1: 파일 작성**

```json
{
  "name": "메르의 블로그",
  "short_name": "메르",
  "start_url": "./",
  "scope": "./",
  "display": "standalone",
  "background_color": "#1f2937",
  "theme_color": "#1f2937",
  "lang": "ko",
  "icons": [{ "src": "./icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any" }]
}
```

```javascript
// sw.js
const SHELL = "shell-v1";
const DATA = "data-v1";
const SHELL_FILES = ["./", "./index.html", "./app.js", "./style.css", "./manifest.webmanifest", "./icon.svg"];
self.addEventListener("install", (e) => { e.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)).then(() => self.skipWaiting())); });
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => ![SHELL, DATA].includes(k)).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.endsWith(".mp3")) return; // stream directly, never cache
  if (url.pathname.endsWith(".json")) {
    e.respondWith(fetch(e.request).then((r) => { const copy = r.clone(); caches.open(DATA).then((c) => c.put(e.request, copy)); return r; })
      .catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then((c) => c || fetch(e.request)));
});
```

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="96" fill="#1f2937"/>
  <text x="256" y="330" font-family="sans-serif" font-size="220" font-weight="700" fill="#fbbf24" text-anchor="middle">메르</text>
</svg>
```

- [ ] **Step 2: 확인** — Chrome DevTools Application 탭에서 manifest 인식, SW 등록 확인.
- [ ] **Step 3: Commit** — `git commit -m "feat(site): pwa manifest and service worker"`

---

### Task 8: GitHub Actions 워크플로 + README

**Files:**
- Create: `.github/workflows/daily.yml`, `README.md`

- [ ] **Step 1: 워크플로**

```yaml
name: daily
on:
  schedule:
    - cron: "0 22 * * *"   # 07:00 KST
    - cron: "0 4 * * *"    # 13:00 KST
  workflow_dispatch:
    inputs:
      limit:
        description: "max posts this run (blank = all pending)"
        required: false
        default: ""
permissions:
  contents: write
  pages: write
  id-token: write
concurrency:
  group: daily
  cancel-in-progress: false
jobs:
  build-deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deploy.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt
      - name: Run pipeline
        id: run
        continue-on-error: true
        env:
          GOOGLE_TTS_API_KEY: ${{ secrets.GOOGLE_TTS_API_KEY }}
          SITE_BASE_URL: https://${{ github.repository_owner }}.github.io/${{ github.event.repository.name }}
        run: |
          ARGS=""
          if [ -n "${{ github.event.inputs.limit }}" ]; then ARGS="--limit ${{ github.event.inputs.limit }}"; fi
          python -m pipeline.run $ARGS
      - name: Commit site changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add site
          if git diff --cached --quiet; then echo "no changes"; else
            git commit -m "chore: update audio posts $(date -u +%Y-%m-%dT%H:%MZ)"
            git push
          fi
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site
      - id: deploy
        uses: actions/deploy-pages@v4
      - name: Fail if pipeline had errors
        if: steps.run.outcome == 'failure'
        run: exit 1
```

- [ ] **Step 2: README** — 목적, 로컬 실행(`.venv`, `GOOGLE_TTS_API_KEY=... .venv/bin/python -m pipeline.run --limit 1`), 테스트(`.venv/bin/pytest`), 배포 설정 절차(스펙의 "사용자가 해야 할 일" 6단계), 음성 변경(`TTS_VOICE` env).
- [ ] **Step 3: 로컬 문법 확인** — `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/daily.yml'))"` (yaml 없으면 `.venv/bin/pip install pyyaml`).
- [ ] **Step 4: Commit** — `git commit -m "ci: daily pipeline and pages deploy"`

---

### Task 9: 실제 TTS 1건 검증 (API key 확보 후 — 사용자 단계)

- [ ] `GOOGLE_TTS_API_KEY=... .venv/bin/python -m pipeline.run --limit 1` → `site/posts/<id>.mp3|json` 생성, 로그에 timepoint 경고 없는지 확인
- [ ] `cd site && python3 -m http.server 8000` → 캡션 싱크 육안 확인
- [ ] 문제 없으면 생성물 커밋 여부 결정 (Actions가 백필하면 로컬 생성물은 불필요 — 삭제 권장)
