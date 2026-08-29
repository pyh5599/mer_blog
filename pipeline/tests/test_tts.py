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
        n = ssml.count("<mark")
        return b"MP3" + bytes([len(calls)]), [{"markName": f"s{i}", "timeSeconds": i * 1.0} for i in range(n)]

    with patch.object(tts, "_request", side_effect=fake_request), patch.object(
        tts, "mp3_duration", return_value=10.0
    ), patch.object(tts.config, "MAX_SSML_BYTES", 1200):
        res = tts.synthesize(sents, api_key="k")
    assert len(calls) == 2
    assert res.starts == [0.0, 1.0, 2.0, 10.0, 11.0, 12.0]
    assert res.duration == 20.0
    assert res.mp3 == b"MP3\x01MP3\x02"


def test_synthesize_falls_back_when_no_timepoints():
    sents = ["가" * 10, "가" * 30]
    with patch.object(tts, "_request", return_value=(b"X", [])), patch.object(
        tts, "mp3_duration", return_value=8.0
    ):
        res = tts.synthesize(sents, api_key="k")
    assert res.starts == [0.0, 2.0]
