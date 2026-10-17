"""Run an existing project locally without the web interface."""

import argparse
import json
from pathlib import Path
import shutil
import tempfile
import threading

from dotenv import load_dotenv

from pipeline import optimize
from schemas import Options


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Validate and optimize a local C/C++ project")
    parser.add_argument("project", type=Path)
    parser.add_argument("--mode", choices=["compile", "benchmark", "optimize"])
    parser.add_argument("--output", type=Path, default=Path("optimizer-result.zip"))
    args = parser.parse_args()
    root = args.project.resolve()
    if not root.is_dir():
        parser.error("project must be a directory")
    manifest = root / "optimizer.json"
    settings = json.loads(manifest.read_text()) if manifest.exists() else {}
    if args.mode:
        settings["mode"] = args.mode
    options = Options.model_validate(settings)
    output = args.output.resolve()
    if output.exists():
        parser.error("Output already exists; choose a new --output path")
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        # Exclude credentials, VCS metadata, generated outputs, and local dependencies.
        shutil.copytree(
            root,
            work / "original",
            symlinks=True,
            ignore=shutil.ignore_patterns(".*", "build", "dist", "node_modules", "__pycache__"),
        )
        if any(path.is_symlink() for path in (work / "original").rglob("*")):
            parser.error("Project symlinks are not supported; supply regular files")
        try:
            result = optimize(
                work, options.model_dump(), threading.Event(), lambda **status: print(status.get("stage", ""))
            )
        except (RuntimeError, ValueError) as exc:
            parser.exit(1, f"Error: {exc}\n")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(work / "result.zip", output)
        print(f"{result['outcome']}: {output}")


if __name__ == "__main__":
    main()
