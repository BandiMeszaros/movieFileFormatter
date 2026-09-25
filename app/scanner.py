import os
from dataclasses import dataclass


@dataclass
class ScanItem:
    """A single top-level entry in the input directory.

    Either a standalone video file dropped directly in the input dir, or a
    directory (as transmission creates for multi-file torrents) that may
    contain the actual video plus extras like .nfo/.txt/sample files.
    """

    root_path: str
    is_directory: bool
    files: list


def scan_input_dir(input_dir: str) -> list:
    """Lists the top-level entries of input_dir. For directories, walks
    recursively and records every file path relative to that directory,
    so the AI step can see everything before deciding what to move.
    """
    items = []
    with os.scandir(input_dir) as entries:
        for entry in sorted(entries, key=lambda e: e.name):
            if entry.is_file():
                items.append(ScanItem(root_path=entry.path, is_directory=False, files=[entry.name]))
            elif entry.is_dir():
                files = []
                for dirpath, _, filenames in os.walk(entry.path):
                    for name in filenames:
                        rel = os.path.relpath(os.path.join(dirpath, name), entry.path)
                        files.append(rel)
                items.append(ScanItem(root_path=entry.path, is_directory=True, files=files))
    return items
