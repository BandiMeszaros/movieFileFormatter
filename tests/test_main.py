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


def _make_item(tmp_path, files):
    return ScanItem(root_path=str(tmp_path / "Movie.Dir"), is_directory=True, files=files)


def test_process_item_skips_when_already_processed(tmp_path):
    item = _make_item(tmp_path, ["movie.mkv"])
    gemini_client = MagicMock()
    state_store = MagicMock()
    state_store.is_processed.return_value = True

    main.process_item(item, gemini_client, state_store)

    gemini_client.identify_movie.assert_not_called()
    state_store.mark_processed.assert_not_called()


def test_process_item_skips_when_no_video_identified(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings, "input_dir", str(tmp_path))
    item = _make_item(tmp_path, ["readme.txt"])
    gemini_client = MagicMock()
    gemini_client.identify_movie.return_value = _identification(video_file=None, movie_title=None)
    state_store = MagicMock()
    state_store.is_processed.return_value = False

    main.process_item(item, gemini_client, state_store)

    gemini_client.verify_movie.assert_not_called()
    main.copy_and_rename.assert_not_called()
    main.copy_keep_name.assert_not_called()
    state_store.mark_processed.assert_not_called()


def test_process_item_renames_using_canonical_title_when_verified(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings, "input_dir", str(tmp_path))
    item = _make_item(tmp_path, ["movie.mkv"])
    gemini_client = MagicMock()
    gemini_client.identify_movie.return_value = _identification()
    gemini_client.verify_movie.return_value = _verification()
    state_store = MagicMock()
    state_store.is_processed.return_value = False

    main.process_item(item, gemini_client, state_store)

    main.copy_and_rename.assert_called_once_with(
        os.path.join(item.root_path, "movie.mkv"), "Ice Age", 2002
    )
    main.copy_keep_name.assert_not_called()
    gemini_client.verify_movie.assert_called_once_with("Ice Age", 2002, "English")
    state_store.mark_processed.assert_called_once_with(
        "Movie.Dir", "/data/output/Ice Age (2002).mkv"
    )


def test_process_item_keeps_original_name_when_verification_says_nonexistent(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings, "input_dir", str(tmp_path))
    item = _make_item(tmp_path, ["movie.mkv"])
    gemini_client = MagicMock()
    gemini_client.identify_movie.return_value = _identification()
    gemini_client.verify_movie.return_value = _verification(exists=False)
    state_store = MagicMock()
    state_store.is_processed.return_value = False

    main.process_item(item, gemini_client, state_store)

    main.copy_keep_name.assert_called_once_with(os.path.join(item.root_path, "movie.mkv"))
    main.copy_and_rename.assert_not_called()


def test_process_item_keeps_original_name_when_confidence_too_low(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings, "input_dir", str(tmp_path))
    monkeypatch.setattr(main.settings, "min_verification_confidence", 0.8)
    item = _make_item(tmp_path, ["movie.mkv"])
    gemini_client = MagicMock()
    gemini_client.identify_movie.return_value = _identification()
    gemini_client.verify_movie.return_value = _verification(confidence=0.5)
    state_store = MagicMock()
    state_store.is_processed.return_value = False

    main.process_item(item, gemini_client, state_store)

    main.copy_keep_name.assert_called_once()
    main.copy_and_rename.assert_not_called()


def test_process_item_keeps_original_name_when_verification_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings, "input_dir", str(tmp_path))
    item = _make_item(tmp_path, ["movie.mkv"])
    gemini_client = MagicMock()
    gemini_client.identify_movie.return_value = _identification()
    gemini_client.verify_movie.side_effect = RuntimeError("network down")
    state_store = MagicMock()
    state_store.is_processed.return_value = False

    main.process_item(item, gemini_client, state_store)

    main.copy_keep_name.assert_called_once()
    main.copy_and_rename.assert_not_called()
    state_store.mark_processed.assert_called_once()


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


def test_run_once_continues_after_one_item_fails(tmp_path, monkeypatch):
    good_dir = tmp_path / "Good.Movie"
    good_dir.mkdir()
    (good_dir / "movie.mkv").write_text("x")
    bad_dir = tmp_path / "Bad.Movie"
    bad_dir.mkdir()
    (bad_dir / "movie.mkv").write_text("x")

    monkeypatch.setattr(main.settings, "input_dir", str(tmp_path))

    gemini_client = MagicMock()

    def identify_side_effect(files):
        raise RuntimeError("boom")

    gemini_client.identify_movie.side_effect = identify_side_effect
    state_store = MagicMock()
    state_store.is_processed.return_value = False

    main.run_once(gemini_client, state_store)

    assert gemini_client.identify_movie.call_count == 2


def test_process_item_skips_non_video_items_without_calling_gemini(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings, "input_dir", str(tmp_path))
    item = ScanItem(root_path=str(tmp_path / "book.epub"), is_directory=False, files=["book.epub"])
    gemini_client = MagicMock()
    state_store = MagicMock()
    state_store.is_processed.return_value = False

    main.process_item(item, gemini_client, state_store)

    gemini_client.identify_movie.assert_not_called()
    state_store.mark_processed.assert_not_called()


def _quota_error():
    return genai_errors.ClientError(
        429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}
    )


def test_process_item_does_not_fall_back_when_verification_hits_quota(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings, "input_dir", str(tmp_path))
    item = _make_item(tmp_path, ["movie.mkv"])
    gemini_client = MagicMock()
    gemini_client.identify_movie.return_value = _identification()
    gemini_client.verify_movie.side_effect = _quota_error()
    state_store = MagicMock()
    state_store.is_processed.return_value = False

    with pytest.raises(genai_errors.ClientError):
        main.process_item(item, gemini_client, state_store)

    main.copy_keep_name.assert_not_called()
    state_store.mark_processed.assert_not_called()


def test_run_once_stops_scan_on_transient_gemini_error(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings, "input_dir", str(tmp_path))
    (tmp_path / "a.mkv").write_text("")
    (tmp_path / "b.mkv").write_text("")
    gemini_client = MagicMock()
    gemini_client.identify_movie.side_effect = genai_errors.ServerError(
        503, {"error": {"code": 503, "message": "busy", "status": "UNAVAILABLE"}}
    )
    state_store = MagicMock()
    state_store.is_processed.return_value = False

    main.run_once(gemini_client, state_store)

    assert gemini_client.identify_movie.call_count == 1
    state_store.mark_processed.assert_not_called()
