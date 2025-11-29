import os, subprocess, time

def compile_and_run_project(filepaths, run_args=None):
    cpp_files = [fp for fp in filepaths if fp.endswith(".cpp") or fp.endswith(".cc")]
    if not cpp_files:
        return None

    exe_path = "a.out"
    try:
        subprocess.run(["clang++", "-std=c++17", *cpp_files, "-o", exe_path], check=True)
        start = time.time()

        cmd = [f"./{exe_path}"] + (run_args or [])
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

        return time.time() - start
    except subprocess.CalledProcessError:
        print("Compilation/Run failed")
        return None


def json_to_cpp(data: dict, filename: str = "optimized.cpp"):
    parts = []
    for header in data.get("headers", []):
        parts.append(f'#include "{header}"')    
    parts.append("")
    for diagnostic in data.get("diagnostics", []):
        parts.append(f"//{diagnostic}")
    parts.append("")
    for enum_name, enum_def in data.get("enums", {}).items():
        if isinstance(enum_def, list):
            parts.append(f"enum {enum_name} {{ {', '.join(enum_def)} }};")
        elif isinstance(enum_def, str):
            # Assume it's already a valid enum definition
            parts.append(enum_def)
    parts.append("")
    for _, cls in data.get("classes", {}).items():
        if "definition" in cls:
            parts.append(cls["definition"])
            parts.append("")
    functions = data.get("functions", {})
    for name, func in functions.items():
        if name != "main":
            parts.append(func)
            parts.append("")
    if "main" in functions:
        parts.append(functions["main"])
        parts.append("")
    code = "\n".join(parts).strip() + "\n"
    with open(filename, "w") as f:
        f.write(code)
    return filename
