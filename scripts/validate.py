"""Offline syntax, packaging, translation and deprecated-API checks.

This is not the official HA hassfest validator or a HA runtime test.
"""

import ast
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "esphome_dehumidifier_helper"


def flatten(value, prefix="") -> dict[str, str]:
    result = {}
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            result.update(flatten(child, path))
        elif isinstance(child, str):
            result[path] = child
        else:
            raise ValueError(f"Unexpected translation value: {path}")
    return result


def main() -> None:
    files = sorted(ROOT.rglob("*.py"))
    for path in files:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    constants = {
        node.target.id: ast.literal_eval(node.value)
        for node in ast.parse((COMPONENT / "const.py").read_text()).body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and isinstance(node.value, ast.Constant)
    }
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    required = {
        "domain": str, "name": str, "version": str, "codeowners": list,
        "documentation": str, "issue_tracker": str, "config_flow": bool,
        "dependencies": list, "requirements": list, "iot_class": str,
        "integration_type": str,
    }
    for key, expected in required.items():
        assert isinstance(manifest.get(key), expected), key
    assert manifest["domain"] == COMPONENT.name == constants["DOMAIN"]
    assert manifest["name"] == constants["NAME"]
    assert re.fullmatch(r"[a-z][a-z0-9_]*", manifest["domain"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "local_push"
    assert manifest["integration_type"] == "device"
    assert manifest["dependencies"] == ["esphome"]
    assert manifest["requirements"] == []
    assert manifest["codeowners"] and all(re.fullmatch(r"@[\w-]+", owner) for owner in manifest["codeowners"])
    repository = "https://github.com/xangin/hacs-esphome-dehumidifier-helper"
    assert manifest["documentation"] == repository
    assert manifest["issue_tracker"] == f"{repository}/issues"
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["name"] == manifest["name"]
    assert hacs["homeassistant"] == "2026.8.0"
    assert hacs["render_readme"] is True
    assert len(list((ROOT / "custom_components").iterdir())) == 1
    strings = flatten(json.loads((COMPONENT / "strings.json").read_text()))
    assert strings["title"] == manifest["name"]
    for language in ("en", "zh-Hant"):
        translated = flatten(json.loads((COMPONENT / "translations" / f"{language}.json").read_text()))
        assert translated.keys() == strings.keys(), f"Translation keys: {language}"
        for key, text in strings.items():
            assert set(re.findall(r"\{([^{}]+)\}", text)) == set(re.findall(r"\{([^{}]+)\}", translated[key])), (language, key)
    for path in COMPONENT.rglob("*.py"):
        code = path.read_text()
        forbidden = (
            r"\basync_track_state_change\s*\(", r"\basync_forward_entry_setup\s*\(",
            r"\bSUPPORT_MODES\b", r"\bDEVICE_CLASS_DEHUMIDIFIER\b",
            r"\basync_setup_platform\b", r"\bSCAN_INTERVAL\b", r"\bupdate_interval\b",
            r"self\.config_entry\s*=", r"\basync_track_time_interval\b",
        )
        for pattern in forbidden:
            assert not re.search(pattern, code), (path.name, pattern)
        for node in ast.walk(ast.parse(code)):
            if isinstance(node, ast.ImportFrom):
                assert "mqtt" not in (node.module or "")
    # Verify the shipped PNG signature/dimensions without imaging dependencies.
    icon = (COMPONENT / "brand" / "icon.png").read_bytes()
    assert icon[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", icon[16:24]) == (256, 256)
    print(f"PASS: compiled {len(files)} Python files; manifest/HACS fields; translations; API scan; icon")
    print("Official hassfest and HA runtime/hardware tests are separate release checks.")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, ValueError, KeyError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise
