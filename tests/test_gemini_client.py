from unittest.mock import MagicMock

from app.gemini_client import GeminiClient, MovieVerification, VideoIdentification


def _make_client(monkeypatch):
    mock_genai_client = MagicMock()
    monkeypatch.setattr(
        "app.gemini_client.genai.Client", MagicMock(return_value=mock_genai_client)
    )
    return GeminiClient(), mock_genai_client


def test_identify_movie_returns_parsed_response_and_lists_files(monkeypatch):
    client, mock_genai_client = _make_client(monkeypatch)
    expected = VideoIdentification(
        video_file="movie.mkv",
        movie_title="Ice Age",
        language="English",
        year=2002,
        confidence=0.9,
    )
    mock_genai_client.models.generate_content.return_value = MagicMock(parsed=expected)

    result = client.identify_movie(["movie.mkv", "sample.mkv"])

    assert result is expected
    _, kwargs = mock_genai_client.models.generate_content.call_args
    assert "movie.mkv" in kwargs["contents"]
    assert "sample.mkv" in kwargs["contents"]
    assert kwargs["config"].response_schema is VideoIdentification


def test_verify_movie_chains_grounded_search_then_structured_extract(monkeypatch):
    client, mock_genai_client = _make_client(monkeypatch)
    search_response = MagicMock(text="Ice Age (2002) is a real animated film.")
    expected = MovieVerification(
        exists=True, canonical_title="Ice Age", year=2002, confidence=0.95, note=None
    )
    extract_response = MagicMock(parsed=expected)
    mock_genai_client.models.generate_content.side_effect = [search_response, extract_response]

    result = client.verify_movie("Ice Age", 2002, "English")

    assert result is expected
    assert mock_genai_client.models.generate_content.call_count == 2

    search_kwargs = mock_genai_client.models.generate_content.call_args_list[0].kwargs
    assert "Ice Age" in search_kwargs["contents"]
    assert "English" in search_kwargs["contents"]
    assert search_kwargs["config"].tools

    extract_kwargs = mock_genai_client.models.generate_content.call_args_list[1].kwargs
    assert "Ice Age (2002) is a real animated film." in extract_kwargs["contents"]
    assert extract_kwargs["config"].response_schema is MovieVerification


def test_verify_movie_handles_unknown_year(monkeypatch):
    client, mock_genai_client = _make_client(monkeypatch)
    mock_genai_client.models.generate_content.side_effect = [
        MagicMock(text="no strong match found"),
        MagicMock(parsed=MovieVerification(exists=False, canonical_title=None, year=None, confidence=0.1, note="not found")),
    ]

    result = client.verify_movie("Some Obscure Title", None, "English")

    assert result.exists is False
    search_kwargs = mock_genai_client.models.generate_content.call_args_list[0].kwargs
    assert "unknown" in search_kwargs["contents"]
