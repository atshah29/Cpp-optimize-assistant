import os
import tempfile
import zipfile
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from analyze import analyze_cpp_project
from utils import json_to_cpp

app = FastAPI(
    title="C++ Optimizer API", 
    description="Optimize C++ projects using AI",
    version="2.0"
)


def process_project(project_root: Path, filepaths: list, include_paths: list, 
                   run_args: list, work_dir: str = None, skip_execution: bool = False,
                   timeout: int = 10):
    """Common processing logic for both upload methods."""
    if not filepaths:
        raise HTTPException(status_code=400, detail="No C++ source files found in upload")
    
    # Build clang arguments
    clang_args = [
        "-std=c++17",
        "-isysroot", "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk",
    ]
    
    # Add custom include paths
    for inc in include_paths:
        clang_args.append(f"-I{inc}")
    
    # Add project root and all subdirectories as include paths
    clang_args.append(f"-I{project_root}")
    for root, dirs, _ in os.walk(project_root):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', '__MACOSX']]
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            clang_args.append(f"-I{dir_path}")
    
    print(f"\n{'='*60}")
    print(f"🔧 Compiling {len(filepaths)} C++ file(s)")
    print(f"📂 Project root: {project_root}")
    if work_dir:
        print(f"📂 Working directory: {work_dir}")
    if run_args:
        print(f"⚙️  Runtime args: {', '.join(run_args)}")
    if skip_execution:
        print(f"⏭️  Execution: SKIPPED (compile-only mode)")
    print(f"⏱️  Timeout: {timeout}s")
    print(f"{'='*60}\n")
    
    # Determine execution directory
    execution_dir = project_root / work_dir if work_dir else project_root
    if not execution_dir.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Working directory '{work_dir}' not found in project"
        )
    
    # Change to execution directory
    original_dir = os.getcwd()
    os.chdir(execution_dir)
    
    try:
        results = analyze_cpp_project(
            filepaths,
            with_ai=True,
            clang_args=clang_args,
            run_args=run_args if not skip_execution else None,
            timeout=timeout
        )
        return results
    finally:
        os.chdir(original_dir)


@app.get("/")
async def root():
    """API information"""
    return {
        "name": "C++ Optimizer API",
        "version": "2.0",
        "endpoints": {
            "/optimize-zip": "Upload entire project as ZIP (recommended for full projects)",
            "/optimize-files": "Upload individual files (good for quick testing)",
            "/health": "Health check endpoint",
            "/docs": "Interactive API documentation"
        },
        "improvements": [
            "Better error handling and validation",
            "Duplicate declaration detection",
            "Correctness verification",
            "Configurable execution timeout",
            "Enhanced feedback with statistics"
        ]
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "version": "2.0"}


@app.post("/optimize-zip")
async def optimize_zip(
    project_zip: UploadFile = File(..., description="ZIP file containing your entire C++ project"),
    program_args: str = Form("", description="Comma-separated runtime arguments (e.g., 'data/input.txt')"),
    include_dirs: str = Form("", description="Comma-separated additional include directories"),
    working_dir: str = Form("", description="Subdirectory to run program from (leave empty for root)"),
    skip_execution: bool = Form(False, description="Skip running the program (compile-only mode, for interactive programs)"),
    timeout: int = Form(10, description="Execution timeout in seconds (default: 10)")
):
    """
    **Upload entire project as ZIP** (Recommended for full projects with data files)
    
    **Steps:**
    1. Zip your project: `zip -r project.zip .`
    2. Upload the ZIP
    3. Set program_args if needed (e.g., "data/input.txt")
    4. Check skip_execution for interactive programs that need user input
    5. Adjust timeout if your program needs more than 10 seconds
    
    **Returns:**
    - Optimized C++ file combining all sources
    - Includes performance statistics in output
    """

    if not project_zip.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")
    
    if timeout < 1 or timeout > 300:
        raise HTTPException(status_code=400, detail="Timeout must be between 1 and 300 seconds")
    
    include_paths = [p.strip() for p in include_dirs.split(",") if p.strip()]
    run_args = [a.strip() for a in program_args.split(",") if a.strip()]
    work_dir = working_dir.strip() if working_dir else None

    for path in include_paths:
        if not os.path.exists(path):
            raise HTTPException(status_code=400, detail=f"Include path not found: {path}")

    with tempfile.TemporaryDirectory() as tmpdirname:
        project_root = Path(tmpdirname)
        source_exts = (".cpp", ".cc", ".c", ".cxx")
        
        print(f"\n📦 Uploading project to: {tmpdirname}")
        print(f"📦 Extracting ZIP: {project_zip.filename}")
        
        # Save and extract ZIP
        zip_path = project_root / "upload.zip"
        with open(zip_path, "wb") as f:
            f.write(await project_zip.read())
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(project_root)
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid ZIP file")
        
        os.remove(zip_path)
        
        # Find all files
        filepaths = []
        all_files = []
        
        header_exts = (".h", ".hpp", ".hxx", ".hh", ".H")
        skip_files = ("Makefile", "CMakeLists.txt", "README", "LICENSE")
        
        for root, dirs, files_in_dir in os.walk(project_root):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', '__MACOSX']]
            
            for file in files_in_dir:
                if file.startswith('.') or file.startswith('._') or file in skip_files:
                    continue
                    
                file_path = Path(root) / file
                rel_path = file_path.relative_to(project_root)
                all_files.append(str(rel_path))
                
                if file.endswith(source_exts) and not file.endswith(header_exts):
                    filepaths.append(str(file_path))
                    print(f"  ✅ {rel_path} (will compile)")
                elif file.endswith(header_exts):
                    print(f"  📋 {rel_path} (header - will be available for #include)")
                else:
                    print(f"  📄 {rel_path}")
        
        if not filepaths:
            raise HTTPException(
                status_code=400,
                detail=f"No C++ source files found. Files in ZIP: {', '.join(all_files)}"
            )

        try:
            results = process_project(
                project_root, filepaths, include_paths, run_args, 
                work_dir, skip_execution, timeout
            )
        except Exception as e:
            import traceback
            print("ERROR during analysis:\n", traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

        if "ai_feedback" not in results:
            raise HTTPException(status_code=500, detail="AI optimization failed")

        final_json = results["ai_feedback"]["best_json"]
        cpp_file = json_to_cpp(final_json, filename="project_combined.cpp")

        # Add optimization metadata as comments
        with open(cpp_file, "a") as f:
            f.write("\n\n// ============================================\n")
            f.write("// Optimized by C++ AI Assistant v2.0\n")
            if results["ai_feedback"].get("baseline_time"):
                baseline = results["ai_feedback"]["baseline_time"]
                best = results["ai_feedback"]["best_time"]
                improvement = ((baseline - best) / baseline * 100) if baseline else 0
                f.write(f"// Baseline: {baseline:.6f}s\n")
                f.write(f"// Optimized: {best:.6f}s\n")
                f.write(f"// Improvement: {improvement:+.2f}%\n")
            f.write("// ============================================\n")

        print(f"\n✅ Optimization complete! Generated: {cpp_file}\n")
        return FileResponse(
            cpp_file, 
            media_type="text/x-c", 
            filename="project_combined.cpp",
            headers={"X-Optimization-Status": "success"}
        )


@app.post("/optimize-files")
async def optimize_files(
    cpp_files: list[UploadFile] = File(..., description="C++ source files (.cpp, .cc, .c)"),
    program_args: str = Form("", description="Comma-separated runtime arguments"),
    include_dirs: str = Form("", description="Comma-separated additional include directories"),
    skip_execution: bool = Form(False, description="Skip running the program (compile-only mode)"),
    timeout: int = Form(10, description="Execution timeout in seconds (default: 10)")
):
    """
    **Upload individual files** (Good for quick testing of single files)
    
    **Note:** This method is best for simple single-file programs.
    For projects with multiple files and dependencies, use /optimize-zip instead.
    """
    
    if timeout < 1 or timeout > 300:
        raise HTTPException(status_code=400, detail="Timeout must be between 1 and 300 seconds")
    
    source_exts = (".cpp", ".cc", ".c", ".cxx")
    
    include_paths = [p.strip() for p in include_dirs.split(",") if p.strip()]
    run_args = [a.strip() for a in program_args.split(",") if a.strip()]

    for path in include_paths:
        if not os.path.exists(path):
            raise HTTPException(status_code=400, detail=f"Include path not found: {path}")

    with tempfile.TemporaryDirectory() as tmpdirname:
        project_root = Path(tmpdirname)
        filepaths = []
        
        print(f"\n📦 Uploading files to: {tmpdirname}")
        
        for upload in cpp_files:
            if not upload.filename.endswith(source_exts):
                raise HTTPException(
                    status_code=400,
                    detail=f"File '{upload.filename}' must be a C++ source file (.cpp, .cc, .c, .cxx)"
                )
            
            file_path = project_root / upload.filename
            with open(file_path, "wb") as f:
                f.write(await upload.read())
            
            filepaths.append(str(file_path))
            print(f"  ✅ {upload.filename}")

        try:
            results = process_project(
                project_root, filepaths, include_paths, run_args, 
                None, skip_execution, timeout
            )
        except Exception as e:
            import traceback
            print("ERROR during analysis:\n", traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

        if "ai_feedback" not in results:
            raise HTTPException(status_code=500, detail="AI optimization failed")

        final_json = results["ai_feedback"]["best_json"]
        cpp_file = json_to_cpp(final_json, filename="project_combined.cpp")

        # Add optimization metadata
        with open(cpp_file, "a") as f:
            f.write("\n\n// ============================================\n")
            f.write("// Optimized by C++ AI Assistant v2.0\n")
            if results["ai_feedback"].get("baseline_time"):
                baseline = results["ai_feedback"]["baseline_time"]
                best = results["ai_feedback"]["best_time"]
                improvement = ((baseline - best) / baseline * 100) if baseline else 0
                f.write(f"// Baseline: {baseline:.6f}s\n")
                f.write(f"// Optimized: {best:.6f}s\n")
                f.write(f"// Improvement: {improvement:+.2f}%\n")
            f.write("// ============================================\n")

        print(f"\n✅ Optimization complete! Generated: {cpp_file}\n")
        return FileResponse(
            cpp_file, 
            media_type="text/x-c", 
            filename="project_combined.cpp",
            headers={"X-Optimization-Status": "success"}
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)