"""Checkpointed, sequential benchmark evaluation. Defaults to one offline baseline."""

import argparse
import csv
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import threading
import time

from dotenv import load_dotenv

from benchmarks.catalog import CATALOG, workloads
from pipeline import optimize
from schemas import Options

ROOT = Path(__file__).resolve().parent


def summarize(state):
    entries = state.get("catalog", CATALOG)
    completed = [row for row in state["results"].values() if row["status"] == "completed"]
    measured = [row for row in completed if row.get("reduction") is not None]
    mean = sum(row["reduction"] for row in measured) / len(measured) if measured else None
    complete = len(completed) == len(entries) and len(measured) == len(entries)
    return {
        "suite_size": len(entries),
        "completed": len(completed),
        "optimized_evaluations": len(measured),
        "mean_runtime_reduction_percent": mean * 100 if mean is not None else None,
        "geometric_mean_speedup": math.exp(sum(math.log(row["speedup"]) for row in measured) / len(measured))
        if measured
        else None,
        "claim_70_percent_supported": bool(complete and len(entries) >= 20 and mean >= 0.70),
        "claim_status": "complete"
        if complete
        else "incomplete — baseline-only, missing, failed, or deferred benchmarks remain",
        "method": "Arithmetic mean of per-benchmark runtime reductions; each benchmark uses sum of workload medians. Unchanged results count as 0%.",
        "scope": (
            "Selected pinned LLVM test-suite workloads run with our harness; not the full upstream suite."
            if state.get("suite") == "llvm"
            else "22 synthetic optimization exercises, not evidence for arbitrary production projects or a historical benchmark run."
        ),
    }


def save(directory, state):
    state["summary"] = summarize(state)
    temporary = directory / "state.tmp"
    temporary.write_text(json.dumps(state, indent=2))
    temporary.replace(directory / "state.json")
    (directory / "summary.json").write_text(json.dumps(state["summary"], indent=2))
    with (directory / "results.csv").open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            [
                "benchmark",
                "category",
                "status",
                "baseline_seconds",
                "result_seconds",
                "reduction_percent",
                "speedup",
                "report",
            ]
        )
        for name, category, _, _ in state.get("catalog", CATALOG):
            row = state["results"].get(name, {})
            writer.writerow(
                [
                    name,
                    category,
                    row.get("status", "pending"),
                    row.get("baseline_seconds", ""),
                    row.get("result_seconds", ""),
                    100 * row["reduction"] if row.get("reduction") is not None else "",
                    row.get("speedup", ""),
                    row.get("report", ""),
                ]
            )


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["benchmark", "optimize"], default="benchmark")
    parser.add_argument("--suite", choices=["synthetic", "llvm"], default="synthetic")
    parser.add_argument("--runner", choices=["docker", "native"])
    parser.add_argument("--output", type=Path, default=Path("benchmark-results"))
    parser.add_argument("--attempts", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--repeats", type=int, choices=range(5, 16), default=7)
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Enable Callgrind (slower; requires the Docker runner or local Valgrind)",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--next", action="store_true", help="Run one unfinished benchmark (default)")
    selection.add_argument(
        "--all", action="store_true", help="Run sequentially; stop at provider unavailability"
    )
    selection.add_argument("--benchmark", help="Run one named unfinished benchmark")
    selection.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    from llvm_suite import MANIFEST, catalog as llvm_catalog, prepare as prepare_llvm

    entries = llvm_catalog() if args.suite == "llvm" else CATALOG
    if args.benchmark and args.benchmark not in {entry[0] for entry in entries}:
        parser.error("Unknown benchmark for the selected suite")
    if args.runner:
        os.environ["OPTIMIZER_RUNNER"] = args.runner
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    lock_handle = (directory / "run.lock").open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("Another process is already running this suite")
    state_path = directory / "state.json"
    if args.report_only:
        if not state_path.exists():
            parser.error("No saved run at this output path")
        state = json.loads(state_path.read_text())
        save(directory, state)
        print(json.dumps(state["summary"], indent=2))
        return
    settings = {
        "mode": args.mode,
        "runner": os.getenv("OPTIMIZER_RUNNER", "docker"),
        "attempts": args.attempts,
        "repeats": args.repeats,
        "profile": args.profile,
        "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        "reasoning_effort": os.getenv("GROQ_REASONING_EFFORT", "medium"),
        "max_completion_tokens": os.getenv("GROQ_MAX_COMPLETION_TOKENS", "2048"),
        "suite_sha256": hashlib.sha256(
            b"".join(
                path.relative_to(ROOT).as_posix().encode() + path.read_bytes()
                for path in sorted((ROOT / "benchmarks").rglob("*"))
                if path.suffix in {".py", ".cpp", ".hpp"}
            )
        ).hexdigest(),
    }
    if args.suite == "llvm":
        settings["suite_sha256"] = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
        settings["suite"] = "llvm"
    # Avoid mixing incompatible machines or experiments in one headline statistic.
    settings["machine"] = {
        "system": platform.system(),
        "machine": platform.machine(),
        "host": platform.node(),
    }
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state["settings"] != settings:
            parser.error(
                "Run settings or suite changed. Use a different --output directory to keep evidence comparable."
            )
        # Successful live reports carry the full sampling configuration. Compare it
        # as well so changing temperature cannot silently mix experiments on resume.
        from feedback import model_settings

        for row in state["results"].values():
            if row.get("report"):
                previous = json.loads((directory / row["report"]).read_text())
                for attempt in previous["attempts"]:
                    recorded = attempt.get("model_call", {}).get("settings")
                    if recorded and recorded != model_settings():
                        parser.error("Model hyperparameters changed. Use a different --output directory.")
    else:
        state = {
            "created": time.time(),
            "settings": settings,
            "results": {},
            "suite": args.suite,
            "catalog": entries,
        }
    pending = [entry for entry in entries if state["results"].get(entry[0], {}).get("status") != "completed"]
    selected = [entry for entry in pending if not args.benchmark or entry[0] == args.benchmark]
    if not args.all:
        selected = selected[:1]
    save(directory, state)
    for entry in selected:
        name = entry[0]
        folder = directory / name / str(time.time_ns())
        folder.mkdir(parents=True)
        source = folder / "original"
        source.mkdir()
        if args.suite == "llvm":
            project_options = prepare_llvm(name, source)
        else:
            for file in (ROOT / "benchmarks/support").iterdir():
                shutil.copy2(file, source / file.name)
            shutil.copy2(ROOT / f"benchmarks/kernels/{name}.cpp", source / "kernel.cpp")
            project_options = {
                "sources": ["driver.cpp", "kernel.cpp"],
                "editable_files": ["kernel.cpp"],
                "cases": workloads(entry),
            }
        options = Options(
            mode=args.mode,
            **project_options,
            attempts=args.attempts,
            repeats=args.repeats,
            profile=args.profile,
        )
        try:
            print(f"\n{name}: starting {args.mode}", flush=True)
            report = optimize(
                folder,
                options.model_dump(),
                threading.Event(),
                lambda **status: print(f"  {status.get('stage', '')}", flush=True),
            )
            deferred = any(attempt["status"] == "unavailable" for attempt in report["attempts"])
            comparison = report.get("final_comparison", {})
            old = comparison.get("before", report["baseline"]["benchmarks"])
            new = comparison["after"] if report["outcome"] == "improved" else old
            baseline_seconds = sum(item["median_seconds"] for item in old.values())
            result_seconds = sum(item["median_seconds"] for item in new.values())
            state["results"][name] = {
                "status": "deferred" if deferred else "completed",
                "outcome": report["outcome"],
                "baseline_seconds": baseline_seconds,
                "result_seconds": result_seconds,
                "reduction": (1 - result_seconds / baseline_seconds)
                if args.mode == "optimize" and not deferred
                else None,
                "speedup": baseline_seconds / result_seconds,
                "report": (folder / "report.json").relative_to(directory).as_posix(),
            }
            save(directory, state)
            if deferred:
                print("Provider unavailable or rate limited. Progress saved; rerun --next later.", flush=True)
                break
        except (RuntimeError, ValueError) as exc:
            state["results"][name] = {"status": "failed", "error": str(exc)}
            save(directory, state)
            print(f"  Failed: {exc}", flush=True)
        except KeyboardInterrupt:
            state["results"][name] = {"status": "interrupted"}
            save(directory, state)
            print("Interrupted; completed benchmarks are saved.")
            break
    print(json.dumps(state["summary"], indent=2))


if __name__ == "__main__":
    main()
