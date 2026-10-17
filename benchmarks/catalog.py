"""Fixed optimization exercises and independent small-input correctness oracles."""

from collections import Counter
import math

# id, category, nominal input size, repetitions within each timed process.
CATALOG = [
    ("vector_copy", "memory", 100000, 80),
    ("vector_growth", "allocation", 200000, 100),
    ("front_erase", "data structures", 20000, 12),
    ("linear_membership", "search", 30000, 20),
    ("duplicate_pairs", "algorithms", 10000, 8),
    ("map_histogram", "data structures", 100000, 12),
    ("sorted_insert", "algorithms", 20000, 15),
    ("repeated_sort", "redundant work", 20000, 8),
    ("range_sum", "algorithms", 100000, 20),
    ("sliding_window", "algorithms", 100000, 30),
    ("matrix_columns", "memory layout", 512, 40),
    ("matrix_transpose", "memory layout", 512, 30),
    ("matrix_multiply", "loop ordering", 128, 20),
    ("string_concat", "allocation", 20000, 20),
    ("string_search", "strings", 200000, 40),
    ("string_copy", "memory", 30000, 40),
    ("integer_format", "conversion", 20000, 20),
    ("polynomial", "arithmetic", 200000, 60),
    ("prime_count", "algorithms", 10000, 8),
    ("fibonacci", "algorithms", 28, 30),
    ("gcd_subtraction", "algorithms", 100000, 20),
    ("list_traversal", "data locality", 100000, 20),
]


def data(n, seed):
    result = []
    for _ in range(n):
        seed = (seed * 1664525 + 1013904223) & 0xFFFFFFFF
        result.append((seed >> 16) % 1000)
    return result


def oracle(name, n, seed):
    if not n:
        return 0
    values = data(n, seed)
    if name in {"vector_growth", "front_erase"}:
        return sum(values)
    if name == "vector_copy":
        return sum(values) * 16 + sum(i * (16 - i) for i in range(16))
    if name == "linear_membership":
        seen = set(values)
        return sum(item in seen for item in data(n, seed + 17))
    if name == "duplicate_pairs":
        return sum(count * (count - 1) // 2 for count in Counter(values).values())
    if name == "map_histogram":
        return sum((value + 1) * count * count for value, count in Counter(values).items())
    if name == "sorted_insert":
        return sum((i + 1) * value for i, value in enumerate(sorted(values)))
    if name == "repeated_sort":
        ordered = sorted(values)
        return sum(ordered[(seed + i) % n] for i in range(16))
    if name == "range_sum":
        total = 0
        for q in range(1000):
            a, b = sorted(((seed + q * 17) % n, (seed + q * 31) % n))
            total += sum(values[a : b + 1])
        return total
    if name == "sliding_window":
        width = min(n, 128)
        return sum(sum(values[i : i + width]) for i in range(n - width + 1))
    if name in {"matrix_columns", "matrix_transpose", "matrix_multiply"}:
        a = data(n * n, seed)
        if name == "matrix_columns":
            return sum(value * (i % n + 1) for i, value in enumerate(a))
        if name == "matrix_transpose":
            return sum(a[row * n + col] * ((col * n + row) % 97 + 1) for row in range(n) for col in range(n))
        b = data(n * n, seed + 17)
        return sum(a[i * n + k] * b[k * n + j] for i in range(n) for j in range(n) for k in range(n))
    if name == "string_concat":
        return sum((97 + value % 26) * (i % 17 + 1) for i, value in enumerate(values))
    if name == "string_search":
        text = "".join(chr(97 + value % 4) for value in values)
        return sum(text[i : i + 4] == "abcd" for i in range(max(0, n - 3)))
    if name == "string_copy":
        return sum(97 + value % 26 for value in values[::8])
    if name == "integer_format":
        return sum(ord(char) for value in values for char in str(value))
    if name == "polynomial":
        return sum((k + 1) * (value % 10) ** k for value in values for k in range(8))
    if name == "prime_count":
        return sum(
            value + seed % 7
            for value in range(2, n + 1)
            if all(value % div for div in range(2, math.isqrt(value) + 1))
        )
    if name == "fibonacci":
        a, b = 0, 1
        for _ in range(min(n, 40)):
            a, b = b, a + b
        return a + seed % 97
    if name == "gcd_subtraction":
        return sum(math.gcd(a + 1, b + 1) for a, b in zip(values, data(n, seed + 17)))
    if name == "list_traversal":
        return 16 * sum(values) + n * sum(range(16))
    raise ValueError(name)


def workloads(entry):
    name, _, n, rounds = entry
    larger = n + 1 if name == "fibonacci" else n + n // 2
    return [
        {
            "name": f"check-{size}-{seed}",
            "args": [str(size), "1", str(seed)],
            "expected_stdout": f"{oracle(name, size, seed)}\n",
            "benchmark": False,
        }
        for size, seed in [(0, 19), (1, 47), (8, 19), (17, 47)]
    ] + [
        {"name": "nominal", "args": [str(n), str(rounds), "1729"]},
        {"name": "larger", "args": [str(larger), str(rounds), "42"]},
    ]
