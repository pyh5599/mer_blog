from pathlib import Path

import pytest

from pipeline.clean import EmptyPostError, extract_sentences, split_sentences

FIX = Path(__file__).parent / "fixtures"
HTML = (FIX / "post_224394691017.html").read_text(encoding="utf-8")
TITLE = "중국이 외국인을 들여다 보는 법"


def test_extract_real_post():
    s = extract_sentences(HTML, title=TITLE)
    assert s[0] == "주말이라 일반적인 시사 내용입니다."
    assert s[1].startswith("1. 2026년 8월초")
    assert all("​" not in x for x in s)
    assert all(x.strip() == x and x for x in s)
    assert 40 <= len(s) <= 80


def test_title_line_removed():
    assert TITLE not in extract_sentences(HTML, title=TITLE)


def test_captions_and_oglinks_excluded():
    html = """<div class="se-main-container">
      <p class="se-text-paragraph"><span>본문 문장임.</span></p>
      <div class="se-caption"><p class="se-text-paragraph"><span>캡션 제외</span></p></div>
      <div class="se-oglink"><p class="se-text-paragraph"><span>링크 제외</span></p></div>
      <div class="se-table"><p class="se-text-paragraph"><span>표 제외</span></p></div>
    </div><div class="se-section-end"></div>"""
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
