"""Real container integration tests; run with TEST_DOCKER=1 and the built image."""

import os
import threading
import time

import pytest

from runner import Runner
from schemas import Options

pytestmark = pytest.mark.skipif(os.getenv("TEST_DOCKER") != "1", reason="Requires local Docker image")


def evaluate(root, **kwargs):
    return Runner(threading.Event(), time.monotonic() + 180).evaluate(root, Options(**kwargs).model_dump())


def test_docker_profile_and_ast(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIMIZER_RUNNER", "docker")
    tmp_path.chmod(0o755)
    (tmp_path / "main.cpp").write_text("""#include <cstdint>
#include <cstdio>
__attribute__((noinline)) std::uint64_t hot_loop(std::uint64_t seed) {
    for (int i=0; i<1000000; ++i) seed = (seed * 1664525 + 1013904223) % 1000000007;
    return seed;
}
int main() { std::printf("%llu\\n", (unsigned long long)hot_loop(42)); }
""")
    result = evaluate(tmp_path, mode="benchmark", profile=True, repeats=5)
    assert result["profile"]["available"], result["profile"]
    assert "hot_loop" in result["profile"]["report"]
    assert result["analysis"]["available"], result["analysis"]
    assert any("hot_loop" in symbol["name"] for symbol in result["analysis"]["symbols"])


def test_docker_runtime_restrictions(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIMIZER_RUNNER", "docker")
    monkeypatch.setenv("GROQ_API_KEY", "test-secret-never-passed-to-worker")
    tmp_path.chmod(0o755)
    (tmp_path / "main.cpp").write_text("""#include <unistd.h>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sys/socket.h>
#include <arpa/inet.h>
int main() {
    if (getuid() == 0 || getenv("GROQ_API_KEY")) return 2;
    if (std::ofstream("/should-not-write").good()) return 3;
    if (std::ofstream("/baseline/main.cpp", std::ios::app).good()) return 4;
    int sock = socket(AF_INET, SOCK_STREAM, 0);
    timeval timeout{1,0}; setsockopt(sock,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout));
    sockaddr_in addr{}; addr.sin_family=AF_INET; addr.sin_port=htons(443);
    inet_pton(AF_INET,"1.1.1.1",&addr.sin_addr);
    if (connect(sock,(sockaddr*)&addr,sizeof(addr)) == 0) return 5;
    close(sock);
    std::string memory,pids; std::ifstream("/sys/fs/cgroup/memory.max") >> memory;
    std::ifstream("/sys/fs/cgroup/pids.max") >> pids;
    if (memory != "1073741824" || pids != "128") return 6;
    std::cout << "restricted\\n";
}""")
    result = evaluate(
        tmp_path, mode="benchmark", profile=False, repeats=5, cases=[{"expected_stdout": "restricted\n"}]
    )
    assert result["executed"]


def test_docker_compile_only_never_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIMIZER_RUNNER", "docker")
    tmp_path.chmod(0o755)
    (tmp_path / "main.cpp").write_text("int main() { for (;;) {} }")
    result = evaluate(tmp_path, mode="compile")
    assert result["compiled"] and not result["executed"]
