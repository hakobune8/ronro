"""Build an attributable Core wheel from a clean commit.

Usage: python scripts/build_core_wheel.py OUT_DIR [CLEAN_PYTHON]
The JSON sidecar records the exact Git source and wheel digest. No credential
or private evaluation artifact is included in the wheel.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> None:
    if len(sys.argv) not in {2, 3}:
        raise SystemExit("Usage: python scripts/build_core_wheel.py OUT_DIR [CLEAN_PYTHON]")
    if _git("status", "--porcelain", "--untracked-files=normal"):
        raise SystemExit("Core wheel requires a clean committed source tree")
    out_dir = Path(sys.argv[1]).absolute()
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit("Core wheel output directory must be empty")
    out_dir.mkdir(parents=True, exist_ok=True)
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    source_sha = _git("rev-parse", "HEAD")
    subprocess.run(["uv", "build", "--out-dir", str(out_dir)], cwd=ROOT, check=True)
    wheels = list(out_dir.glob(f"ronro_core-{version}-*.whl"))
    sdists = list(out_dir.glob(f"ronro_core-{version}.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit(f"Expected one Core wheel and sdist for {version}")
    wheel, sdist = wheels[0], sdists[0]
    if len(sys.argv) == 3:
        subprocess.run([sys.executable, str(ROOT / "scripts/verify_core_wheel.py"),
                        str(wheel), sys.argv[2], str(sdist)], cwd=ROOT, check=True)
    provenance = {
        "source_git_sha": source_sha,
        "project_version": version,
        "wheel_filename": wheel.name,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "sdist_filename": sdist.name,
        "sdist_sha256": hashlib.sha256(sdist.read_bytes()).hexdigest(),
    }
    (out_dir / "ronro-core-provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(json.dumps(provenance, sort_keys=True))


if __name__ == "__main__":
    main()
