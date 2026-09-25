import os

import pytest

from app import organizer


@pytest.fixture(autouse=True)
def _output_dir(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    monkeypatch.setattr(organizer.settings, "output_dir", str(output_dir))
    return output_dir


def test_sanitize_filename_strips_illegal_chars():
    assert organizer.sanitize_filename('Movie: Title?/\\*<>|"') == "Movie Title"


def test_build_target_filename_with_year():
    assert organizer.build_target_filename("Ice Age", 2002, ".mkv") == "Ice Age (2002).mkv"


def test_build_target_filename_without_year():
    assert organizer.build_target_filename("Ice Age", None, ".mkv") == "Ice Age.mkv"


def test_copy_and_rename_copies_without_touching_original(tmp_path, _output_dir):
    source = tmp_path / "Ice.Age.Bluray.1080p.mkv"
    source.write_text("video-bytes")

    target = organizer.copy_and_rename(str(source), "Ice Age", 2002)

    assert target == str(_output_dir / "Ice Age (2002).mkv")
    assert os.path.exists(target)
    assert source.exists()
    assert source.read_text() == "video-bytes"


def test_copy_and_rename_avoids_collision(tmp_path, _output_dir):
    _output_dir.mkdir(parents=True)
    (_output_dir / "Ice Age (2002).mkv").write_text("existing")

    source = tmp_path / "Ice.Age.mkv"
    source.write_text("new")

    target = organizer.copy_and_rename(str(source), "Ice Age", 2002)

    assert target == str(_output_dir / "Ice Age (2002) (2).mkv")


def test_copy_keep_name_preserves_original_filename(tmp_path, _output_dir):
    source = tmp_path / "weird_release_name_XYZ.mkv"
    source.write_text("video-bytes")

    target = organizer.copy_keep_name(str(source))

    assert os.path.basename(target) == "weird_release_name_XYZ.mkv"
    assert source.exists()


def test_copy_subtitle_matches_video_base_name(tmp_path, _output_dir):
    video_target = _output_dir / "Ice Age (2002).mkv"
    subtitle = tmp_path / "Ice.Age.eng.srt"
    subtitle.write_text("subtitle-bytes")

    target = organizer.copy_subtitle(str(subtitle), str(video_target))

    assert target == str(_output_dir / "Ice Age (2002).srt")
    assert subtitle.exists()


def test_copy_subtitle_disambiguates_on_collision(tmp_path, _output_dir):
    _output_dir.mkdir(parents=True)
    video_target = _output_dir / "Ice Age (2002).mkv"
    (_output_dir / "Ice Age (2002).srt").write_text("english subs")

    subtitle = tmp_path / "Ice.Age.fre.srt"
    subtitle.write_text("french subs")

    target = organizer.copy_subtitle(str(subtitle), str(video_target))

    assert target == str(_output_dir / "Ice Age (2002) (Ice.Age.fre).srt")
