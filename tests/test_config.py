from app.config import _parse_extensions, load_settings


def test_parse_extensions_normalizes_dots_and_case():
    assert _parse_extensions("MKV, .mp4 ,avi") == (".mkv", ".mp4", ".avi")


def test_parse_extensions_empty_string_yields_empty_tuple():
    assert _parse_extensions("") == ()


def test_load_settings_reads_env_overrides(monkeypatch):
    monkeypatch.setenv("INPUT_DIR", "/custom/input")
    monkeypatch.setenv("MIN_VERIFICATION_CONFIDENCE", "0.75")
    monkeypatch.delenv("OUTPUT_DIR", raising=False)

    settings = load_settings()

    assert settings.input_dir == "/custom/input"
    assert settings.output_dir == "/data/output"
    assert settings.min_verification_confidence == 0.75


def test_load_settings_defaults(monkeypatch):
    for key in [
        "INPUT_DIR",
        "OUTPUT_DIR",
        "GEMINI_MODEL",
        "POLL_INTERVAL_SECONDS",
        "VIDEO_EXTENSIONS",
        "SUBTITLE_EXTENSIONS",
        "MIN_VERIFICATION_CONFIDENCE",
        "STATE_FILE",
    ]:
        monkeypatch.delenv(key, raising=False)

    settings = load_settings()

    assert settings.input_dir == "/data/input"
    assert settings.output_dir == "/data/output"
    assert settings.gemini_model == "gemini-2.5-flash"
    assert settings.poll_interval_seconds == 60
    assert settings.video_extensions == (".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".flv")
    assert settings.subtitle_extensions == (".srt", ".sub", ".ass", ".ssa", ".vtt", ".idx")
    assert settings.min_verification_confidence == 0.6
    assert settings.state_file == "/data/state/processed.json"
