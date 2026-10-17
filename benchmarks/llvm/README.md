# Pinned LLVM test-suite subset

This adapter uses five unmodified sources from LLVM's `SingleSource/Benchmarks/Shootout-C++` directory: **ary3, matrix, lists1, sieve, and heapsort**. The upstream README attributes these programs to the Programming Language Shootout. They are independent workloads, not programs written for this optimizer.

[manifest.json](manifest.json) pins revision `95569a773206d4ea96522bec400817478efa1511` and SHA-256 hashes for each source, reference output, build description, README, and license. The downloader validates HTTPS and hashes before using files. The cache is local and ignored by Git. Original program text and notices are preserved.

Each benchmark uses an explicitly selected smaller input and its upstream reference output, plus another input checked against the original program. The `exit 0` trailer is interpreted as the LLVM harness exit-status check, not literal stdout. The optimizer already requires exit code zero. Floating-point output is compared exactly in this subset; upstream's broader tolerance configuration is not imported.

This is **a selected subset evaluated using our own harness**, not a complete run of LLVM's test suite, nor an LLVM-endorsed score. Inputs, compiler configuration, and results must be reported alongside any performance claim. Keep results separate from the custom 22-case suite.

The `protected-main-v1` policy makes each complete `main` driver immutable. Proposals may optimize helper functions, but cannot delete benchmark repetitions, change input sizes, or replace printed results. `ary3` has no helper outside `main`, so under this conservative policy it can legitimately remain unchanged. An exploratory run without this guard was excluded after a model removed the matrix repetition loop; its results are not part of the published score. Use a fresh output directory when changing workload policy.

```sh
uv run python benchmark_suite.py --suite llvm --mode benchmark --runner native --all --output benchmark-results/llvm-baselines
uv run python benchmark_suite.py --suite llvm --mode optimize --runner native --next --output benchmark-results/llvm-optimized
```

The first invocation downloads only the pinned files. The same runner, correctness checks, model budget, and resumable state used by the custom suite apply here. Use `--runner docker` for an isolated Linux environment.

Sources: [LLVM test-suite guide](https://llvm.org/docs/TestSuiteGuide.html), [pinned upstream directory](https://github.com/llvm/llvm-test-suite/tree/95569a773206d4ea96522bec400817478efa1511/SingleSource/Benchmarks/Shootout-C%2B%2B).
