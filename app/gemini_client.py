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


_PROMPT_TEMPLATE = """You are helping organize a home media library. Below is a
list of files found together (from a torrent download). Identify which single
file is the actual movie video file (ignore samples, extras, subtitles,
.nfo/.txt files, etc), and figure out the real movie title and release year
from the filename, stripping out release-group tags, resolution, codec,
source (bluray/webrip), language tags, and other clutter.

Also determine what language the movie title itself is written in (respond
with the language name in English, e.g. "English", "French", "Japanese").
Keep movie_title in that same original language — do not translate it.

Files:
{files}

Respond with the video file's relative path exactly as listed, the clean
human-readable movie title in its original language, the language it is
written in, the release year if you can determine it, and a confidence score
between 0 and 1. If no file looks like a movie, set video_file to null.
"""

_VERIFY_SEARCH_PROMPT = """Search the web to confirm whether a real, released
movie matching this candidate title/year actually exists. The candidate
title is written in {language} — look it up and report its official title
in {language} specifically. Do not translate the title into English unless
{language} is English.

Candidate title: {title}
Candidate year: {year}
Candidate title language: {language}

Report what you find: does a matching movie exist, what is its correct
official title in {language}, and what year was it actually released?
"""

_VERIFY_EXTRACT_PROMPT = """Based on the following research notes, extract a
structured verification result for the movie.

Research notes:
{notes}
"""


class GeminiClient:
    def __init__(self):
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def identify_movie(self, file_list: list) -> VideoIdentification:
        prompt = _PROMPT_TEMPLATE.format(files="\n".join(f"- {f}" for f in file_list))
        response = self._client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VideoIdentification,
            ),
        )
        return response.parsed

    def verify_movie(self, title: str, year: int | None, language: str) -> MovieVerification:
        # Google Search grounding can't be combined with response_schema in a
        # single call, so this is a two-step chain: a grounded search for
        # free-text research notes, then a plain structured-output call to
        # extract a typed result from those notes.
        search_prompt = _VERIFY_SEARCH_PROMPT.format(
            title=title, year=year or "unknown", language=language
        )
        search_response = self._client.models.generate_content(
            model=settings.gemini_model,
            contents=search_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )

        extract_response = self._client.models.generate_content(
            model=settings.gemini_model,
            contents=_VERIFY_EXTRACT_PROMPT.format(notes=search_response.text),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MovieVerification,
            ),
        )
        return extract_response.parsed
