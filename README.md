# C++ Optimize Assistant

A local-first C/C++ optimization workbench. Upload a source file or ZIP project, run representative workloads, and download the preserved project with a diff and measurement report. Groq is optional: compilation and benchmarking work without an API key.

The optimizer keeps a change only after it builds, matches the original's outputs on every supplied workload, and passes repeated performance comparisons. It does not claim semantic equivalence for untested inputs, and it never promises a particular speedup.

## Start locally

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 22.12+ (or a supported newer Node version), and a Docker-compatible local engine. Linux and macOS are supported. Docker runs the compiler and uploaded programs; the API runs on the host.

```sh
uv sync --frozen
cp .env.example .env
docker build -f Dockerfile.runner -t cpp-optimizer-runner:local .
uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

If you already have an `.env`, keep it and add any missing settings instead of overwriting it. Set `GROQ_API_KEY` only to enable optimization. Keep your provider account on its **Free** plan; this application cannot enforce the account's billing settings.

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. The development server proxies `/api` to port 8000. For a single-server setup, run `npm run build` inside `frontend`, then restart the API; it serves the built UI at <http://localhost:8000>.

### Native mode for your own trusted code

If you have Clang installed and want to run without Docker, explicitly set `OPTIMIZER_RUNNER=native` in `.env`. Native mode has timeouts and output limits, but **is not a security sandbox**. It runs builds and programs with your local permissions. On macOS, install the Xcode command-line tools; CMake projects additionally need CMake and either Ninja or Make on PATH. Optional local libclang bindings improve symbol context; Callgrind profiling is normally available through the Linux Docker image.

The default Docker runner has no network, a read-only root, an unprivileged user, dropped capabilities, and bounded memory, CPU, processes, temporary storage, output, and execution time. API credentials are never passed to the execution worker. No container image is pulled automatically during a run.

For native AST indexing, install the optional bindings with `uv sync --extra ast`. AST diagnostics are included in reports; an unavailable index does not prevent compilation or output validation.

This is a **local application**, not a public multi-tenant execution service. Bind to loopback. Public hosting would require authentication, per-user isolation and quotas, a durable distributed queue, and additional sandbox hardening.

## Use the workbench

1. Upload one `.cpp`, `.cc`, `.cxx`, or `.c` file, or a ZIP containing sources, headers, and data. A single wrapper directory in a ZIP is removed automatically.
2. Select **Optimize and verify**, **Benchmark only**, or **Compile only**. Compile-only never executes code and never calls the model.
3. Supply deterministic workloads. Arguments, stdin, expected stdout/stderr, and output files can be configured through a project manifest or the UI's JSON overrides.
4. Watch progress, inspect every proposal, and download the project, `changes.diff`, and `report.json`. Unsuccessful optimization returns the unchanged original.

Try [examples/sum](examples/sum) for an optimization exercise, or [examples/cmake](examples/cmake) for a multi-file CMake project. Zip the contents of the example directory. The CMake example is deliberately tiny and is for functional validation, not a meaningful speedup claim.

### Project manifest

Add `optimizer.json` to the project root. UI overrides take precedence; the UI's selected mode takes precedence over the manifest mode.

```json
{
  "build": "simple",
  "standard": "c++17",
  "sources": ["src/main.cpp", "src/algorithm.cpp"],
  "include_dirs": ["include"],
  "working_dir": ".",
  "editable_files": ["src/algorithm.cpp"],
  "cases": [
    {"name": "edge", "args": ["0"], "expected_stdout": "0\n", "benchmark": false},
    {"name": "large", "args": ["1000000"], "stdin": "", "output_files": []}
  ],
  "attempts": 3,
  "repeats": 7,
  "min_improvement": 0.03,
  "run_timeout": 10,
  "profile": true
}
```

`simple` builds the listed translation units separately with `-O3`, using C17 for C and the selected standard for C++, then links them. Without `sources`, it discovers all source files. Specify the list if your project has multiple executable targets or test entry points.

For CMake use `"build": "cmake"`, a `cmake_target`, and `executable` relative to the generated build directory. The worker configures a clean Release build with `-O3 -DNDEBUG -g`, preserves the project's target definitions, and reads the resulting compilation database for AST context. Dependencies must be present locally/in the image; execution containers cannot download them. Other build systems and imported machine-specific compilation databases are not supported.

Output comparison is byte-for-byte: stdout, stderr, and declared output-file hashes must match on every run. Print actual results/checksums rather than timing logs; seed random generators. Every execution gets a fresh fixture directory. Use `benchmark: false` for fast edge-case correctness checks; at least one timed workload is required. This version does not apply floating-point tolerances or silently ignore output differences.

## Validate the “70% across 20+ benchmarks” claim

The repository contains **22 synthetic optimization exercises**, covering allocations, containers, search, strings, matrices, redundant work, and algorithm changes. They are a reproducible evaluation suite, not evidence that a historical résumé result happened or that all production programs improve similarly.

Every benchmark has an immutable driver, a separately editable kernel, four edge/small-input checks with independent Python oracles, and two timed workloads with different input sizes/seeds. Both original and candidate use the same compiler settings. Results include raw samples, diffs, correctness checks, and model usage.

Run all baselines with **zero model calls**:

```sh
uv run python benchmark_suite.py --mode benchmark --runner native --all --output benchmark-results/baselines
```

Use `--runner docker` after building the image if you prefer the isolated environment. For real optimization, run **one benchmark per invocation**:

```sh
uv run python benchmark_suite.py --mode optimize --runner native --next --output benchmark-results/optimized
```

Repeat the same command later to continue. Completed benchmarks are skipped. A 429/provider error saves the current benchmark as deferred and stops; the next invocation retries that benchmark. There is no automatic paid fallback, unbounded retry, or background schedule. The suite defaults to **one model attempt per benchmark**. `--attempts 2` is available, but use a separate output directory when changing experimental settings. `--all` remains sequential and stops at provider unavailability. `--benchmark vector_copy` targets one unfinished benchmark.

```sh
uv run python benchmark_suite.py --report-only --output benchmark-results/optimized
```

Each run saves `state.json`, `summary.json`, `results.csv`, and individual reports/project ZIPs. The runner locks its output directory and rejects incompatible settings or source-suite revisions on resume. Keep the machine idle; avoid concurrent benchmark suites.

The headline metric is the **arithmetic mean of per-benchmark runtime reductions**, where each benchmark's runtime is the sum of its timed-workload medians:

`reduction = 100 × (original_time − result_time) / original_time`

Unchanged results count as **0%**, not as excluded failures. Failed, deferred, and baseline-only benchmarks remain explicitly incomplete. The report only marks the 70% claim supported when all 22 optimization evaluations are complete and their mean reduction reaches 70%. It also reports geometric mean speedup; a 70% time reduction corresponds to about 3.33× speedup for an individual benchmark. Do not use a partial or winners-only average on your résumé.

## Model call and free-tier controls

The default stays `openai/gpt-oss-120b` on Groq:

| Setting | Default | Purpose |
|---|---|---|
| Reasoning effort | `medium` | Balanced starting point for source reasoning |
| Temperature | `0.2` | Limit unnecessary variation between proposals |
| Top-p | `1` | Avoid tuning two sampling controls together |
| Completion cap | `2048` | Bound visible output **and reasoning tokens** |
| Output | Strict JSON schema | Validated, exact-match edits |
| Streaming | Off | Groq structured outputs do not support streaming |
| SDK retries | `0` | Avoid hidden retry consumption |

These are practical starting values, not empirically proven optimal hyperparameters. Tune against the saved benchmark evidence. Environment variables in [.env.example](.env.example) allow low/medium/high reasoning, a 512–4096 token cap, and temperature 0–1. Truncated responses are rejected without applying partial edits. Reports record actual token usage, settings, latency, and rate-limit headers for successful calls.

Selected source context is bounded to 8 KB and the serialized context to 14 KB. Large files are represented by explicitly marked source windows selected using AST function ranges and profiling evidence, with nearby declarations and headers where space permits. When AST indexing is unavailable, bounded line windows provide a fallback. Recent failures can steer selection toward another function. This improves large-file coverage without sending the entire project or increasing the free-tier budget. Jobs stop after two unsuccessful proposals. Requests can still hit provider limits; account-specific limits take precedence over estimates. See [Groq rate limits](https://console.groq.com/docs/rate-limits), [structured outputs](https://console.groq.com/docs/structured-outputs), and [the model's reasoning settings](https://developers.openai.com/api/docs/models/gpt-oss-120b).

## Architecture and measurement

`UI → local job queue → isolated build/validation worker → bounded model proposal → source patch → validation → repeated comparison → report`

- AST indexing provides symbol identities and locations; it never reconstructs C++. Namespaces, overloads, headers, templates, and source boundaries remain intact.
- Callgrind optionally reports instruction-count hotspots for the first timed workload. Those are not wall-clock timings. Unsupported tools or profiling timeouts are reported explicitly.
- The worker uses a monotonic clock inside the execution environment. Container startup, compilation, and fixture copying are excluded; process startup and program I/O remain included.
- Warmups precede repeated measurements. Baseline/candidate order alternates. A paired bootstrap lower bound must clear the configured improvement threshold, and individual workloads must not show a regression beyond noise.
- Timed workloads under 5 ms are not eligible for accepted optimizations. Prefer workloads lasting at least 100 ms. Statistical checks reduce noise; they do not eliminate machine or workload bias.
- Accepted changes are rechecked against the original after the search. Failed final confirmation restores the original download.
- A single worker limits benchmark interference. Jobs and artifacts are kept locally, with cleanup on startup/new submission after 24 hours and a maximum of 20 retained jobs. Interrupted jobs are marked failed after restart.

API: `POST /api/jobs` (multipart `project`, JSON-string `options`), `GET /api/jobs/{id}`, `DELETE /api/jobs/{id}`, `GET /api/jobs/{id}/report`, and `GET /api/jobs/{id}/download`. Interactive API docs: <http://localhost:8000/docs>. Legacy synchronous upload routes return 410 with migration guidance.

## Verification

```sh
uv run ruff check .
uv run pytest -q
TEST_DOCKER=1 uv run pytest -q tests/test_docker.py tests/test_worker.py -k docker
cd frontend
npm run lint
npm run build
```

The Docker test requires the local image and running engine. CI builds the image and runs that test separately. Tests never call the live model. The suite CLI is the explicit way to run a live model evaluation.

For a project without the web UI:

```sh
uv run python cli.py examples/sum --mode benchmark --output sum-baseline.zip
```

## Independent LLVM workloads

The [LLVM adapter](benchmarks/llvm/README.md) adds five pinned C++ programs from LLVM's test suite, with verified source hashes and upstream reference outputs. They run under our validation harness using explicitly recorded smaller inputs. The `protected-main-v1` policy prevents model changes to their workload drivers and repetition loops. This is a selected subset, not a full upstream test-suite run. Their statistics stay separate from the 22 custom exercises.

```sh
uv run python benchmark_suite.py --suite llvm --mode benchmark --runner native --all --output benchmark-results/llvm-baselines
uv run python benchmark_suite.py --suite llvm --mode optimize --runner native --next --output benchmark-results/llvm-optimized
```

To publish a curated snapshot, including exact original/retained sources and their notices:

```sh
uv run python export_results.py benchmark-results/optimized docs/results/my-run
```

## Free Docker runtime on macOS

A Docker-compatible engine is needed; the CLI alone is insufficient. Colima is one free option:

```sh
brew install colima docker
colima start --profile cpp-optimizer --cpu 2 --memory 3 --vm-type vz --activate=false
export DOCKER_CONTEXT=colima-cpp-optimizer
docker build -f Dockerfile.runner -t cpp-optimizer-runner:local .
TEST_DOCKER=1 uv run pytest -q tests/test_docker.py tests/test_worker.py -k docker
```

Run the API with that environment, or set `DOCKER_CONTEXT=colima-cpp-optimizer` in your local `.env`. The dedicated profile avoids switching another project's default Docker context. Stop it when unused with `colima stop --profile cpp-optimizer`. Docker inputs are staged beneath the local job directory so macOS VM file sharing does not require exposing the system temporary directory.
