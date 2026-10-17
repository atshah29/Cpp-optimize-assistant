"""Select bounded source windows without discarding large translation units."""

from pathlib import Path
import re


def select_sources(files, allowed, analysis, profile, budget=8000, attempt=0):
    symbols = analysis.get("symbols", [])
    ranked = sorted(files, key=lambda name: (name not in allowed, Path(name).name not in profile, name))
    selected, windows = {}, {}
    for name in ranked:
        if budget < 200:
            break
        text = files[name]
        if len(text.encode()) <= budget:
            selected[name] = text
            windows[name] = {"complete": True, "ranges": [[1, len(text.splitlines())]]}
            budget -= len(text.encode())
            continue
        lines = text.splitlines(keepends=True)
        functions = [
            item
            for item in symbols
            if item["file"] == name
            and item.get("definition")
            and item["kind"] in {"FUNCTION_DECL", "CXX_METHOD", "FUNCTION_TEMPLATE", "CONSTRUCTOR"}
        ]
        functions.sort(key=lambda item: (item["name"].split("(")[0] not in profile, item["line"]))
        if functions:
            # Failed attempts can explore another function without increasing the token budget.
            pivot = attempt % len(functions)
            functions = functions[pivot:] + functions[:pivot]
        chunks, ranges, spent = [], [], 0
        limit = min(budget, 6000)

        def add(start, end, cap):
            nonlocal spent
            start, end = max(0, start), min(len(lines), end)
            if end <= start or any(start < b and end > a for a, b in ranges):
                return
            chunk, actual_end = "", start
            for line in lines[start:end]:
                if len((chunk + line).encode()) > cap - 100:
                    break
                chunk += line
                actual_end += 1
            if chunk:
                marked = f"// SOURCE EXCERPT: lines {start + 1}-{actual_end}\n{chunk}"
                addition = len(marked.encode()) + bool(chunks)
                if spent + addition <= limit:
                    chunks.append(marked)
                    ranges.append((start, actual_end))
                    spent += addition

        # Include local includes/type declarations when there is room for the hotspot too.
        first_function = min((item["line"] - 1 for item in functions), default=30)
        add(0, min(first_function, 40), min(1200, limit // 4))
        for item in functions:
            add(item["line"] - 1, item.get("end_line", item["line"] + 80), limit - spent)
            if spent > limit * 0.65:
                break
        if not functions:
            start = max(attempt * 80, ranges[-1][1] if ranges else 0)
            add(start, start + 160, limit - spent)
        # Add small project declarations/helpers referenced by the selected function.
        names = set(re.findall(r"\b[A-Za-z_]\w*\b", "".join(chunks)))
        for item in symbols:
            if item["file"] == name and item["name"].split("(")[0] in names:
                add(item["line"] - 1, item.get("end_line", item["line"]), limit - spent)
        if chunks:
            selected[name] = "\n".join(chunks)
            windows[name] = {"complete": False, "ranges": [[a + 1, b] for a, b in ranges]}
            budget -= len(selected[name].encode())
    return selected, windows
