"""Command runner for Infiapp repository tooling."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from repo_tools.common import AGENTS_DIR, REPO_ROOT, iter_agent_dirs


def run(command: Sequence[str], *, cwd: Path = REPO_ROOT, env: dict[str, str] | None = None) -> None:
    print(f"+ cwd={cwd} {' '.join(command)}", flush=True)
    subprocess.run(list(command), cwd=cwd, check=True, env=env)


def python_command(*args: str) -> list[str]:
    return [sys.executable, *args]


def npm_webui_command(*args: str) -> list[str]:
    return ["npm", "--prefix", "webUI", *args]


def title_from_app_name(app_name: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[-_\s]+", app_name) if part)


def env_prefix_from_app_name(app_name: str) -> str:
    prefix = re.sub(r"[^A-Za-z0-9]+", "_", app_name).strip("_").upper()
    if not prefix:
        raise ValueError("app name must contain at least one letter or number")
    if prefix[0].isdigit():
        prefix = f"APP_{prefix}"
    return prefix


def validate_app_name(app_name: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9-]*", app_name):
        raise ValueError(
            "app name must use lowercase letters, numbers, and hyphens, and start with a letter"
        )


def git_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [REPO_ROOT / rel_path for rel_path in result.stdout.splitlines()]


def rename_app(app_name: str, app_title: str | None = None) -> None:
    validate_app_name(app_name)
    title = app_title or title_from_app_name(app_name)
    env_prefix = env_prefix_from_app_name(app_name)

    changed: list[Path] = []
    for path in git_files():
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        updated = (
            text.replace("INFIAPP", env_prefix)
            .replace("Infiapp", title)
            .replace("infiapp", app_name)
        )
        if updated != text:
            path.write_text(updated)
            changed.append(path)

    print(f"Renamed starter app to {title} ({app_name}).")
    print(f"Updated {len(changed)} tracked text file(s).")


def validate_agents() -> None:
    print("==> Validating agent specs", flush=True)
    run(python_command("-m", "repo_tools.validate_agents"))


def validate_db() -> None:
    print("==> Validating DynamoDB specs", flush=True)
    run(python_command("-m", "repo_tools.validate_dynamodb"))


def codegen() -> None:
    print("==> Regenerating generated framework files", flush=True)
    run(python_command("-m", "repo_tools.codegen"))


def codegen_check() -> None:
    print("==> Checking generated framework files are current", flush=True)
    run(python_command("-m", "repo_tools.codegen", "--check"))


def test_agents() -> None:
    print("==> Running agent and shared utility tests", flush=True)
    run(python_command("-m", "unittest", "discover", "-s", "agents", "-p", "test_*.py"))


def typecheck_agents() -> None:
    print("==> Type checking shared utilities", flush=True)
    shared_utils_dir = AGENTS_DIR / "shared_utils"
    config_file = REPO_ROOT / "pyproject.toml"
    cache_dir = REPO_ROOT / ".mypy_cache"
    mypy_base_args = [
        "-m",
        "mypy",
        "--config-file",
        str(config_file),
        "--cache-dir",
        str(cache_dir),
    ]
    run(python_command(*mypy_base_args, "response.py", "generated"), cwd=shared_utils_dir)
    shared_utils_test_dir = shared_utils_dir / "test"
    if shared_utils_test_dir.exists():
        print("==> Type checking shared utility tests", flush=True)
        shared_utils_test_env = os.environ.copy()
        shared_utils_test_env["MYPYPATH"] = os.pathsep.join(
            [
                str(shared_utils_dir),
                shared_utils_test_env.get("MYPYPATH", ""),
            ]
        )
        run(python_command(*mypy_base_args, "."), cwd=shared_utils_test_dir, env=shared_utils_test_env)
    for agent_dir in iter_agent_dirs():
        print(f"==> Type checking agent code: {agent_dir.name}", flush=True)
        code_env = os.environ.copy()
        code_env["MYPYPATH"] = os.pathsep.join(
            [
                str(shared_utils_dir),
                code_env.get("MYPYPATH", ""),
            ]
        )
        run(python_command(*mypy_base_args, "."), cwd=agent_dir / "code", env=code_env)
        test_dir = agent_dir / "test"
        if test_dir.exists():
            print(f"==> Type checking agent tests: {agent_dir.name}", flush=True)
            test_env = os.environ.copy()
            test_env["MYPYPATH"] = os.pathsep.join(
                [
                    str(agent_dir / "code"),
                    str(shared_utils_dir),
                    test_env.get("MYPYPATH", ""),
                ]
            )
            run(python_command(*mypy_base_args, "."), cwd=test_dir, env=test_env)


def build_web() -> None:
    print("==> Building WebUI", flush=True)
    run(npm_webui_command("run", "build"))


def test_web_e2e() -> None:
    print("==> Running WebUI Playwright E2E and screenshot tests", flush=True)
    run(npm_webui_command("run", "test:e2e"))


COMMANDS = {
    "validate-agents": validate_agents,
    "validate-db": validate_db,
    "codegen": codegen,
    "codegen-check": codegen_check,
    "test-agents": test_agents,
    "typecheck-agents": typecheck_agents,
    "build-web": build_web,
    "test-web-e2e": test_web_e2e,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Infiapp repository tooling")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in sorted(COMMANDS):
        subparsers.add_parser(command)

    rename_parser = subparsers.add_parser("rename-app", help="Rename the starter app text across tracked files")
    rename_parser.add_argument("app_name", help="New app slug, such as my-app-name")
    rename_parser.add_argument("--title", help="Human-readable app title, defaults from app_name")

    args = parser.parse_args()

    if args.command == "rename-app":
        try:
            rename_app(args.app_name, args.title)
        except ValueError as exc:
            parser.error(str(exc))
    else:
        COMMANDS[args.command]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
