"""Generate gRPC Python stubs from the vendored platform-core proto contract.

The proto module under ``proto/`` is a pinned copy of platform-core's contract
(ADR-0001: vendor + generate locally; platform-core never writes here). Generated
code lands under ``app/transport/grpc/_pb/`` and is committed so the service runs
without a toolchain.

The proto root package is ``platform.*`` (kept by decision), which collides with
Python's stdlib ``platform`` module. We avoid the shadow WITHOUT protoletariat by
rewriting the generated absolute imports (``from platform.x.v1 ...``) to the
vendored package root (``from app.transport.grpc._pb.platform.x.v1 ...``), so the
stubs live under a private subpackage and ``import platform`` (stdlib) is intact.

Run: ``uv run python -m scripts.gen_proto`` (or ``make proto``).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROTO_DIR = REPO / "proto"
OUT_DIR = REPO / "app" / "transport" / "grpc" / "_pb"
OUT_PKG = "app.transport.grpc._pb"


def main() -> int:
    protos = sorted(PROTO_DIR.rglob("*.proto"))
    if not protos:
        print(f"no .proto under {PROTO_DIR}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{PROTO_DIR}",
        f"--python_out={OUT_DIR}",
        f"--pyi_out={OUT_DIR}",
        f"--grpc_python_out={OUT_DIR}",
        *[str(p) for p in protos],
    ]
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        return result.returncode

    _rewrite_imports()
    _write_package_markers()
    print(f"✓ generated {len(protos)} proto file(s) -> {OUT_DIR.relative_to(REPO)}")
    return 0


def _rewrite_imports() -> None:
    """Root absolute proto imports at the vendored package (no stdlib shadow)."""
    for path in list(OUT_DIR.rglob("*.py")) + list(OUT_DIR.rglob("*.pyi")):
        text = path.read_text()
        fixed = text.replace("\nfrom platform.", f"\nfrom {OUT_PKG}.platform.")
        if fixed.startswith("from platform."):
            fixed = f"from {OUT_PKG}.platform." + fixed[len("from platform.") :]
        if fixed != text:
            path.write_text(fixed)


def _write_package_markers() -> None:
    for directory in [OUT_DIR, *[p for p in OUT_DIR.rglob("*") if p.is_dir()]]:
        (directory / "__init__.py").touch()


if __name__ == "__main__":
    raise SystemExit(main())
