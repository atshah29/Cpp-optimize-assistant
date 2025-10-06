import os
import shutil
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

        # Copy include_dirs recursively into temp folder
        for inc_path in include_paths:
            if not os.path.exists(inc_path):
                raise HTTPException(status_code=400, detail=f"Include path not found: {inc_path}")
            # Copy entire folder contents into temp/include
            dest_inc = os.path.join(tmpdirname, "include")
            shutil.copytree(inc_path, os.path.join(dest_inc, os.path.basename(inc_path)), dirs_exist_ok=True)

        # Build clang args
        clang_args = [
            "-std=c++17",
            "-I/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/include/c++/v1",
            "-I/Library/Developer/CommandLineTools/usr/include/c++/v1",
            "-isysroot", "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk",
            f"-I{os.path.join(tmpdirname, 'include')}",  # Point to copied includes
        ]

        # Analyze and optimize
        results = analyze_cpp_project(filepaths, with_ai=True, clang_args=clang_args)

        if "ai_feedback" not in results:
            raise HTTPException(status_code=500, detail="AI feedback generation failed")

        final_json = results["ai_feedback"]["best_json"]
        cpp_file = json_to_cpp(final_json, filename="project_combined.cpp")

        # Optional: add comment
        with open(cpp_file, "a") as f:
            f.write("\n// Optimized by Aadesh")

        return FileResponse(
            cpp_file,
            media_type="text/x-c",
            filename="project_combined.cpp"
        )
