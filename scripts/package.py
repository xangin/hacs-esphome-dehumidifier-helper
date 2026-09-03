"""Build a clean install ZIP and verify its contents against local sources."""

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "esphome_dehumidifier_helper"


def main() -> None:
    version = json.loads((COMPONENT / "manifest.json").read_text())["version"]
    output = ROOT / "dist" / f"esphome_dehumidifier_helper-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    files = [
        path for path in COMPONENT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
        and path.suffix != ".pyc" and path.name != ".DS_Store"
    ]
    files.extend(ROOT / name for name in ("README.md", "LICENSE", "VALIDATION.md", "CHANGELOG.md"))
    files.extend((ROOT / "docs").glob("*.md"))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for path in files:
            assert archive.read(path.relative_to(ROOT).as_posix()) == path.read_bytes()
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n")
    print(f"Verified {len(files)} files: {output}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
