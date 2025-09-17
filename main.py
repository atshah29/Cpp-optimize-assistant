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
    include_dirs: str = Form("")  # optional, comma-separated include paths
):
    valid_exts = (".cpp", ".h", ".hpp")

    # Parse user-provided include paths
    include_paths = [p.strip() for p in include_dirs.split(",") if p.strip()]

    with tempfile.TemporaryDirectory() as tmpdirname:
        filepaths = []

        # Save uploaded files to temp directory
        for upload in files:
            if not upload.filename.endswith(valid_exts):
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type: {upload.filename}. Only .cpp, .h, .hpp allowed."
                )
            temp_path = os.path.join(tmpdirname, upload.filename)
            with open(temp_path, "wb") as f:
                f.write(await upload.read())
            filepaths.append(temp_path)

        # Dynamically build clang args
        clang_args = [
            "-std=c++17",
            "-I/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/include/c++/v1",
            "-I/Library/Developer/CommandLineTools/usr/include/c++/v1",
            "-isysroot", "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk"
        ]
        for p in include_paths:
            clang_args.append(f"-I{p}")

        # Optional: automatically include temp subdirectories (project-local headers)
        for root, dirs, _ in os.walk(tmpdirname):
            for d in dirs:
                clang_args.append(f"-I{os.path.join(root, d)}")

        # Analyze project
        results = analyze_cpp_project(filepaths, with_ai=True, clang_args=clang_args)

        # Convert AI JSON to C++ file
        final_json = results["ai_feedback"]["best_json"]
        # Save to persistent /tmp folder so FastAPI can return it
        output_file = os.path.join("/tmp", "project_combined.cpp")
        cpp_file = json_to_cpp(final_json, filename=output_file)

        # Optional: add a comment in the output file
        with open(cpp_file, "a") as f:
            f.write("\n// Optimized by Aadesh")

    # Return optimized file (file now persists outside TemporaryDirectory)
    return FileResponse(
        cpp_file,
        media_type="text/x-c",
        filename="project_combined.cpp"
    )
