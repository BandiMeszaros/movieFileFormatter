import os
from dataclasses import dataclass


def _parse_extensions(raw: str) -> tuple:
    return tuple(f".{ext.strip().lstrip('.').lower()}" for ext in raw.split(",") if ext.strip())


@dataclass
class Settings:
    input_dir: str
    output_dir: str
    gemini_api_key: str
    gemini_model: str
    poll_interval_seconds: int
    video_extensions: tuple
    subtitle_extensions: tuple
    min_verification_confidence: float
    state_file: str
    heartbeat_file: str
    heartbeat_max_age_seconds: int


def load_settings() -> Settings:
    return Settings(
        input_dir=os.environ.get("DOWNLOAD_DIR", "/data/input"),
        output_dir=os.environ.get("MOVIE_OUTPUT", "/data/output"),
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
        poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "60")),
        video_extensions=_parse_extensions(
            os.environ.get("VIDEO_EXTENSIONS", "mkv,mp4,avi,mov,m4v,wmv,flv")
        ),
        subtitle_extensions=_parse_extensions(
            os.environ.get("SUBTITLE_EXTENSIONS", "srt,sub,ass,ssa,vtt,idx")
        ),
        min_verification_confidence=float(
            os.environ.get("MIN_VERIFICATION_CONFIDENCE", "0.6")
        ),
        state_file=os.path.join(
            os.environ.get("STATE_DIR", "/data/state"), "processed.json"
        ),
        heartbeat_file=os.environ.get("HEARTBEAT_FILE", "/tmp/movie-file-formatter.heartbeat"),
        heartbeat_max_age_seconds=int(os.environ.get("HEARTBEAT_MAX_AGE_SECONDS", "1800")),
    )


settings = load_settings()
