import json

from google import genai
from google.genai import types
from pydantic import BaseModel

from .config import settings


class VideoIdentification(BaseModel):
    video_file: str | None
    movie_title: str | None
    language: str | None
    year: int | None
    confidence: float


class MovieVerification(BaseModel):
    exists: bool
    canonical_title: str | None
    year: int | None
    confidence: float
    note: str | None


class MovieCandidate(BaseModel):
    title: str
    year: int | None
    language: str


# Batched wrappers: each entry echoes back the id it was given in the prompt
# so results can be matched to their inputs regardless of order or omissions.
class _IdentifiedItem(VideoIdentification):
    item_id: int


class _IdentificationBatch(BaseModel):
    results: list[_IdentifiedItem]


class _VerifiedCandidate(MovieVerification):
    candidate_id: int


class _VerificationBatch(BaseModel):
    results: list[_VerifiedCandidate]


_IDENTIFY_PROMPT = """You are helping organize a home media library. Below are
several items, each with an id and the list of files found together in it
(from a torrent download). Handle every item independently.

For each item, identify which single file is the actual movie video file
(ignore samples, extras, subtitles, .nfo/.txt files, etc), and figure out the
real movie title and release year from the filename, stripping out
release-group tags, resolution, codec, source (bluray/webrip), language tags,
and other clutter.

Also determine what language the movie title itself is written in (respond
with the language name in English, e.g. "English", "French", "Japanese").
Keep movie_title in that same original language — do not translate it.

{items}

Return exactly one result per item, with item_id set to that item's id. For
each, respond with the video file's relative path exactly as listed for that
item, the clean human-readable movie title in its original language, the
language it is written in, the release year if you can determine it, and a
confidence score between 0 and 1. If no file in an item looks like a movie,
set its video_file to null.
"""

_VERIFY_PROMPT = """Search the web to confirm, for each candidate below,
whether a real, released movie matching its title/year actually exists. Each
candidate's title is written in the language given for it — look it up and
report its official title in that language specifically. Do not translate a
title into English unless its language is English. Handle every candidate
independently.

{candidates}

For each candidate report what you find: does a matching movie exist
(exists), its correct official title in the candidate's language
(canonical_title), the year it was actually released (year), your confidence
between 0 and 1 (confidence), and an optional short note (note).

Respond with ONLY a JSON object, no other text, matching this JSON schema,
with exactly one result per candidate and candidate_id set to its id:
{schema}
"""


# We never pass Python functions as tools, so AFC does nothing for us except
# log an "AFC is enabled" line and a Chat.send_message recommendation per call.
_NO_AFC = types.AutomaticFunctionCallingConfig(disable=True)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


class GeminiClient:
    def __init__(self):
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def identify_movies(self, file_lists: list) -> list:
        """Identifies the movie in every item with a single request. Returns a
        list aligned with file_lists; an entry is None if Gemini returned no
        result for that item."""
        if not file_lists:
            return []
        items = "\n\n".join(
            f"Item {i}:\n" + "\n".join(f"- {f}" for f in files)
            for i, files in enumerate(file_lists)
        )
        response = self._client.models.generate_content(
            model=settings.gemini_model,
            contents=_IDENTIFY_PROMPT.format(items=items),
            config=types.GenerateContentConfig(
                automatic_function_calling=_NO_AFC,
                response_mime_type="application/json",
                response_schema=_IdentificationBatch,
            ),
        )
        by_id = {r.item_id: r for r in response.parsed.results}
        return [by_id.get(i) for i in range(len(file_lists))]

    def verify_movies(self, candidates: list) -> list:
        """Verifies every candidate with a single grounded-search request.
        Returns a list aligned with candidates; an entry is None if Gemini
        returned no result for that candidate."""
        if not candidates:
            return []
        listing = "\n".join(
            f"- Candidate {i}: title: {c.title} | year: {c.year or 'unknown'} | language: {c.language}"
            for i, c in enumerate(candidates)
        )
        # Google Search grounding can't be combined with response_schema, so
        # the prompt asks for JSON in plain text and we validate it ourselves.
        response = self._client.models.generate_content(
            model=settings.gemini_model,
            contents=_VERIFY_PROMPT.format(
                candidates=listing,
                schema=json.dumps(_VerificationBatch.model_json_schema()),
            ),
            config=types.GenerateContentConfig(
                automatic_function_calling=_NO_AFC,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        batch = _VerificationBatch.model_validate_json(_strip_code_fence(response.text or ""))
        by_id = {r.candidate_id: r for r in batch.results}
        return [by_id.get(i) for i in range(len(candidates))]
