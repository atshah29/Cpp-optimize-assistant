"""Project paths, bounded archive extraction, and transactional source edits."""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path, PurePosixPath
import stat
import zipfile

SOURCE_EXTENSIONS = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
MAX_UPLOAD = 20 * 1024 * 1024
MAX_EXTRACTED = 50 * 1024 * 1024
MAX_FILES = 500
IGNORED = {".git", "__MACOSX", "node_modules", ".venv", "build", "dist", ".optimizer-build"}


def relative_path(value: str) -> str:
    if not value or "\\" in value or "\x00" in value or ":" in value:
        raise ValueError("Use a relative project path with forward slashes")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Paths must stay inside the project")
    return path.as_posix()


def inside(root: Path, value: str) -> Path:
    target = (root / relative_path(value)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Path escapes the project")
    return target


def extract_project(archive: Path, destination: Path) -> None:
    total = 0
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) > MAX_FILES:
            raise ValueError(f"Archives may contain at most {MAX_FILES} entries")
        seen = set()
        for entry in entries:
            name = relative_path(entry.filename.rstrip("/"))
            if name in seen:
                raise ValueError("Archive contains duplicate paths")
            seen.add(name)
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("Archive symlinks are not allowed")
            total += entry.file_size
            if total > MAX_EXTRACTED or entry.flag_bits & 1:
                raise ValueError("Archive is too large or encrypted")
            if any(part in IGNORED or part.startswith(".") for part in PurePosixPath(name).parts):
                continue
            target = inside(destination, name)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(entry) as source, target.open("wb") as output:
                copied = 0
                while chunk := source.read(65536):
                    copied += len(chunk)
                    if copied > entry.file_size or copied > MAX_EXTRACTED:
                        raise ValueError("Archive exceeds its declared size")
                    output.write(chunk)


def source_files(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in IGNORED or part.startswith(".") for part in rel.parts):
            continue
        if path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS:
            if path.stat().st_size > 512_000:
                continue
            result[rel.as_posix()] = path.read_bytes().decode("utf-8")
    return result


def apply_edits(root: Path, edits: list[dict], allowed: set[str]) -> str:
    """Validate every edit before writing; only exact, unique matches are allowed."""
    originals, updated = {}, {}
    if not 1 <= len(edits) <= 12:
        raise ValueError("A proposal must contain between 1 and 12 edits")
    for edit in edits:
        name = relative_path(edit["path"])
        if name not in allowed:
            raise ValueError(f"Editing {name} is not allowed")
        path = inside(root, name)
        if name not in originals:
            originals[name] = path.read_bytes().decode("utf-8")
            updated[name] = originals[name]
        old, new = edit["old"], edit["new"]
        if not old or old == new or updated[name].count(old) != 1:
            raise ValueError(f"Edit in {name} must uniquely match existing text and change it")
        updated[name] = updated[name].replace(old, new, 1)
        if len(updated[name].encode()) > 512_000:
            raise ValueError("Edited source is too large")
    diff = "".join(
        "".join(
            difflib.unified_diff(
                originals[name].splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{name}",
                tofile=f"b/{name}",
            )
        )
        for name, content in updated.items()
    )
    for name, content in updated.items():
        inside(root, name).write_bytes(content.encode("utf-8"))
    return diff


def project_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()
