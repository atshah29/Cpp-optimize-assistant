"""Optional AST indexing; source files remain the source of truth."""

from pathlib import Path
import json
import shlex

from utils import inside, source_files


def analyze_project(root: Path, build_dir: Path, standard: str, include_dirs: list[str]) -> dict:
    try:
        from clang import cindex

        index = cindex.Index.create()
    except Exception as exc:
        return {"available": False, "reason": f"libclang unavailable: {type(exc).__name__}", "symbols": []}
    commands = {}
    database = build_dir / "compile_commands.json"
    if database.exists():
        for entry in json.loads(database.read_text()):
            file = Path(entry["file"])
            if not file.is_absolute():
                file = Path(entry["directory"]) / file
            args = entry.get("arguments") or shlex.split(entry["command"])
            clean, skip = [], False
            for arg in args[1:]:
                if skip:
                    skip = False
                    continue
                if arg in {"-o", "-MF", "-MT", "-MQ"}:
                    skip = True
                elif arg not in {"-c", entry["file"], str(file)}:
                    clean.append(arg)
            commands[str(file.resolve())] = ["-working-directory", entry["directory"], *clean]
    symbols, diagnostics = [], []
    sources = source_files(root)
    for name in sources:
        if Path(name).suffix not in {".cpp", ".cc", ".cxx", ".c"}:
            continue
        path = inside(root, name)
        args = commands.get(
            str(path),
            [
                f"-std={'c17' if path.suffix == '.c' else standard}",
                f"-I{root}",
                *[f"-I{inside(root, inc)}" for inc in include_dirs],
            ],
        )
        try:
            unit = index.parse(str(path), args=args)
            diagnostics.extend(str(item) for item in unit.diagnostics)

            def visit(node):
                location = node.location.file
                if location and not Path(location.name).resolve().is_relative_to(root):
                    return
                if location and node.kind.is_declaration() and node.spelling and len(symbols) < 400:
                    symbols.append(
                        {
                            "id": node.get_usr(),
                            "name": node.displayname,
                            "kind": node.kind.name,
                            "file": Path(location.name).resolve().relative_to(root).as_posix(),
                            "line": node.location.line,
                            "end_line": node.extent.end.line,
                            "definition": node.is_definition(),
                        }
                    )
                if not node.kind.is_statement() and not node.kind.is_expression():
                    for child in node.get_children():
                        visit(child)

            visit(unit.cursor)
        except Exception as exc:
            diagnostics.append(f"{name}: {exc}")
    unique = {(item["file"], item["line"], item["id"]): item for item in symbols}
    return {"available": True, "symbols": list(unique.values()), "diagnostics": diagnostics[:30]}
