import logging
import os
import time

from .config import settings
from .gemini_client import GeminiClient, MovieVerification
from .organizer import copy_and_rename, copy_keep_name, copy_subtitle
from .scanner import ScanItem, scan_input_dir
from .state import ProcessedStateStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("movie_file_formatter")


def _verify(gemini_client: GeminiClient, title: str, year, language: str) -> MovieVerification | None:
    try:
        return gemini_client.verify_movie(title, year, language)
    except Exception:
        logger.exception("Verification lookup failed for '%s' (%s)", title, year)
        return None


def _copy_subtitles(item: ScanItem, video_file: str, video_target_path: str) -> None:
    if not item.is_directory:
        return
    for rel_path in item.files:
        if rel_path == video_file:
            continue
        if os.path.splitext(rel_path)[1].lower() not in settings.subtitle_extensions:
            continue
        source_path = os.path.join(item.root_path, rel_path)
        target = copy_subtitle(source_path, video_target_path)
        logger.info("Copied subtitle %s -> %s", source_path, target)


def process_item(item: ScanItem, gemini_client: GeminiClient, state_store: ProcessedStateStore) -> None:
    key = os.path.relpath(item.root_path, settings.input_dir)
    if state_store.is_processed(key):
        return

    identification = gemini_client.identify_movie(item.files)
    if not identification.video_file or not identification.movie_title:
        logger.info("No video identified in %s, skipping", item.root_path)
        return

    video_path = (
        item.root_path
        if not item.is_directory
        else os.path.join(item.root_path, identification.video_file)
    )
    language = identification.language or "English"

    verification = _verify(gemini_client, identification.movie_title, identification.year, language)
    verified = (
        verification is not None
        and verification.exists
        and verification.confidence >= settings.min_verification_confidence
    )

    if verified:
        final_title = verification.canonical_title or identification.movie_title
        final_year = verification.year or identification.year
        target = copy_and_rename(video_path, final_title, final_year)
    else:
        logger.warning(
            "Could not verify '%s' (%s) as a real movie, keeping original filename for %s",
            identification.movie_title,
            identification.year,
            video_path,
        )
        target = copy_keep_name(video_path)

    logger.info("Copied %s -> %s", video_path, target)
    _copy_subtitles(item, identification.video_file, target)
    state_store.mark_processed(key, target)


def touch_heartbeat() -> None:
    """Marks the loop as alive for app.healthcheck. Failure here must never
    stop processing, the healthcheck will just report unhealthy."""
    try:
        with open(settings.heartbeat_file, "a"):
            pass
        os.utime(settings.heartbeat_file, None)
    except OSError:
        logger.exception("Failed to update heartbeat file %s", settings.heartbeat_file)


def run_once(gemini_client: GeminiClient, state_store: ProcessedStateStore) -> None:
    items = scan_input_dir(settings.input_dir)
    logger.info("Found %d item(s) in %s", len(items), settings.input_dir)
    for item in items:
        try:
            process_item(item, gemini_client, state_store)
        except Exception:
            logger.exception("Failed to process %s", item.root_path)
        touch_heartbeat()


def main() -> None:
    gemini_client = GeminiClient()
    state_store = ProcessedStateStore(settings.state_file)
    while True:
        touch_heartbeat()
        run_once(gemini_client, state_store)
        time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
