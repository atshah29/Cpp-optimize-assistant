"""Single-worker local queue with durable status and bounded retention."""

from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
import shutil
import threading
import time
import uuid

from pipeline import optimize
from runner import Cancelled


class JobStore:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.jobs = {}
        self.events = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="optimizer")
        for path in root.glob("*/status.json"):
            try:
                job = json.loads(path.read_text())
                if job["status"] in {"queued", "running", "cancelling"}:
                    job.update(
                        status="failed",
                        stage="Interrupted by server restart",
                        error="Submit the project again",
                    )
                self.jobs[job["id"]] = job
                self.save(job)
            except (ValueError, KeyError, OSError):
                logging.exception("Could not recover job status")
        self.prune()

    def save(self, job):
        folder = self.root / job["id"]
        folder.mkdir(exist_ok=True)
        temp = folder / "status.tmp"
        temp.write_text(json.dumps(job))
        temp.replace(folder / "status.json")

    def prune(self):
        with self.lock:
            finished = sorted(
                (job for job in self.jobs.values() if job["status"] in {"completed", "failed", "cancelled"}),
                key=lambda job: job["created"],
            )
            for job in finished:
                if time.time() - job["created"] > 86400 or len(self.jobs) >= 20:
                    shutil.rmtree(self.root / job["id"], ignore_errors=True)
                    self.jobs.pop(job["id"], None)
                    self.events.pop(job["id"], None)

    def submit(self, prepared: Path, options: dict):
        with self.lock:
            self.prune()
            if sum(job["status"] in {"queued", "running", "cancelling"} for job in self.jobs.values()) >= 3:
                raise ValueError("The local queue is full. Wait for a job to finish.")
            identifier = uuid.uuid4().hex
            folder = self.root / identifier
            folder.mkdir()
            shutil.move(str(prepared), folder / "original")
            job = {
                "id": identifier,
                "status": "queued",
                "stage": "Queued",
                "progress": 0,
                "created": time.time(),
                "options": options,
            }
            self.jobs[identifier] = job
            self.events[identifier] = threading.Event()
            self.save(job)
            self.pool.submit(self.run, identifier)
            return dict(job)

    def update(self, identifier, **changes):
        with self.lock:
            self.jobs[identifier].update(changes)
            self.save(self.jobs[identifier])

    def get(self, identifier):
        with self.lock:
            if identifier not in self.jobs:
                raise KeyError(identifier)
            return dict(self.jobs[identifier])

    def cancel(self, identifier):
        with self.lock:
            job = self.get(identifier)
            if job["status"] in {"queued", "running", "cancelling"}:
                self.events[identifier].set()
                self.update(
                    identifier,
                    status="cancelling",
                    stage="Cancelling (an active model call may take up to 60 seconds)",
                )
            return self.get(identifier)

    def run(self, identifier):
        event = self.events[identifier]
        try:
            if event.is_set():
                raise Cancelled("Job cancelled")
            self.update(identifier, status="running")
            result = optimize(
                self.root / identifier,
                self.jobs[identifier]["options"],
                event,
                lambda **changes: self.update(identifier, **changes),
            )
            if event.is_set():
                raise Cancelled("Job cancelled")
            self.update(
                identifier, status="completed", stage="Complete", progress=100, outcome=result["outcome"]
            )
        except Cancelled:
            self.update(identifier, status="cancelled", stage="Cancelled")
        except Exception as exc:
            logging.exception("Optimization job failed")
            self.update(identifier, status="failed", stage="Failed", error=str(exc)[:7000])
        finally:
            folder = self.root / identifier
            for path in folder.glob("candidate-*"):
                shutil.rmtree(path, ignore_errors=True)

    def close(self):
        for event in self.events.values():
            event.set()
        self.pool.shutdown(wait=True, cancel_futures=True)
