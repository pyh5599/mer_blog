import re
from unittest.mock import patch

from pipeline import tts


def test_chunk_respects_byte_limit_and_keeps_order():
    sents = ["가" * 100] * 30  # ~300 bytes each in utf-8
    chunks = tts.chunk_sentences(sents, max_bytes=1000)
    assert [i for c in chunks for i in c] == list(range(30))
    for c in chunks:
        assert len(tts.build_ssml(sents, c).encode("utf-8")) <= 1000


def test_oversized_single_sentence_gets_own_chunk():
    sents = ["가" * 2000, "짧음"]
    assert tts.chunk_sentences(sents, max_bytes=1000) == [[0], [1]]


def test_build_ssml_escapes_and_marks():
    ssml = tts.build_ssml(["A & B <c>", "둘"], [0, 1])
    assert '<mark name="s0"/>' in ssml and '<mark name="s1"/>' in ssml
    assert "&amp;" in ssml and "&lt;c&gt;" in ssml
    assert ssml.startswith("<speak>") and ssml.endswith("</speak>")


def test_estimate_starts_proportional():
    assert tts.estimate_starts(["가" * 10, "가" * 30], total=8.0) == [0.0, 2.0]


def test_synthesize_accumulates_offsets():
    sents = ["가" * 100] * 6
    calls = []

    def fake_request(ssml, api_key, voice):
        calls.append(ssml)
        marks = re.findall(r'<mark name="(s\d+)"/>', ssml)
        return b"MP3" + bytes([len(calls)]), [{"markName": m, "timeSeconds": k * 1.0} for k, m in enumerate(marks)]

    with patch.object(tts, "_request", side_effect=fake_request), patch.object(
        tts, "mp3_duration", return_value=10.0
    ), patch.object(tts.config, "MAX_SSML_BYTES", 1200):
        res = tts.synthesize(sents, api_key="k", voice="ko-KR-Neural2-A")
    assert len(calls) == 2
    assert res.starts == [0.0, 1.0, 2.0, 10.0, 11.0, 12.0]
    assert res.duration == 20.0
    assert res.mp3 == b"MP3\x01MP3\x02"


def test_synthesize_falls_back_when_no_timepoints():
    sents = ["가" * 10, "가" * 30]
    with patch.object(tts, "_request", return_value=(b"X", [])), patch.object(
        tts, "mp3_duration", return_value=8.0
    ):
        res = tts.synthesize(sents, api_key="k", voice="ko-KR-Neural2-A")
    assert res.starts == [0.0, 2.0]


def test_spoken_text_drops_list_prefix_only():
    assert tts.spoken_text("12. 금리가 올랐음.") == "금리가 올랐음."
    assert tts.spoken_text("2026년 8월초 기사.") == "2026년 8월초 기사."
    assert tts.spoken_text("3.") == "3."
    assert '<mark name="s0"/>금리' in tts.build_ssml(["1. 금리"], [0])


def test_per_sentence_mode_for_chirp_uses_measured_clip_lengths():
    sents = ["1. 하나.", "둘.", "셋."]
    seen = []

    def fake_request(ssml, api_key, voice):
        seen.append(ssml)
        return ssml.encode(), []

    durations = iter([2.0, 3.5, 1.0])
    with patch.object(tts, "_request", side_effect=fake_request), patch.object(
        tts, "mp3_duration", side_effect=lambda b: next(durations)
    ):
        res = tts.synthesize(sents, api_key="k", voice="ko-KR-Chirp3-HD-Kore")
    assert res.starts == [0.0, 2.0, 5.5]
    assert res.duration == 6.5
    assert len(seen) == 3 and "하나." in seen[0] and "1." not in seen[0]
    assert res.mp3 == b"".join(s.encode() for s in seen)


def test_neural2_keeps_chunked_mark_mode():
    assert tts.supports_timepoints("ko-KR-Neural2-A")
    assert not tts.supports_timepoints("ko-KR-Chirp3-HD-Kore")
