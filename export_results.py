"""Export curated, reviewable benchmark evidence without credentials or job binaries."""

import argparse
import csv
import json
from pathlib import Path
import re
import shutil

from benchmark_suite import summarize


def sanitized(value):
    if isinstance(value, dict):
        return {key: sanitized(item) for key, item in value.items() if key not in {"host", "rate_limits"}}
    if isinstance(value, list):
        return [sanitized(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"/Users/[^/\s]+", "<user-home>", value)
    return value


def export(source: Path, destination: Path):
    state = json.loads((source / "state.json").read_text())
    if destination.exists():
        raise ValueError("Evidence destination already exists; use a new snapshot directory")
    destination.mkdir(parents=True)
    (destination / "summary.json").write_text(json.dumps(sanitized(summarize(state)), indent=2) + "\n")
    (destination / "settings.json").write_text(json.dumps(sanitized(state["settings"]), indent=2) + "\n")
    with (
        (source / "results.csv").open(newline="") as original,
        (destination / "results.csv").open("w", newline="") as output,
    ):
        reader = csv.DictReader(original)
        writer = csv.DictWriter(output, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if row["report"]:
                row["report"] = f"{row['benchmark']}/report.json"
            writer.writerow(row)
    index = {}
    for name, row in state["results"].items():
        index[name] = sanitized(row)
        if not row.get("report"):
            continue
        path = source / row["report"]
        report = json.loads(path.read_text())
        folder = destination / name
        folder.mkdir()
        (folder / "report.json").write_text(json.dumps(sanitized(report), indent=2) + "\n")
        (folder / "changes.diff").write_text(report["diff"])
        # Publish the actual inputs/results, including third-party notices where present.
        for version in ("original", "best"):
            shutil.copytree(path.parent / version, folder / version)
        index[name]["report"] = f"{name}/report.json"
    (destination / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    (destination / "README.md").write_text(
        "# Local benchmark evidence\n\n"
        "This snapshot contains the exact original and retained sources, raw timing samples, "
        "validation outcomes, proposal diffs, and recorded model usage. See [summary](summary.json), "
        "[settings](settings.json), and [index](index.json). Host/user names are redacted.\n\n"
        "Failed or deferred runs remain visible; unchanged results contribute zero improvement. "
        "One attempt per benchmark is a limited search budget. These results are specific to the "
        "recorded workloads and environment and do not establish general-purpose performance. "
        "Inspect rejected proposals in each report as well as accepted patches.\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    export(args.source, args.destination)
