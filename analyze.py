import sys
import json
from clang import cindex
from feedback import get_ai_feedback  # Import from feedback.py

# Point Python to libclang
cindex.Config.set_library_file("/opt/homebrew/opt/llvm/lib/libclang.dylib")

headers = set()
functions = {}
diagnostics = []

def analyze_cpp_file(filepath, with_ai=False):
    index = cindex.Index.create()
    from clang.cindex import TranslationUnit

    tu = index.parse(
        filepath,
        args=[
            "-std=c++17",
            "-I/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/include/c++/v1",
            "-I/Library/Developer/CommandLineTools/usr/include/c++/v1",
            "-isysroot", "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk"
        ],
        options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
    )

    print(f"Analyzing {filepath}...\n")
    recursiveSearch(tu.cursor, filepath)

    # Diagnostics
    severity_map = {0: "Ignored", 1: "Note", 2: "Warning", 3: "Error", 4: "Fatal"}
    for element in tu.diagnostics:
        diagnostics.append(f"{severity_map[element.severity]}: {element.spelling} at {element.location}")

    results = {
        "headers": sorted(headers),
        "functions": functions,
        "diagnostics": diagnostics,
    }

    # Optionally add AI feedback directly into results
    if with_ai and functions:
        results["ai_feedback"] = {
            fname: get_ai_feedback(code)
            for fname, code in functions.items()
        }

    return results


def recursiveSearch(node, filepath):
    for child in node.get_children():
        if child.kind == cindex.CursorKind.INCLUSION_DIRECTIVE:
            headers.add(child.spelling)
        elif child.kind == cindex.CursorKind.FUNCTION_DECL:
            if child.location.file and child.location.file.name == filepath:
                with open(child.location.file.name) as f:
                    lines = f.readlines()
                    code = "".join(lines[child.extent.start.line - 1 : child.extent.end.line])
                    functions[child.spelling] = code.strip()
        recursiveSearch(child, filepath)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze.py file.cpp [--ai]")
        sys.exit(1)

    filepath = sys.argv[1]
    use_ai = "--ai" in sys.argv

    results = analyze_cpp_file(filepath, with_ai=use_ai)

    # Pretty print final results (including AI feedback if requested)
    print(json.dumps(results, indent=2))
