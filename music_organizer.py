#!/usr/bin/env python3
"""
organize_music.py
Reorganizes MP3 (and other audio) files into:
    <Album Artist>/<Album>/<Track#> - <Title>.<ext>

Requirements:
    pip install mutagen
"""

import os
import re
import shutil
import sys
from pathlib import Path

try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3NoHeaderError
except ImportError:
    sys.exit("mutagen is not installed. Run: pip install mutagen")


# ── Config ────────────────────────────────────────────────────────────────────

# Set this to True to preview changes without moving any files
DRY_RUN = False

# Root folder containing your music (edit this or pass as a command-line arg)
MUSIC_ROOT = r"C:/Users/tylim/Music"

# Output folder (can be the same as MUSIC_ROOT to reorganize in place)
OUTPUT_ROOT = r"C:/Users/tylim/Music"

# Folder/filename template
# Available placeholders: {album_artist}, {artist}, {album}, {track}, {title}, {ext}
TEMPLATE = "{album}/{track} - {title}{ext}"

# Fallback values when tags are missing
FALLBACK_ARTIST = "Unknown Artist"
FALLBACK_ALBUM  = "Unknown Album"
FALLBACK_TRACK  = "00"
FALLBACK_TITLE  = None  # None = use filename

# Audio extensions to process
AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav", ".aac"}

# ── Helpers ───────────────────────────────────────────────────────────────────

def sanitize(name: str) -> str:
    """Remove characters that are illegal in Windows/macOS/Linux filenames."""
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = name.strip(". ")          # strip leading/trailing dots and spaces
    return name or "_"


def get_tag(tags, *keys, fallback=""):
    """Try multiple tag key names, return the first non-empty value found."""
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
    """Turn '3/12' or '3' into zero-padded '03'."""
    if not raw:
        return FALLBACK_TRACK
    num = raw.split("/")[0]
    try:
        return f"{int(num):02d}"
    except ValueError:
        return FALLBACK_TRACK


def extract_metadata(path: Path) -> dict:
    """Read ID3 / Vorbis / MP4 tags from an audio file."""
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        audio = None

    if audio is None:
        return {
            "album_artist": FALLBACK_ARTIST,
            "artist":       FALLBACK_ARTIST,
            "album":        FALLBACK_ALBUM,
            "track":        FALLBACK_TRACK,
            "title":        path.stem,
            "ext":          path.suffix.lower(),
        }

    tags = audio.tags or {}

    # Album Artist → Artist → uploader fallback
    album_artist = get_tag(tags, "albumartist", "album_artist", "TPE2")
    artist       = get_tag(tags, "artist", "TPE1")

    # If no album artist tag, derive it
    if not album_artist:
        album_artist = artist or FALLBACK_ARTIST

    title = get_tag(tags, "title", "TIT2") or (FALLBACK_TITLE or path.stem)
    album = get_tag(tags, "album", "TALB") or FALLBACK_ALBUM
    track = parse_track(get_tag(tags, "tracknumber", "TRCK"))

    return {
        "album_artist": sanitize(album_artist),
        "artist":       sanitize(artist or album_artist),
        "album":        sanitize(album),
        "track":        track,
        "title":        sanitize(title),
        "ext":          path.suffix.lower(),
    }


def build_dest(meta: dict) -> Path:
    rel = TEMPLATE.format(**meta)
    return Path(OUTPUT_ROOT) / rel


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

    print(f"Found {len(files)} audio file(s). DRY_RUN={DRY_RUN}\n")

    moved   = 0
    skipped = 0
    errors  = 0

    for src in sorted(files):
        try:
            meta = extract_metadata(src)
            dest = build_dest(meta)

            if src.resolve() == dest.resolve():
                print(f"  [SKIP] Already in place: {src.name}")
                skipped += 1
                continue

            # Handle duplicate filenames at destination
            if dest.exists():
                stem = dest.stem
                suffix = dest.suffix
                counter = 1
                while dest.exists():
                    dest = dest.with_name(f"{stem} ({counter}){suffix}")
                    counter += 1

            print(f"  [{'DRY' if DRY_RUN else 'MOVE'}] {src}")
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

    # Clean up empty directories left behind
    if not DRY_RUN:
        cleanup_empty_dirs(root)


def cleanup_empty_dirs(root: Path):
    """Remove any empty folders left after moving files."""
    removed = 0
    for dirpath in sorted(root.rglob("*"), reverse=True):
        if dirpath.is_dir():
            try:
                dirpath.rmdir()   # only works if directory is empty
                removed += 1
            except OSError:
                pass
    if removed:
        print(f"Removed {removed} empty folder(s).")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else MUSIC_ROOT
    organize(root)