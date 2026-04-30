#!/usr/bin/env python3
"""
organize_music.py
Reorganizes audio files into:
    <Album>/<Track#> - <Title>.<ext>

Fuzzy-matches similar album names and lets you pick the canonical name
before moving anything.

Requirements:
    pip install mutagen rapidfuzz
"""

import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

try:
    from mutagen import File as MutagenFile
except ImportError:
    sys.exit("mutagen is not installed. Run: pip install mutagen")

try:
    from rapidfuzz import fuzz, process
except ImportError:
    sys.exit("rapidfuzz is not installed. Run: pip install rapidfuzz")


# ── Config ────────────────────────────────────────────────────────────────────

# Set to True to preview changes without moving any files
DRY_RUN = False

# Root folder containing your music (edit or pass as a command-line arg)
MUSIC_ROOT = r"C:\Users\tylim\Music"

# Output folder (same as MUSIC_ROOT to reorganize in place)
OUTPUT_ROOT = r"C:\Users\tylim\Music"

# How similar two album names need to be to be flagged as a match (0-100)
# 80 is a good default — lower = more aggressive matching
FUZZY_THRESHOLD = 50

# Audio extensions to process
AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav", ".aac"}

FALLBACK_ALBUM  = "Unknown Album"
FALLBACK_TRACK  = "00"
FALLBACK_TITLE  = None  # None = use filename


# ── Helpers ───────────────────────────────────────────────────────────────────

def sanitize(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = name.strip(". ")
    return name or "_"


def get_tag(tags, *keys, fallback=""):
    for key in keys:
        val = tags.get(key)
        if val:
            if isinstance(val, list):
                val = val[0]
            val = str(val).strip()
            if val:
                return val
    return fallback


def parse_track(raw: str) -> str:
    if not raw:
        return FALLBACK_TRACK
    num = raw.split("/")[0]
    try:
        return f"{int(num):02d}"
    except ValueError:
        return FALLBACK_TRACK


def extract_metadata(path: Path) -> dict:
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        audio = None

    if audio is None:
        return {
            "album": FALLBACK_ALBUM,
            "track": FALLBACK_TRACK,
            "title": path.stem,
            "ext":   path.suffix.lower(),
        }

    tags = audio.tags or {}

    title = get_tag(tags, "title", "TIT2") or (FALLBACK_TITLE or path.stem)
    album = get_tag(tags, "album", "TALB") or FALLBACK_ALBUM
    track = parse_track(get_tag(tags, "tracknumber", "TRCK"))

    return {
        "album": album,
        "track": track,
        "title": sanitize(title),
        "ext":   path.suffix.lower(),
    }


# ── Fuzzy album grouping ──────────────────────────────────────────────────────

def fuzzy_merge_albums(album_names: list, threshold: int) -> dict:
    """
    Returns a mapping of {original_album_name: canonical_album_name}.
    Groups similar album names together and asks the user to pick one.
    """
    unique = list(dict.fromkeys(album_names))
    groups = []
    assigned = set()

    for name in unique:
        if name in assigned:
            continue
        matches = process.extract(
            name, unique,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=threshold
        )
        group = {m[0] for m in matches}
        group.add(name)
        groups.append(group)
        assigned.update(group)

    mapping = {}

    for group in groups:
        if len(group) == 1:
            name = next(iter(group))
            mapping[name] = name
        else:
            sorted_group = sorted(group)
            print("\n" + "─" * 60)
            print("These album names look like the same album:")
            for i, name in enumerate(sorted_group, 1):
                print(f"  {i}. {name}")
            print(f"  {len(sorted_group) + 1}. Keep them SEPARATE (don't merge)")

            while True:
                try:
                    choice = int(input(f"\nWhich name should be used? [1-{len(sorted_group) + 1}]: "))
                    if 1 <= choice <= len(sorted_group):
                        canonical = sorted_group[choice - 1]
                        for name in sorted_group:
                            mapping[name] = canonical
                        break
                    elif choice == len(sorted_group) + 1:
                        for name in sorted_group:
                            mapping[name] = name
                        break
                    else:
                        print("Invalid choice, try again.")
                except ValueError:
                    print("Please enter a number.")

    return mapping


# ── Main ──────────────────────────────────────────────────────────────────────

def organize(music_root: str):
    root = Path(music_root)
    if not root.exists():
        sys.exit(f"Folder not found: {root}")

    files = [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    ]

    if not files:
        print("No audio files found.")
        return

    print(f"Found {len(files)} audio file(s). Scanning tags...\n")

    file_meta = {f: extract_metadata(f) for f in sorted(files)}

    all_albums = [m["album"] for m in file_meta.values()]
    album_mapping = fuzzy_merge_albums(all_albums, FUZZY_THRESHOLD)

    print("\n" + "─" * 60)
    print(f"DRY_RUN={DRY_RUN}\n")

    moved   = 0
    skipped = 0
    errors  = 0

    for src, meta in file_meta.items():
        try:
            raw_album   = meta["album"]
            canon_album = sanitize(album_mapping.get(raw_album, raw_album))
            filename    = f"{meta['track']} - {meta['title']}{meta['ext']}"
            dest        = Path(OUTPUT_ROOT) / canon_album / filename

            if src.resolve() == dest.resolve():
                print(f"  [SKIP] Already in place: {src.name}")
                skipped += 1
                continue

            if dest.exists():
                stem, suffix = dest.stem, dest.suffix
                counter = 1
                while dest.exists():
                    dest = dest.with_name(f"{stem} ({counter}){suffix}")
                    counter += 1

            print(f"  [{'DRY' if DRY_RUN else 'MOVE'}] {src.name}")
            print(f"         → {dest}\n")

            if not DRY_RUN:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))

            moved += 1

        except Exception as e:
            print(f"  [ERROR] {src}: {e}")
            errors += 1

    print("─" * 60)
    print(f"Done.  Moved: {moved}  Skipped: {skipped}  Errors: {errors}")

    if DRY_RUN:
        print("\nThis was a DRY RUN — no files were moved.")
        print("Set DRY_RUN = False to apply changes.")

    if not DRY_RUN:
        cleanup_empty_dirs(root)


def cleanup_empty_dirs(root: Path):
    removed = 0
    for dirpath in sorted(Path(root).rglob("*"), reverse=True):
        if dirpath.is_dir():
            try:
                dirpath.rmdir()
                removed += 1
            except OSError:
                pass
    if removed:
        print(f"Removed {removed} empty folder(s).")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else MUSIC_ROOT
    organize(root)