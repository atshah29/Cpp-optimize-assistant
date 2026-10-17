import io
import json
import time
import zipfile

from fastapi.testclient import TestClient
import pytest

import main
from jobs import JobStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIMIZER_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("GROQ_API_KEY", "")

    def fake_run(self, identifier):
        self.update(identifier, status="completed", progress=100)

    monkeypatch.setattr(JobStore, "run", fake_run)
    with TestClient(main.app) as client:
        yield client


def test_health_without_model(client):
    assert client.get("/api/health").json()["model_configured"] is False


def test_upload_and_poll(client):
    response = client.post(
        "/api/jobs", files={"project": ("main.cpp", b"int main() {}")}, data={"options": '{"mode":"compile"}'}
    )
    assert response.status_code == 202
    job = response.json()
    assert client.get(f"/api/jobs/{job['id']}").status_code == 200
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 200


@pytest.mark.parametrize("name", ["../escape.cpp", "/tmp/escape.cpp", "bad.exe"])
def test_invalid_upload_paths(client, name):
    response = client.post("/api/jobs", files={"project": (name, b"int main() {}")})
    assert response.status_code == 422


def test_invalid_options_and_missing_job(client):
    response = client.post(
        "/api/jobs", files={"project": ("main.cpp", b"int main() {}")}, data={"options": "[]"}
    )
    assert response.status_code == 422
    assert client.get("/api/jobs/missing").status_code == 404
    assert client.post("/optimize-files").status_code == 410


def test_manifest_and_wrapper_directory(client):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("project/main.cpp", "int main() {}")
        archive.writestr("project/optimizer.json", json.dumps({"mode": "compile", "standard": "c++20"}))
    response = client.post("/api/jobs", files={"project": ("project.zip", data.getvalue())})
    assert response.status_code == 202
    assert response.json()["options"]["standard"] == "c++20"


def test_foreign_browser_origin_rejected(client):
    response = client.post(
        "/api/jobs",
        headers={"Origin": "https://evil.example"},
        files={"project": ("main.cpp", b"int main() {}")},
    )
    assert response.status_code == 403


def test_oversized_request_rejected(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD", 10)
    response = client.post("/api/jobs", files={"project": ("main.cpp", b"x" * 200000)})
    assert response.status_code == 413


def test_restart_marks_active_jobs_failed(tmp_path):
    folder = tmp_path / ("a" * 32)
    folder.mkdir()
    (folder / "status.json").write_text(
        json.dumps({"id": folder.name, "status": "running", "created": time.time()})
    )
    store = JobStore(tmp_path)
    try:
        assert store.get(folder.name)["status"] == "failed"
    finally:
        store.close()


def test_real_job_download_roundtrip(tmp_path, monkeypatch):
    from tests.test_worker import compiler_available

    if not compiler_available():
        pytest.skip("Clang toolchain unavailable")
    monkeypatch.setenv("OPTIMIZER_JOB_DIR", str(tmp_path / "real-jobs"))
    monkeypatch.setenv("OPTIMIZER_RUNNER", "native")
    monkeypatch.setenv("GROQ_API_KEY", "")
    with TestClient(main.app) as client:
        response = client.post(
            "/api/jobs",
            files={"project": ("main.cpp", b"int main() {}")},
            data={"options": '{"mode":"compile"}'},
        )
        assert response.status_code == 202
        identifier = response.json()["id"]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = client.get(f"/api/jobs/{identifier}").json()
            if state["status"] in {"completed", "failed"}:
                break
            time.sleep(0.02)
        assert state["status"] == "completed", state
        report = client.get(f"/api/jobs/{identifier}/report").json()
        assert report["outcome"] == "compiled"
        assert report["attempts"] == []
        downloaded = client.get(f"/api/jobs/{identifier}/download")
        with zipfile.ZipFile(io.BytesIO(downloaded.content)) as bundle:
            assert bundle.read("project/main.cpp") == b"int main() {}"
