"""Fetch and prepare a small, hash-verified LLVM test-suite subset."""

import hashlib
import json
import re
from pathlib import Path
import shutil
import ssl
from urllib.parse import quote
from urllib.request import urlopen

import certifi

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "benchmarks/llvm/manifest.json"


def manifest():
    return json.loads(MANIFEST.read_text())


def catalog():
    return [("llvm_" + item["name"], item["category"], 0, 0) for item in manifest()["benchmarks"]]


def fetch(cache: Path | None = None):
    spec = manifest()
    root = (cache or ROOT / ".tools/llvm-suite") / spec["revision"]
    root.mkdir(parents=True, exist_ok=True)
    for name, info in spec["files"].items():
        target = root / name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == info["sha256"]:
            continue
        url = (
            f"https://raw.githubusercontent.com/llvm/llvm-test-suite/{spec['revision']}/{quote(info['path'])}"
        )
        with urlopen(url, context=ssl.create_default_context(cafile=certifi.where()), timeout=30) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000 or hashlib.sha256(data).hexdigest() != info["sha256"]:
            raise ValueError(f"Upstream checksum mismatch: {name}")
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(target)
    return root


def reference_stdout(text):
    trailer = "exit 0\n"
    if not text.endswith(trailer):
        raise ValueError("Expected a successful LLVM reference-output trailer")
    return text[: -len(trailer)]


def prepare(name: str, destination: Path):
    spec = manifest()
    entry = next(item for item in spec["benchmarks"] if "llvm_" + item["name"] == name)
    cached = fetch()
    for filename in (entry["source"], entry["reference"], "LICENSE.TXT", "README.txt"):
        shutil.copyfile(cached / filename, destination / filename)
    (destination / "upstream.json").write_text(
        json.dumps(
            {
                "revision": spec["revision"],
                "repository": spec["repository"],
                "benchmark": entry,
                "files": spec["files"],
            },
            indent=2,
        )
    )
    source = (cached / entry["source"]).read_text()
    main = re.search(r"\bint\s+main\s*\(", source)
    if main is None:
        raise ValueError("Pinned LLVM source has no recognized main driver")
    return {
        "sources": [entry["source"]],
        "editable_files": [entry["source"]],
        "protected_main": {entry["source"]: source[main.start() :]},
        "cases": [
            {
                "name": "upstream-reference",
                "args": entry["args"],
                "expected_stdout": reference_stdout((cached / entry["reference"]).read_text()),
            },
            {"name": "alternate-input", "args": entry["alternate_args"]},
        ],
        "run_timeout": 30,
    }
