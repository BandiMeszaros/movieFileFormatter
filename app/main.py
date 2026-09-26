import logging
import os
import time

from google.genai import errors as genai_errors

from .config import settings
from .gemini_client import GeminiClient, MovieVerification
from .organizer import copy_and_rename, copy_keep_name, copy_subtitle
from .scanner import ScanItem, scan_input_dir
from .state import ProcessedStateStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("movie_file_formatter")

INITIAL_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 1800


def _is_transient(exc: Exception) -> bool:
    """Quota exhausted (429) or Gemini overloaded (5xx): worth retrying later,
    not evidence about the movie itself."""
    return isinstance(exc, genai_errors.APIError) and (exc.code == 429 or exc.code >= 500)


def _verify(gemini_client: GeminiClient, title: str, year, language: str) -> MovieVerification | None:
    try:
        return gemini_client.verify_movie(title, year, language)
    except Exception as exc:
        # Don't fall back to the original filename over a temporary outage;
        # let the item stay unprocessed so the next poll retries it.
        if _is_transient(exc):
            raise
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

    # Ebooks, archives etc. aren't movies; skip them without spending a Gemini call.
    if not any(os.path.splitext(f)[1].lower() in settings.video_extensions for f in item.files):
        logger.debug("No video files in %s, skipping", item.root_path)
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


def _retry_delay_seconds(exc: genai_errors.APIError) -> int | None:
    """The retryDelay Gemini sometimes attaches to a 429 (e.g. "37s")."""
    body = exc.details if isinstance(exc.details, dict) else {}
    for detail in body.get("error", {}).get("details", []):
        delay = detail.get("retryDelay") if isinstance(detail, dict) else None
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return int(float(delay[:-1])) + 1
            except ValueError:
                pass
    return None


def run_once(gemini_client: GeminiClient, state_store: ProcessedStateStore) -> genai_errors.APIError | None:
    """Processes every pending item. Returns the transient Gemini error that
    stopped the scan early, if any, so the caller can back off."""
    items = scan_input_dir(settings.input_dir)
    logger.info("Found %d item(s) in %s", len(items), settings.input_dir)
    for item in items:
        try:
            process_item(item, gemini_client, state_store)
        except Exception as exc:
            if _is_transient(exc):
                # The remaining items would hit the same quota/overload, so
                # stop this scan and retry everything on the next poll.
                logger.warning(
                    "Gemini unavailable (%s %s), retrying %s on next poll",
                    exc.code,
                    exc.status,
                    item.root_path,
                )
                touch_heartbeat()
                return exc
            logger.exception("Failed to process %s", item.root_path)
        touch_heartbeat()
    return None


def _sleep(seconds: int) -> None:
    """Sleeps in short chunks, keeping the heartbeat fresh so a long back-off
    doesn't make the container look hung to the healthcheck."""
    deadline = time.monotonic() + seconds
    while (remaining := deadline - time.monotonic()) > 0:
        time.sleep(min(remaining, 60))
        touch_heartbeat()


def main() -> None:
    gemini_client = GeminiClient()
    state_store = ProcessedStateStore(settings.state_file)
    backoff = INITIAL_BACKOFF_SECONDS
    while True:
        touch_heartbeat()
        error = run_once(gemini_client, state_store)
        if error is None:
            backoff = INITIAL_BACKOFF_SECONDS
            _sleep(settings.poll_interval_seconds)
            continue
        # Double the wait after each consecutive failure (30s, 1m, 2m ... 30m)
        # so an exhausted quota isn't hammered. Honor Gemini's own retryDelay
        # when it sends one; retrying sooner just gets another 429.
        delay = _retry_delay_seconds(error) or backoff
        logger.warning("Backing off Gemini for %d seconds", delay)
        _sleep(delay)
        backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


if __name__ == "__main__":
    main()
