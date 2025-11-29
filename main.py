import os
import tempfile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from analyze import analyze_cpp_project
from utils import json_to_cpp

app = FastAPI()

@app.post("/optimize")
async def optimize(
    files: list[UploadFile] = File(...),
    include_dirs: str = Form(""),       # comma-separated include paths
    program_args: str = Form("")        # <-- NEW: comma-separated runtime args
):
    valid_exts = (".cpp", ".h", ".hpp", ".cc")

    include_paths = [p.strip() for p in include_dirs.split(",") if p.strip()]
    run_args = [a.strip() for a in program_args.split(",") if a.strip()]  # <--

    for path in include_paths:
        if not os.path.exists(path):
            raise HTTPException(status_code=400, detail=f"Include path not found: {path}")

    with tempfile.TemporaryDirectory() as tmpdirname:
        filepaths = []
        for upload in files:
            if not upload.filename.endswith(valid_exts):
                raise HTTPException(status_code=400, detail=f"Unsupported file type: {upload.filename}")
            temp_path = os.path.join(tmpdirname, upload.filename)
            with open(temp_path, "wb") as f:
                f.write(await upload.read())
            filepaths.append(temp_path)

        clang_args = [
            "-std=c++17",
            "-I/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/include/c++/v1",
            "-I/Library/Developer/CommandLineTools/usr/include/c++/v1",
            "-isysroot", "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk",
        ]
        for inc in include_paths:
            clang_args.append(f"-I{inc}")

        print("DEBUG: Files =", filepaths)
        print("DEBUG: Clang args =", clang_args)
        print("DEBUG: Run args =", run_args)  # <--

        try:
            results = analyze_cpp_project(filepaths, with_ai=True, clang_args=clang_args, run_args=run_args)  # <--
        except Exception as e:
            import traceback
            print("ERROR during analysis:\n", traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Analyze failed: {str(e)}")

        if "ai_feedback" not in results:
            raise HTTPException(status_code=500, detail="AI feedback generation failed")

        final_json = results["ai_feedback"]["best_json"]
        cpp_file = json_to_cpp(final_json, filename="project_combined.cpp")

        with open(cpp_file, "a") as f:
            f.write("\n// Optimized by Aadesh")

        return FileResponse(cpp_file, media_type="text/x-c", filename="project_combined.cpp")

