"""Google Cloud Text-to-Speech with per-sentence timepoints."""
from __future__ import annotations

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
    """Group sentence indices so each chunk's SSML stays under max_bytes."""
    max_bytes = max_bytes or config.MAX_SSML_BYTES
    wrap = len("<speak></speak>".encode())
    chunks: list[list[int]] = []
    cur: list[int] = []
    cur_bytes = wrap
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
    """Fallback: distribute total duration proportionally to sentence length."""
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
        if not r.ok:
            raise RuntimeError(f"tts http {r.status_code}: {r.text[:300]}")
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
        audio, timepoints = _request(build_ssml(sentences, indices), api_key, voice)
        dur = mp3_duration(audio)
        by_mark = {tp["markName"]: float(tp["timeSeconds"]) for tp in timepoints}
        if all(f"s{i}" in by_mark for i in indices):
            starts.extend(round(offset + by_mark[f"s{i}"], 3) for i in indices)
        else:
            fallback = True
            starts.extend(round(offset + s, 3) for s in estimate_starts([sentences[i] for i in indices], dur))
        parts.append(audio)
        offset += dur
    if fallback:
        log.warning("timepoints missing for some chunks; used length-based estimate")
    return SynthResult(mp3=b"".join(parts), starts=starts, duration=round(offset, 3))
