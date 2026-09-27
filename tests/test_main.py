import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from google.genai import errors as genai_errors

from app import main
from app.scanner import ScanItem


def _identification(**overrides):
    defaults = dict(
        video_file="movie.mkv",
        movie_title="Ice Age",
        language="English",
        year=2002,
        confidence=0.9,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _verification(**overrides):
    defaults = dict(exists=True, canonical_title="Ice Age", year=2002, confidence=0.9, note=None)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture(autouse=True)
def _patch_heartbeat_file(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings, "heartbeat_file", str(tmp_path / "heartbeat"))


@pytest.fixture(autouse=True)
def _patch_copy_functions(monkeypatch):
    monkeypatch.setattr(
        main, "copy_and_rename", MagicMock(return_value="/data/output/Ice Age (2002).mkv")
    )
    monkeypatch.setattr(main, "copy_keep_name", MagicMock(return_value="/data/output/original.mkv"))
    monkeypatch.setattr(
        main, "copy_subtitle", MagicMock(return_value="/data/output/Ice Age (2002).srt")
    )


@pytest.fixture(autouse=True)
def _patch_sleep(monkeypatch):
    sleep = MagicMock()
    monkeypatch.setattr(main.time, "sleep", sleep)
    return sleep


def _make_item(tmp_path, files):
    return ScanItem(root_path=str(tmp_path / "Movie.Dir"), is_directory=True, files=files)


def _make_dirs(tmp_path, *names):
    for name in names:
        (tmp_path / name).mkdir()
        (tmp_path / name / "movie.mkv").write_text("x")


@pytest.fixture
def state_store():
    store = MagicMock()
    store.is_processed.return_value = False
    return store


@pytest.fixture
def input_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings, "input_dir", str(tmp_path))
    return tmp_path


def test_run_once_batches_identification_and_verification(input_dir, state_store, _patch_sleep):
    _make_dirs(input_dir, "A.Movie", "B.Movie")
    gemini_client = MagicMock()
    gemini_client.identify_movies.return_value = [
        _identification(),
        _identification(movie_title="Amelie", language="French", year=2001),
    ]
    gemini_client.verify_movies.return_value = [_verification(), _verification(exists=False)]

    assert main.run_once(gemini_client, state_store) is None

    gemini_client.identify_movies.assert_called_once_with([["movie.mkv"], ["movie.mkv"]])
    _patch_sleep.assert_called_once_with(main.PAUSE_BETWEEN_REQUESTS_SECONDS)
    candidates = gemini_client.verify_movies.call_args.args[0]
    assert [(c.title, c.year, c.language) for c in candidates] == [
        ("Ice Age", 2002, "English"),
        ("Amelie", 2001, "French"),
    ]
    main.copy_and_rename.assert_called_once_with(
        os.path.join(str(input_dir), "A.Movie", "movie.mkv"), "Ice Age", 2002
    )
    main.copy_keep_name.assert_called_once_with(os.path.join(str(input_dir), "B.Movie", "movie.mkv"))
    assert state_store.mark_processed.call_count == 2


def test_run_once_skips_processed_and_non_video_items_without_calling_gemini(input_dir):
    _make_dirs(input_dir, "Done.Movie")
    (input_dir / "book.epub").write_text("x")
    gemini_client = MagicMock()
    state_store = MagicMock()
    state_store.is_processed.side_effect = lambda key: key == "Done.Movie"

    assert main.run_once(gemini_client, state_store) is None

    gemini_client.identify_movies.assert_not_called()
    gemini_client.verify_movies.assert_not_called()
    state_store.mark_processed.assert_not_called()


def test_run_once_skips_items_with_no_video_identified(input_dir, state_store):
    _make_dirs(input_dir, "A.Movie", "B.Movie", "C.Movie")
    gemini_client = MagicMock()
    gemini_client.identify_movies.return_value = [
        _identification(video_file=None, movie_title=None),
        None,
        _identification(),
    ]
    gemini_client.verify_movies.return_value = [_verification()]

    main.run_once(gemini_client, state_store)

    assert len(gemini_client.verify_movies.call_args.args[0]) == 1
    main.copy_and_rename.assert_called_once_with(
        os.path.join(str(input_dir), "C.Movie", "movie.mkv"), "Ice Age", 2002
    )
    state_store.mark_processed.assert_called_once_with("C.Movie", "/data/output/Ice Age (2002).mkv")


def test_organize_item_renames_using_canonical_title_when_verified(tmp_path, monkeypatch, state_store):
    monkeypatch.setattr(main.settings, "input_dir", str(tmp_path))
    item = _make_item(tmp_path, ["movie.mkv"])

    main.organize_item(item, _identification(), _verification(canonical_title="Ice Age"), state_store)

    main.copy_and_rename.assert_called_once_with(
        os.path.join(item.root_path, "movie.mkv"), "Ice Age", 2002
    )
    main.copy_keep_name.assert_not_called()
    state_store.mark_processed.assert_called_once_with(
        "Movie.Dir", "/data/output/Ice Age (2002).mkv"
    )


def test_organize_item_keeps_original_name_when_verification_says_nonexistent(tmp_path, state_store):
    item = _make_item(tmp_path, ["movie.mkv"])

    main.organize_item(item, _identification(), _verification(exists=False), state_store)

    main.copy_keep_name.assert_called_once_with(os.path.join(item.root_path, "movie.mkv"))
    main.copy_and_rename.assert_not_called()


def test_organize_item_keeps_original_name_when_confidence_too_low(tmp_path, monkeypatch, state_store):
    monkeypatch.setattr(main.settings, "min_verification_confidence", 0.8)
    item = _make_item(tmp_path, ["movie.mkv"])

    main.organize_item(item, _identification(), _verification(confidence=0.5), state_store)

    main.copy_keep_name.assert_called_once()
    main.copy_and_rename.assert_not_called()


def test_organize_item_keeps_original_name_without_verification(tmp_path, state_store):
    item = _make_item(tmp_path, ["movie.mkv"])

    main.organize_item(item, _identification(), None, state_store)

    main.copy_keep_name.assert_called_once()
    main.copy_and_rename.assert_not_called()
    state_store.mark_processed.assert_called_once()


def test_run_once_keeps_original_names_when_verification_raises(input_dir, state_store):
    _make_dirs(input_dir, "A.Movie", "B.Movie")
    gemini_client = MagicMock()
    gemini_client.identify_movies.return_value = [_identification(), _identification()]
    gemini_client.verify_movies.side_effect = RuntimeError("bad json")

    assert main.run_once(gemini_client, state_store) is None

    assert main.copy_keep_name.call_count == 2
    main.copy_and_rename.assert_not_called()
    assert state_store.mark_processed.call_count == 2


def test_copy_subtitles_skipped_for_standalone_files():
    item = ScanItem(root_path="/input/movie.mkv", is_directory=False, files=["movie.mkv"])

    main._copy_subtitles(item, "movie.mkv", "/output/Movie (2020).mkv")

    main.copy_subtitle.assert_not_called()


def test_copy_subtitles_copies_only_subtitle_extensions(tmp_path):
    root = tmp_path / "Movie.Dir"
    item = ScanItem(
        root_path=str(root),
        is_directory=True,
        files=["movie.mkv", "movie.eng.srt", "readme.txt"],
    )

    main._copy_subtitles(item, "movie.mkv", "/output/Movie (2020).mkv")

    main.copy_subtitle.assert_called_once_with(
        os.path.join(str(root), "movie.eng.srt"), "/output/Movie (2020).mkv"
    )


def test_run_once_continues_after_one_item_fails(input_dir, state_store, monkeypatch):
    _make_dirs(input_dir, "A.Movie", "B.Movie")
    gemini_client = MagicMock()
    gemini_client.identify_movies.return_value = [_identification(), _identification()]
    gemini_client.verify_movies.return_value = [_verification(), _verification()]
    monkeypatch.setattr(main, "copy_and_rename", MagicMock(side_effect=[OSError("disk full"), "/out/x.mkv"]))

    main.run_once(gemini_client, state_store)

    assert main.copy_and_rename.call_count == 2
    state_store.mark_processed.assert_called_once_with("B.Movie", "/out/x.mkv")


def test_run_once_does_not_retry_on_non_transient_identify_error(input_dir, state_store):
    _make_dirs(input_dir, "A.Movie")
    gemini_client = MagicMock()
    gemini_client.identify_movies.side_effect = RuntimeError("boom")

    assert main.run_once(gemini_client, state_store) is None

    gemini_client.verify_movies.assert_not_called()
    state_store.mark_processed.assert_not_called()


def _quota_error():
    return genai_errors.ClientError(
        429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}
    )


def test_run_once_does_not_fall_back_when_verification_hits_quota(input_dir, state_store):
    _make_dirs(input_dir, "A.Movie")
    gemini_client = MagicMock()
    gemini_client.identify_movies.return_value = [_identification()]
    gemini_client.verify_movies.side_effect = _quota_error()

    error = main.run_once(gemini_client, state_store)

    assert error.code == 429
    main.copy_keep_name.assert_not_called()
    state_store.mark_processed.assert_not_called()


def test_run_once_stops_scan_on_transient_gemini_error(input_dir, state_store):
    (input_dir / "a.mkv").write_text("")
    (input_dir / "b.mkv").write_text("")
    gemini_client = MagicMock()
    gemini_client.identify_movies.side_effect = genai_errors.ServerError(
        503, {"error": {"code": 503, "message": "busy", "status": "UNAVAILABLE"}}
    )

    error = main.run_once(gemini_client, state_store)

    assert error.code == 503
    assert gemini_client.identify_movies.call_count == 1
    gemini_client.verify_movies.assert_not_called()
    state_store.mark_processed.assert_not_called()


def test_retry_delay_read_from_quota_error():
    exc = genai_errors.ClientError(
        429,
        {
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "37s"}
                ],
            }
        },
    )
    assert main._retry_delay_seconds(exc) == 38


def test_retry_delay_missing():
    assert main._retry_delay_seconds(_quota_error()) is None
