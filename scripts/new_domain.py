from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

SCHEMAS = """from pydantic import BaseModel


class __PASCAL__Request(BaseModel):
    message: str


class __PASCAL__Result(BaseModel):
    message: str
"""

SERVICE = """from app.modules.business.__NAME__.schemas import (
    __PASCAL__Request,
    __PASCAL__Result,
)


class __PASCAL__Service:
    async def handle(self, request: __PASCAL__Request) -> __PASCAL__Result:
        return __PASCAL__Result(message=request.message)
"""

ROUTER = """from fastapi import APIRouter, Depends, Request

from app.bootstrap.state import get_app_resources
from app.modules.business.__NAME__.schemas import (
    __PASCAL__Request,
    __PASCAL__Result,
)
from app.modules.business.__NAME__.service import __PASCAL__Service
from app.modules.platform.identity.auth import require_principal

router = APIRouter(
    prefix="/__DASHED__",
    tags=["__NAME__"],
    dependencies=[Depends(require_principal)],
)


@router.post("", response_model=__PASCAL__Result)
async def handle(payload: __PASCAL__Request, request: Request) -> __PASCAL__Result:
    service = get_app_resources(request.app).service(__PASCAL__Service)
    result = await service.handle(payload)
    return __PASCAL__Result.model_validate(result, from_attributes=True)
"""

FEATURE = """from app.api.v1.__NAME__.router import router as __NAME___router
from app.bootstrap.features.base import Feature
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.business.__NAME__.service import __PASCAL__Service


def build(resources: ApplicationResources, settings: Settings) -> __PASCAL__Service:
    return __PASCAL__Service()


def __NAME___feature() -> Feature:
    return Feature(
        name="__NAME__",
        service=__PASCAL__Service,
        build=build,
        routers=(__NAME___router,),
        enabled=lambda settings: settings.__UPPER___ENABLED,
    )
"""

CONFIG = """from pydantic import BaseModel


class __PASCAL__SettingsMixin(BaseModel):
    __UPPER___ENABLED: bool = False
"""

TEST = """from httpx import AsyncClient

from app.bootstrap.application import create_app
from tests.factories import api_client_for, build_test_settings

AUTH = {"Authorization": "Bearer test-token"}
URL = "/api/v1/__DASHED__"


async def _client(enabled: bool):
    settings = build_test_settings(__UPPER___ENABLED=enabled)
    return api_client_for(create_app(settings=settings))


async def test___NAME___echoes_message() -> None:
    async with await _client(True) as client:
        response = await client.post(URL, headers=AUTH, json={"message": "hi"})

    assert response.status_code == 200
    assert response.json() == {"message": "hi"}


async def test___NAME___requires_token() -> None:
    async with await _client(True) as client:
        response = await client.post(URL, json={"message": "hi"})

    assert response.status_code == 401


async def test___NAME___route_absent_when_disabled() -> None:
    async with await _client(False) as client:
        response = await client.post(URL, headers=AUTH, json={"message": "hi"})

    assert response.status_code == 404
"""


class ScaffoldError(Exception):
    pass


def render(template: str, name: str) -> str:
    pascal = "".join(part.capitalize() for part in name.split("_"))
    return (
        template.replace("__PASCAL__", pascal)
        .replace("__UPPER__", name.upper())
        .replace("__DASHED__", name.replace("_", "-"))
        .replace("__NAME__", name)
    )


def insert_after_last(text: str, pattern: str, line: str, anchor: str) -> str:
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    if not matches:
        raise ScaffoldError(f"anchor missing in {anchor}: {pattern}")
    end = matches[-1].end()
    return text[:end] + "\n" + line + text[end:]


def edit_registry(text: str, name: str) -> str:
    text = insert_after_last(
        text,
        r"^from app\.bootstrap\.features\.\w+ import \w+$",
        f"from app.bootstrap.features.{name} import {name}_feature",
        "registry.py",
    )
    match = re.search(
        r"(FEATURES: tuple\[Feature, \.\.\.\] = \()(.*?)(\))\s*\Z", text, re.DOTALL
    )
    if not match:
        raise ScaffoldError("anchor missing in registry.py: FEATURES tuple")
    body = match.group(2).rstrip().rstrip(",")
    return (
        text[: match.start()]
        + match.group(1)
        + f"{body}, {name}_feature()"
        + match.group(3)
        + "\n"
    )


def edit_settings(text: str, name: str, pascal: str) -> str:
    anchor_import = "from app.core.config.http import HttpSettingsMixin"
    anchor_base = "    PlatformSettingsMixin,\n"
    for anchor in (anchor_import, anchor_base):
        if text.count(anchor) != 1:
            raise ScaffoldError(f"anchor missing in config/__init__.py: {anchor!r}")
    text = text.replace(
        anchor_import,
        f"from app.core.config.{name} import {pascal}SettingsMixin\n{anchor_import}",
    )
    return text.replace(anchor_base, f"    {pascal}SettingsMixin,\n{anchor_base}")


def scaffold(name: str, root: Path) -> list[Path]:
    if not NAME_RE.match(name):
        raise ScaffoldError(f"invalid name {name!r}: use snake_case [a-z][a-z0-9_]*")
    domain_dir = root / "app" / "modules" / "business" / name
    if domain_dir.exists():
        raise ScaffoldError(f"{domain_dir.relative_to(root)} already exists")
    flag = f"{name.upper()}_ENABLED"
    config_dir = root / "app" / "core" / "config"
    for path in config_dir.glob("*.py"):
        if re.search(rf"\b{flag}\b", path.read_text()):
            raise ScaffoldError(f"{flag} is already a Settings field")

    pascal = "".join(part.capitalize() for part in name.split("_"))
    registry_path = root / "app" / "bootstrap" / "features" / "registry.py"
    settings_path = config_dir / "__init__.py"
    env_path = root / ".env.example"
    for path in (registry_path, settings_path, env_path):
        if not path.exists():
            raise ScaffoldError(f"missing {path.relative_to(root)}")

    new_files = {
        domain_dir / "__init__.py": "",
        domain_dir / "schemas.py": render(SCHEMAS, name),
        domain_dir / "service.py": render(SERVICE, name),
        root / "app" / "api" / "v1" / name / "__init__.py": "",
        root / "app" / "api" / "v1" / name / "router.py": render(ROUTER, name),
        root / "app" / "bootstrap" / "features" / f"{name}.py": render(FEATURE, name),
        config_dir / f"{name}.py": render(CONFIG, name),
        root / "tests" / "integration" / f"test_{name}.py": render(TEST, name),
    }
    for path in new_files:
        if path.exists():
            raise ScaffoldError(f"{path.relative_to(root)} already exists")

    env_text = env_path.read_text()
    if env_text and not env_text.endswith("\n"):
        env_text += "\n"
    edits = {
        registry_path: edit_registry(registry_path.read_text(), name),
        settings_path: edit_settings(settings_path.read_text(), name, pascal),
        env_path: env_text + f"{flag}=false\n",
    }

    for path, content in new_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    for path, content in edits.items():
        path.write_text(content)
    return [*new_files, *edits]


def run_ruff(root: Path, paths: list[Path]) -> None:
    targets = [str(p) for p in paths if p.suffix == ".py"]
    subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--fix", "--quiet", *targets],
        cwd=root,
        check=False,
    )
    subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--quiet", *targets],
        cwd=root,
        check=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.new_domain")
    parser.add_argument("name")
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()
    try:
        created = scaffold(args.name, root)
    except ScaffoldError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    run_ruff(root, created)
    for path in created:
        print(path.relative_to(root))
    print()
    print(f"1. Add stores and integrations under app/modules/business/{args.name}/.")
    print(f"2. Set {args.name.upper()}_ENABLED=true in .env.")
    print("3. Run make verify.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
