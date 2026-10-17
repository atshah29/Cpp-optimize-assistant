# Validation record — 17 October 2026

## Local setup

- Host: Apple M4, macOS arm64.
- Native compiler: Apple Clang 15.0.0, target `arm64-apple-darwin24.6.0`.
- Optimization: `-O3`; seven measurements after warmup, alternating baseline/candidate order.
- Model: Groq `openai/gpt-oss-120b`, medium reasoning, temperature 0.2, top-p 1, 2,048 completion-token cap, strict JSON, one proposal per benchmark.
- Calls stopped on rate limits and resumed after the cooldown. No paid fallback was used.
- The evaluation accumulated across development sessions on the same machine. Source-window selection was improved after the first benchmark; model parameters and benchmark inputs stayed fixed. Exact original/retained source snapshots are included to reproduce runtime comparisons independently of model generation.

## Completed synthetic evaluation

All 22 benchmarks completed. The arithmetic mean runtime reduction was **66.36%**, with **20 improved and 2 unchanged**. The measured result does **not** support a 70% average claim. The two unchanged cases remain in the denominator:

- Sliding window: the model's patch failed an independent small-input expected-output check.
- Polynomial evaluation: output checks passed, but performance did not clear the configured statistical threshold.

See [summary](results/2026-10-17-synthetic/summary.json), [per-benchmark CSV](results/2026-10-17-synthetic/results.csv), and [full evidence index](results/2026-10-17-synthetic/index.json). Each entry includes original source, retained source, proposal history, and raw measurements. These are deliberately chosen optimization exercises, not a random sample of production projects.

## Container and profiling validation

A dedicated free Colima 0.10.3 VM was used, with Docker context `colima-cpp-optimizer`. The tested runner image ID was:

`sha256:9b487acbe7dd5fdba36be80fc8a3b550c61d9055cf59d05826ecd3024cc93388`

The final local regression run passed **63 tests** with Docker enabled. It exercised:

- Non-root execution, network isolation, read-only root/input mounts, and enforced memory/process limits.
- Exclusion of the model API key from worker environments.
- Compile-only mode without executing an infinite-loop program.
- Callgrind instruction profiling with the expected hot function in its output.
- libclang AST indexing inside the image.
- CMake, upload/download round trips, cancellation checks, source-edit isolation, output validation, and benchmark acceptance rules.

An additional targeted Docker check confirmed C++23 selection works through the `c++2b` spelling supported by the image's compiler. A macOS VM mount-path defect found during testing was corrected by staging Docker inputs under the shared project job directory.

```sh
DOCKER_CONTEXT=colima-cpp-optimizer TEST_DOCKER=1 uv run pytest -q
```

Frontend lint/build and the local browser upload-to-report smoke test passed during implementation. GitHub Actions has been configured but has not been run remotely; that happens after pushing.

## Independent workloads

All five pinned LLVM Shootout C++ baselines passed their upstream reference-output checks. The adapter uses unmodified upstream sources and explicitly recorded smaller input sizes. The LLVM subset's optimization results are recorded separately from the custom suite. See the [adapter provenance](../benchmarks/llvm/README.md).

An initial exploratory LLVM run exposed a benchmark-integrity problem: the model removed the matrix program's repetition loop while preserving its output. Those exploratory results are **excluded**. The published evaluation uses `protected-main-v1`, which makes each entire main function immutable, preserving input generation, repetitions, and output code. Proposals that alter those drivers are rejected even if their output matches. This also means the array benchmark, whose work lives entirely in main, remains an unchanged case rather than being dropped from the denominator.

The guarded run completed **all five workloads**, with **21.64% mean runtime reduction**, **three retained improvements and two unchanged cases**. See the [LLVM summary](results/2026-10-17-llvm/summary.json), [CSV](results/2026-10-17-llvm/results.csv), and [evidence index](results/2026-10-17-llvm/index.json). These numbers are deliberately separate from the custom suite's 66.36%; neither suite is selectively filtered to retain only successful changes.

No result here establishes correctness for every possible input or a speedup on every C++ project. Percentages describe whole-program execution for the documented inputs, including process startup and I/O but excluding compilation and fixture preparation.
