"""Local API: upload -> job -> progress -> evidence and preserved source archive."""

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.concurrency import run_in_threadpool

from jobs import JobStore
from schemas import Options
from utils import MAX_UPLOAD, extract_project, inside, source_files

load_dotenv()
ROOT = Path(__file__).resolve().parent


class RequestLimit:
    """Bound the full multipart body before the framework spools uploaded files."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        origin = headers.get(b"origin", b"").decode()
        allowed = {
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        }
        if scope["method"] in {"POST", "DELETE"} and origin and origin not in allowed:
            return await JSONResponse({"detail": "Only local browser origins are allowed"}, 403)(
                scope, receive, send
            )
        if scope["method"] != "POST":
            return await self.app(scope, receive, send)
        chunks, total = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            total += len(body)
            if total > MAX_UPLOAD + 131072:
                return await JSONResponse({"detail": "Upload exceeds 20 MiB"}, 413)(scope, receive, send)
            chunks.append(body)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


@asynccontextmanager
async def lifespan(application):
    application.state.jobs = JobStore(Path(os.getenv("OPTIMIZER_JOB_DIR", str(ROOT / ".optimizer-jobs"))))
    yield
    await run_in_threadpool(application.state.jobs.close)


app = FastAPI(title="C++ Optimizer", version="0.2.0", lifespan=lifespan)
app.add_middleware(RequestLimit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])


@app.get("/api/health")
async def health():
    mode = os.getenv("OPTIMIZER_RUNNER", "docker")
    return {
        "status": "ok",
        "runner": mode,
        "model_configured": bool(os.getenv("GROQ_API_KEY")),
        "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        "runner_available": bool(shutil.which("docker" if mode == "docker" else "clang++")),
        "notice": "Use locally. Native execution is only for code you trust.",
    }


def prepare_and_submit(upload: Path, name: str, raw_options: dict, store: JobStore, parent: Path):
    project = parent / "project"
    project.mkdir()
    if name.lower().endswith(".zip"):
        extract_project(upload, project)
        entries = list(project.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            project = entries[0]
    elif Path(name).suffix.lower() in {".c", ".cpp", ".cc", ".cxx"}:
        path = inside(project, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(upload, path)
    else:
        raise ValueError("Upload a C/C++ source file or a ZIP project")
    manifest = project / "optimizer.json"
    defaults = json.loads(manifest.read_text()) if manifest.exists() else {}
    if not isinstance(defaults, dict):
        raise ValueError("optimizer.json must contain an object")
    options = Options.model_validate({**defaults, **raw_options})
    files = source_files(project)
    if not files:
        raise ValueError("No UTF-8 C/C++ sources found")
    for name in options.sources + options.include_dirs + options.editable_files + [options.working_dir]:
        if not inside(project, name).exists():
            raise ValueError(f"Project path does not exist: {name}")
    return store.submit(project, options.model_dump())


@app.post("/api/jobs", status_code=202)
async def submit(request: Request, project: UploadFile = File(...), options: str = Form("{}")):
    try:
        raw = json.loads(options)
        if not isinstance(raw, dict):
            raise ValueError("Options must be a JSON object")
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            upload = parent / "upload"
            total = 0
            with upload.open("wb") as output:
                while chunk := await project.read(65536):
                    total += len(chunk)
                    if total > MAX_UPLOAD:
                        raise HTTPException(413, "Upload exceeds 20 MiB")
                    output.write(chunk)
            return await run_in_threadpool(
                prepare_and_submit, upload, project.filename or "", raw, request.app.state.jobs, parent
            )
    except (ValueError, ValidationError, zipfile.BadZipFile, UnicodeError) as exc:
        raise HTTPException(422, str(exc)[:3000]) from exc
    finally:
        await project.close()


def get_job(request, identifier):
    try:
        return request.app.state.jobs.get(identifier)
    except KeyError as exc:
        raise HTTPException(404, "Job not found or expired (results are retained for 24 hours)") from exc


@app.get("/api/jobs/{identifier}")
async def status(identifier: str, request: Request):
    return get_job(request, identifier)


@app.delete("/api/jobs/{identifier}")
async def cancel(identifier: str, request: Request):
    get_job(request, identifier)
    return request.app.state.jobs.cancel(identifier)


@app.get("/api/jobs/{identifier}/report")
async def report(identifier: str, request: Request):
    job = get_job(request, identifier)
    if job["status"] != "completed":
        raise HTTPException(409, "Job has no completed report")
    return FileResponse(
        request.app.state.jobs.root / identifier / "report.json", media_type="application/json"
    )


@app.get("/api/jobs/{identifier}/download")
async def download(identifier: str, request: Request):
    job = get_job(request, identifier)
    if job["status"] != "completed":
        raise HTTPException(409, "Job has no completed download")
    return FileResponse(
        request.app.state.jobs.root / identifier / "result.zip",
        filename=f"cpp-optimizer-{identifier[:8]}.zip",
        media_type="application/zip",
    )


@app.post("/optimize-files", include_in_schema=False)
@app.post("/optimize-zip", include_in_schema=False)
async def legacy():
    raise HTTPException(410, "Use POST /api/jobs, then poll its status and download the result")


if (ROOT / "frontend/dist").is_dir():
    app.mount("/", StaticFiles(directory=ROOT / "frontend/dist", html=True), name="frontend")
else:

    @app.get("/")
    async def root():
        return {"name": "C++ Optimizer", "docs": "/docs", "frontend": "http://localhost:5173"}
