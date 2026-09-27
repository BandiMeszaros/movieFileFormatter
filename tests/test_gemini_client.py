import json
from unittest.mock import MagicMock

from app.gemini_client import (
    GeminiClient,
    MovieCandidate,
    _IdentificationBatch,
    _IdentifiedItem,
)


def _make_client(monkeypatch):
    mock_genai_client = MagicMock()
    monkeypatch.setattr(
        "app.gemini_client.genai.Client", MagicMock(return_value=mock_genai_client)
    )
    return GeminiClient(), mock_genai_client


def _identified(item_id, **overrides):
    fields = dict(
        item_id=item_id,
        video_file="movie.mkv",
        movie_title="Ice Age",
        language="English",
        year=2002,
        confidence=0.9,
    )
    fields.update(overrides)
    return _IdentifiedItem(**fields)


def test_identify_movies_sends_all_items_in_one_request(monkeypatch):
    client, mock_genai_client = _make_client(monkeypatch)
    batch = _IdentificationBatch(
        results=[
            _identified(1, video_file="amelie.mkv", movie_title="Le Fabuleux Destin d'Amélie Poulain"),
            _identified(0),
        ]
    )
    mock_genai_client.models.generate_content.return_value = MagicMock(parsed=batch)

    results = client.identify_movies([["movie.mkv", "sample.mkv"], ["amelie.mkv"]])

    assert mock_genai_client.models.generate_content.call_count == 1
    assert results[0].movie_title == "Ice Age"
    assert results[1].video_file == "amelie.mkv"
    _, kwargs = mock_genai_client.models.generate_content.call_args
    for name in ("movie.mkv", "sample.mkv", "amelie.mkv", "Item 0", "Item 1"):
        assert name in kwargs["contents"]
    assert kwargs["config"].response_schema is _IdentificationBatch


def test_identify_movies_returns_none_for_missing_results(monkeypatch):
    client, mock_genai_client = _make_client(monkeypatch)
    mock_genai_client.models.generate_content.return_value = MagicMock(
        parsed=_IdentificationBatch(results=[_identified(0)])
    )

    results = client.identify_movies([["a.mkv"], ["b.mkv"]])

    assert results[0] is not None
    assert results[1] is None


def test_identify_movies_skips_request_when_empty(monkeypatch):
    client, mock_genai_client = _make_client(monkeypatch)

    assert client.identify_movies([]) == []
    mock_genai_client.models.generate_content.assert_not_called()


def _verification_json(*results):
    return json.dumps({"results": list(results)})


def test_verify_movies_sends_all_candidates_in_one_grounded_request(monkeypatch):
    client, mock_genai_client = _make_client(monkeypatch)
    text = "```json\n" + _verification_json(
        {"candidate_id": 1, "exists": False, "canonical_title": None, "year": None, "confidence": 0.1, "note": "not found"},
        {"candidate_id": 0, "exists": True, "canonical_title": "Ice Age", "year": 2002, "confidence": 0.95, "note": None},
    ) + "\n```"
    mock_genai_client.models.generate_content.return_value = MagicMock(text=text)

    results = client.verify_movies(
        [
            MovieCandidate(title="Ice Age", year=2002, language="English"),
            MovieCandidate(title="Some Obscure Title", year=None, language="French"),
        ]
    )

    assert mock_genai_client.models.generate_content.call_count == 1
    assert results[0].exists is True and results[0].canonical_title == "Ice Age"
    assert results[1].exists is False
    _, kwargs = mock_genai_client.models.generate_content.call_args
    for fragment in ("Ice Age", "2002", "Some Obscure Title", "unknown", "French", "English"):
        assert fragment in kwargs["contents"]
    assert kwargs["config"].tools


def test_verify_movies_returns_none_for_missing_results(monkeypatch):
    client, mock_genai_client = _make_client(monkeypatch)
    mock_genai_client.models.generate_content.return_value = MagicMock(
        text=_verification_json(
            {"candidate_id": 0, "exists": True, "canonical_title": "Ice Age", "year": 2002, "confidence": 0.9, "note": None}
        )
    )

    results = client.verify_movies(
        [MovieCandidate(title="Ice Age", year=2002, language="English"),
         MovieCandidate(title="Other", year=None, language="English")]
    )

    assert results[1] is None


def test_verify_movies_skips_request_when_empty(monkeypatch):
    client, mock_genai_client = _make_client(monkeypatch)

    assert client.verify_movies([]) == []
    mock_genai_client.models.generate_content.assert_not_called()
