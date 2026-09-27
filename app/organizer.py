import os
import re
import shutil

from .config import settings

_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|]')
# S01E01, s1e1, multi-episode S01E01E02 / S01E01-E02, and the 1x01 style.
_EPISODE_TAG = re.compile(
    r"(?<![a-z0-9])s(\d{1,2})[ ._-]?((?:e\d{1,3})(?:-?e\d{1,3})*)(?![0-9])"
    r"|(?<![a-z0-9])(\d{1,2})x(\d{2,3})(?![0-9])",
    re.IGNORECASE,
)


def sanitize_filename(name: str) -> str:
    return _ILLEGAL_CHARS.sub("", name).strip()


def extract_episode_tag(filename: str) -> str | None:
    """Returns the normalized season/episode marker of a series episode
    filename (e.g. "S01E01" or "S01E01E02"), or None for a movie."""
    match = _EPISODE_TAG.search(os.path.basename(filename))
    if not match:
        return None
    if match.group(1):
        episodes = re.findall(r"\d+", match.group(2))
        season = int(match.group(1))
    else:
        episodes = [match.group(4)]
        season = int(match.group(3))
    return f"S{season:02d}" + "".join(f"E{int(e):02d}" for e in episodes)


def build_target_filename(
    movie_title: str, year: int | None, extension: str, episode_tag: str | None = None
) -> str:
    name = sanitize_filename(movie_title)
    if year:
        name = f"{name} ({year})"
    if episode_tag:
        name = f"{name} {episode_tag}"
    return f"{name}{extension}"


def copy_and_rename(source_path: str, movie_title: str, year: int | None) -> str:
    """Copies the video under its clean title. Series episodes keep their
    season/episode marker so each episode stays identifiable."""
    extension = os.path.splitext(source_path)[1]
    target_name = build_target_filename(
        movie_title, year, extension, extract_episode_tag(source_path)
    )

    os.makedirs(settings.output_dir, exist_ok=True)
    target_path = _avoid_collision(os.path.join(settings.output_dir, target_name))
    shutil.copy2(source_path, target_path)
    return target_path


def copy_keep_name(source_path: str) -> str:
    """Copies a file to the output dir as-is, used when the movie title
    couldn't be verified and we don't trust the AI-guessed name enough to
    rename it."""
    os.makedirs(settings.output_dir, exist_ok=True)
    target_path = _avoid_collision(os.path.join(settings.output_dir, os.path.basename(source_path)))
    shutil.copy2(source_path, target_path)
    return target_path


def copy_subtitle(source_path: str, video_target_path: str) -> str:
    """Copies a subtitle file alongside its video, matching the video's final
    base name so media players auto-detect it. On a name collision (e.g.
    multiple language tracks) the original subtitle filename is appended to
    disambiguate instead of a bare numeric suffix."""
    base, _ = os.path.splitext(video_target_path)
    extension = os.path.splitext(source_path)[1]
    target_path = f"{base}{extension}"

    if os.path.exists(target_path):
        original_stem = sanitize_filename(os.path.splitext(os.path.basename(source_path))[0])
        target_path = f"{base} ({original_stem}){extension}"

    os.makedirs(settings.output_dir, exist_ok=True)
    target_path = _avoid_collision(target_path)
    shutil.copy2(source_path, target_path)
    return target_path


def _avoid_collision(target_path: str) -> str:
    if not os.path.exists(target_path):
        return target_path
    base, ext = os.path.splitext(target_path)
    counter = 2
    while os.path.exists(f"{base} ({counter}){ext}"):
        counter += 1
    return f"{base} ({counter}){ext}"
