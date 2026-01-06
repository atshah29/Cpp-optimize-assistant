import os
import subprocess
import time

def compile_and_run_project(filepaths, run_args=None, clang_args=None, timeout=10, num_runs=5):
    """Compile and run C++ project multiple times, returning median execution time.
    
    Args:
        filepaths: List of C++ source files
        run_args: Arguments to pass to compiled program
        clang_args: Arguments to pass to compiler
        timeout: Maximum execution time in seconds per run
        num_runs: Number of times to run for statistical reliability (default: 5)
        
    Returns:
        float: Median execution time in seconds, or None if compilation/execution failed
    """
    cpp_files = [fp for fp in filepaths if fp.endswith(".cpp") or fp.endswith(".cc")]
    if not cpp_files:
        return None

    exe_path = "a.out"
    
    # Build compile command with custom clang args if provided
    compile_cmd = ["clang++", "-std=c++17", "-O2"]  # Add -O2 for fair comparison
    if clang_args:
        compile_cmd.extend(clang_args)
    compile_cmd.extend(cpp_files)
    compile_cmd.extend(["-o", exe_path])
    
    try:
        result = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True,
            timeout=30  # Compilation timeout
        )
        
        if result.returncode != 0:
            print(f"❌ Compilation failed:")
            print(f"   Command: {' '.join(compile_cmd)}")
            # Only show first 500 chars of error to avoid spam
            stderr = result.stderr[:500] + ("..." if len(result.stderr) > 500 else "")
            print(f"   Error: {stderr}")
            return None
        
        # Run multiple times to get reliable measurement
        times = []
        cmd = [f"./{exe_path}"] + (run_args or [])
        
        for i in range(num_runs):
            try:
                start = time.time()
                result = subprocess.run(
                    cmd, 
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                elapsed = time.time() - start
                
                if result.returncode != 0:
                    print(f"⚠️  Run {i+1}/{num_runs}: Program exited with code {result.returncode}")
                    if result.stdout:
                        print(f"   Output: {result.stdout[:200]}")
                    if result.stderr:
                        print(f"   Errors: {result.stderr[:200]}")
                    # Don't return None yet, maybe other runs succeed
                    continue
                
                times.append(elapsed)
                
            except subprocess.TimeoutExpired:
                print(f"⚠️  Run {i+1}/{num_runs}: Program timed out after {timeout} seconds")
                continue
        
        if not times:
            print(f"❌ All {num_runs} runs failed")
            return None
        
        if len(times) < num_runs:
            print(f"⚠️  Only {len(times)}/{num_runs} runs completed successfully")
        
        # Return median time (more robust than mean)
        times.sort()
        median = times[len(times) // 2]
        
        # Show statistics for transparency
        min_time = min(times)
        max_time = max(times)
        variance = ((max_time - min_time) / median * 100) if median > 0 else 0
        
        print(f"   Times: min={min_time:.6f}s, median={median:.6f}s, max={max_time:.6f}s (variance: {variance:.1f}%)")
        
        return median
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Execution failed: {e}")
        return None
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None
        
    finally:
        # Clean up executable
        if os.path.exists(exe_path):
            os.remove(exe_path)

def json_to_cpp(data: dict, filename: str = "optimized.cpp"):
    """Convert JSON structure back to C++ code with proper include handling.
    
    Args:
        data: Dictionary containing code structure (headers, functions, classes, etc.)
        filename: Output filename
        
    Returns:
        str: Path to generated file
    """
    parts = []
    
    # Handle headers with proper include syntax
    headers_seen = set()
    for header in data.get("headers", []):
        header = header.strip()
        
        # Skip duplicates
        if header in headers_seen:
            continue
        headers_seen.add(header)
        
        # If header already has include syntax, use it as-is
        if header.startswith("#include"):
            parts.append(header)
        # System headers (no extension or common system headers)
        elif not ("." in header) or header in ["iostream", "vector", "string", "map", 
                                                "set", "algorithm", "memory", "cmath",
                                                "cstring", "cstdlib", "cstdio", "queue",
                                                "unordered_map", "limits", "sstream",
                                                "utility", "inttypes"]:
            parts.append(f"#include <{header}>")
        # Local headers (has extension like .h, .hpp)
        else:
            parts.append(f'#include "{header}"')
    
    if parts:  # Add newline after headers if any exist
        parts.append("")
    
    # Add using namespace std (critical for most C++ code)
    parts.append("using namespace std;")
    parts.append("")
    
    # Add global variables (with duplicate detection)
    globals_seen = set()
    for global_var in data.get("globals", []):
        # Normalize to detect duplicates
        normalized = " ".join(global_var.split())
        if normalized in globals_seen:
            continue
        globals_seen.add(normalized)
        
        # Don't add semicolon if it already has one
        if global_var.endswith(';'):
            parts.append(global_var)
        else:
            parts.append(global_var + ";")
    
    if data.get("globals"):
        parts.append("")
    
    # Add diagnostics as comments (limit to avoid spam)
    diagnostics = data.get("diagnostics", [])[:10]  # Max 10 diagnostics
    for diagnostic in diagnostics:
        parts.append(f"// {diagnostic}")
    if diagnostics:
        parts.append("")
    
    # Add enums
    for enum_name, enum_def in data.get("enums", {}).items():
        if isinstance(enum_def, list):
            parts.append(f"enum {enum_name} {{ {', '.join(enum_def)} }};")
        elif isinstance(enum_def, str):
            parts.append(enum_def)
    if data.get("enums"):
        parts.append("")
    
    # Add classes
    for cls_name, cls in data.get("classes", {}).items():
        if isinstance(cls, dict) and "definition" in cls:
            parts.append(cls["definition"])
            parts.append("")
        elif isinstance(cls, str):
            # If AI returned class as string directly
            parts.append(cls)
            parts.append("")
    
    # Add functions (main last)
    functions = data.get("functions", {})
    for name, func in functions.items():
        if name != "main":
            parts.append(func)
            parts.append("")
    
    # Add main function last if it exists
    if "main" in functions:
        parts.append(functions["main"])
        parts.append("")
    
    code = "\n".join(parts).strip() + "\n"
    
    with open(filename, "w") as f:
        f.write(code)
    
    return filename