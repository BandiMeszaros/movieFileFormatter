import os

from app.scanner import scan_input_dir


def test_scan_input_dir_lists_standalone_files_and_directories(tmp_path):
    (tmp_path / "Standalone.Movie.mkv").write_text("x")

    movie_dir = tmp_path / "Some.Movie.2020.GROUP"
    movie_dir.mkdir()
    (movie_dir / "movie.mkv").write_text("x")
    (movie_dir / "movie.eng.srt").write_text("x")
    (movie_dir / "sample").mkdir()
    (movie_dir / "sample" / "sample.mkv").write_text("x")

    items = scan_input_dir(str(tmp_path))
    by_name = {os.path.basename(item.root_path): item for item in items}

    assert set(by_name) == {"Standalone.Movie.mkv", "Some.Movie.2020.GROUP"}

    standalone = by_name["Standalone.Movie.mkv"]
    assert standalone.is_directory is False
    assert standalone.files == ["Standalone.Movie.mkv"]

    directory_item = by_name["Some.Movie.2020.GROUP"]
    assert directory_item.is_directory is True
    assert set(directory_item.files) == {
        "movie.mkv",
        "movie.eng.srt",
        os.path.join("sample", "sample.mkv"),
    }


def test_scan_input_dir_empty(tmp_path):
    assert scan_input_dir(str(tmp_path)) == []
