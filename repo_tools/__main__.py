"""Command runner for Infiapp repository tooling."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from repo_tools.common import AGENTS_DIR, REPO_ROOT, iter_agent_dirs


def run(command: Sequence[str], *, cwd: Path = REPO_ROOT, env: dict[str, str] | None = None) -> None:
    subprocess.run(list(command), cwd=cwd, check=True, env=env)


def python_command(*args: str) -> list[str]:
    return [sys.executable, *args]


def npm_webui_command(*args: str) -> list[str]:
    return ["npm", "--prefix", "webUI", *args]


def validate() -> None:
    validate_agents()
    validate_db()


def validate_agents() -> None:
    run(python_command("-m", "repo_tools.validate_agents"))


def validate_db() -> None:
    run(python_command("-m", "repo_tools.validate_dynamodb"))


def codegen() -> None:
    run(python_command("-m", "repo_tools.codegen"))


def codegen_check() -> None:
    run(python_command("-m", "repo_tools.codegen", "--check"))


def test_agents() -> None:
    run(python_command("-m", "unittest", "discover", "-s", "agents", "-p", "test_*.py"))


def typecheck_agents() -> None:
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
        shared_utils_test_env = os.environ.copy()
        shared_utils_test_env["MYPYPATH"] = os.pathsep.join(
            [
                str(shared_utils_dir),
                shared_utils_test_env.get("MYPYPATH", ""),
            ]
        )
        run(python_command(*mypy_base_args, "."), cwd=shared_utils_test_dir, env=shared_utils_test_env)
    for agent_dir in iter_agent_dirs():
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
            test_env = os.environ.copy()
            test_env["MYPYPATH"] = os.pathsep.join(
                [
                    str(agent_dir / "code"),
                    str(shared_utils_dir),
                    test_env.get("MYPYPATH", ""),
                ]
            )
            run(python_command(*mypy_base_args, "."), cwd=test_dir, env=test_env)


def test_web() -> None:
    run(npm_webui_command("test"))


def build_web() -> None:
    run(npm_webui_command("run", "build"))


def test_web_e2e() -> None:
    run(npm_webui_command("run", "test:e2e"))


def check() -> None:
    validate()
    codegen_check()
    test_agents()
    typecheck_agents()
    test_web()
    build_web()


COMMANDS = {
    "validate": validate,
    "validate-agents": validate_agents,
    "validate-db": validate_db,
    "codegen": codegen,
    "codegen-check": codegen_check,
    "test-agents": test_agents,
    "typecheck-agents": typecheck_agents,
    "test-web": test_web,
    "build-web": build_web,
    "test-web-e2e": test_web_e2e,
    "check": check,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Infiapp repository tooling")
    parser.add_argument("command", choices=sorted(COMMANDS))
    args = parser.parse_args()

    COMMANDS[args.command]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
