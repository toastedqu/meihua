"""Build a static site using the exact same Python engine and frontend."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
PYODIDE_VERSION = "314.0.7"
ENGINE_FILES = ("app/__init__.py", "app/engine.py", "app/data/classics.json")


def build(output: Path) -> None:
    archive = io.BytesIO()
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
        for name in ENGINE_FILES:
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            bundle.writestr(entry, (ROOT / name).read_bytes())
    content = archive.getvalue()
    digest = hashlib.sha256(content).hexdigest()[:16]
    static = output / "static"
    static.mkdir(parents=True, exist_ok=True)
    (static / "meihua-engine.zip").write_bytes(content)
    for name in ("app.js", "styles.css"):
        shutil.copyfile(ROOT / "app" / "static" / name, static / name)
    shutil.copyfile(ROOT / "web" / "pyodide-backend.js", static / "pyodide-backend.js")
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    marker = "<!-- STATIC_BACKEND -->"
    if html.count(marker) != 1:
        raise ValueError("Expected exactly one static-backend marker")
    html = html.replace(marker, '<script src="static/pyodide-backend.js" defer></script>')
    (output / "index.html").write_text(html, encoding="utf-8")
    (static / "runtime-manifest.json").write_text(
        json.dumps({"pyodide_version": PYODIDE_VERSION, "engine": f"meihua-engine.zip?v={digest}"}) + "\n",
        encoding="utf-8",
    )
    (output / ".nojekyll").touch()
    print(f"Static site: {output}; engine + classics: {len(content):,} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", "-o", type=Path, default=ROOT / "site")
    build(parser.parse_args().output.resolve())
