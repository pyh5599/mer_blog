"""Turn Naver blog post HTML into a list of plain-text sentences."""
from __future__ import annotations
import re

from bs4 import BeautifulSoup


class EmptyPostError(Exception):
    pass


EXCLUDE_CLASSES = ("se-caption", "se-oglink", "se-table", "se-code")
_ZW = re.compile("[​‌‍﻿]")
_URL = re.compile(r"https?://\S+|www\.\S+")
_WS = re.compile(r"\s+")
# sentence end (. ? !) + optional closing quote/bracket + whitespace.
# A period directly after a digit is a list prefix ("1. ...") or a number,
# not a sentence end.
_BOUNDARY = re.compile(r"(?:(?<!\d)\.|[?!])[\"')\]”’]*\s+")


def normalize(text: str) -> str:
    text = _ZW.sub("", text)
    text = _URL.sub("", text)
    return _WS.sub(" ", text).strip()


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


def _paragraph_texts(soup: BeautifulSoup) -> list[str]:
    main = soup.select_one("div.se-main-container")
    if main is not None:
        for cls in EXCLUDE_CLASSES:
            for node in main.select(f".{cls}"):
                node.decompose()
        return [p.get_text(" ", strip=True) for p in main.select("p.se-text-paragraph")]
    legacy = soup.select_one("#postViewArea")
    if legacy is not None:
        return [
            n.get_text(" ", strip=True)
            for n in legacy.find_all(["p", "div"])
            if not n.find(["p", "div"])
        ]
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
