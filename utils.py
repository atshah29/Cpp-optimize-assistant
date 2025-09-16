import os, subprocess, time

def compile_and_run_project(filepaths, output_binary="project_bin"):
    try:
        subprocess.run(["g++", "-O2", "-std=c++17", *filepaths, "-o", output_binary], check=True, capture_output=True)
        start = time.time()
        subprocess.run([f"./{output_binary}"], check=True, capture_output=True)
        end = time.time()
        return end - start
    except subprocess.CalledProcessError as e:
        print("Compilation/Run failed:", e.stderr.decode())
        return None
    finally:
        if os.path.exists(output_binary):
            os.remove(output_binary)


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
