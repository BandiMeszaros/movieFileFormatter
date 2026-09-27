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

    return _copy_once(source_path, os.path.join(settings.output_dir, target_name))


def copy_keep_name(source_path: str) -> str:
    """Copies a file to the output dir as-is, used when the movie title
    couldn't be verified and we don't trust the AI-guessed name enough to
    rename it."""
    return _copy_once(source_path, os.path.join(settings.output_dir, os.path.basename(source_path)))


def copy_subtitle(source_path: str, video_target_path: str) -> str:
    """Copies a subtitle file alongside its video, matching the video's final
    base name so media players auto-detect it. On a name collision (e.g.
    multiple language tracks) the original subtitle filename is appended to
    disambiguate instead of a bare numeric suffix."""
    base, _ = os.path.splitext(video_target_path)
    extension = os.path.splitext(source_path)[1]
    target_path = f"{base}{extension}"

    if os.path.exists(target_path):
        if _is_copy_of(source_path, target_path):
            return target_path
        original_stem = sanitize_filename(os.path.splitext(os.path.basename(source_path))[0])
        target_path = f"{base} ({original_stem}){extension}"

    return _copy_once(source_path, target_path)


def _copy_once(source_path: str, target_path: str) -> str:
    """Copies source to target_path, or to a numbered variant if that name is
    taken by a different file. If source was already copied to one of those
    names (e.g. the state file was lost and the item is reprocessed), returns
    that existing copy instead of duplicating it."""
    base, ext = os.path.splitext(target_path)
    candidate, counter = target_path, 2
    while os.path.exists(candidate):
        if _is_copy_of(source_path, candidate):
            return candidate
        candidate = f"{base} ({counter}){ext}"
        counter += 1

    os.makedirs(os.path.dirname(candidate), exist_ok=True)
    shutil.copy2(source_path, candidate)
    return candidate


def _is_copy_of(source_path: str, target_path: str) -> bool:
    """copy2 preserves the modification time, so a copy we made earlier has
    the source's size and mtime. The 2s tolerance covers filesystems with
    coarse timestamps."""
    source, target = os.stat(source_path), os.stat(target_path)
    return source.st_size == target.st_size and abs(source.st_mtime - target.st_mtime) < 2

