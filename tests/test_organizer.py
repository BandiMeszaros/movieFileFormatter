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


def test_build_target_filename_keeps_episode_tag():
    assert (
        organizer.build_target_filename("Breaking Bad", 2008, ".mkv", "S01E01")
        == "Breaking Bad (2008) S01E01.mkv"
    )


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("Breaking.Bad.S01E01.720p.BluRay.x264.mkv", "S01E01"),
        ("show.s1e2.mkv", "S01E02"),
        ("Show - S02 E05.mkv", "S02E05"),
        ("Show.S01.E03.mkv", "S01E03"),
        ("Show.S03E01E02.mkv", "S03E01E02"),
        ("Show.S03E01-E02.mkv", "S03E01E02"),
        ("Show.1x03.HDTV.mkv", "S01E03"),
        ("Season 1/Show.S01E04.mkv", "S01E04"),
        ("Ice.Age.2002.1080p.x264.mkv", None),
        ("Movie.1920x1080.mkv", None),
    ],
)
def test_extract_episode_tag(filename, expected):
    assert organizer.extract_episode_tag(filename) == expected


def test_copy_and_rename_keeps_episode_tag(tmp_path, _output_dir):
    source = tmp_path / "Breaking.Bad.S02E03.720p.mkv"
    source.write_text("video-bytes")

    target = organizer.copy_and_rename(str(source), "Breaking Bad", 2008)

    assert target == str(_output_dir / "Breaking Bad (2008) S02E03.mkv")


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


def test_copy_and_rename_does_not_duplicate_an_existing_copy(tmp_path, _output_dir):
    source = tmp_path / "Ice.Age.mkv"
    source.write_text("video-bytes")

    first = organizer.copy_and_rename(str(source), "Ice Age", 2002)
    second = organizer.copy_and_rename(str(source), "Ice Age", 2002)

    assert second == first
    assert sorted(os.listdir(_output_dir)) == ["Ice Age (2002).mkv"]


def test_copy_and_rename_finds_existing_copy_under_numbered_name(tmp_path, _output_dir):
    _output_dir.mkdir(parents=True)
    (_output_dir / "Ice Age (2002).mkv").write_text("a different movie")
    source = tmp_path / "Ice.Age.mkv"
    source.write_text("new")

    first = organizer.copy_and_rename(str(source), "Ice Age", 2002)
    second = organizer.copy_and_rename(str(source), "Ice Age", 2002)

    assert first == second == str(_output_dir / "Ice Age (2002) (2).mkv")
    assert len(os.listdir(_output_dir)) == 2


def test_copy_keep_name_does_not_duplicate_an_existing_copy(tmp_path, _output_dir):
    source = tmp_path / "weird_release_name_XYZ.mkv"
    source.write_text("video-bytes")

    organizer.copy_keep_name(str(source))
    organizer.copy_keep_name(str(source))

    assert os.listdir(_output_dir) == ["weird_release_name_XYZ.mkv"]


def test_copy_subtitle_does_not_duplicate_an_existing_copy(tmp_path, _output_dir):
    video_target = _output_dir / "Ice Age (2002).mkv"
    english = tmp_path / "Ice.Age.eng.srt"
    english.write_text("english subs")
    french = tmp_path / "Ice.Age.fre.srt"
    french.write_text("french subs")

    for _ in range(2):
        organizer.copy_subtitle(str(english), str(video_target))
        organizer.copy_subtitle(str(french), str(video_target))

    assert sorted(os.listdir(_output_dir)) == ["Ice Age (2002) (Ice.Age.fre).srt", "Ice Age (2002).srt"]
