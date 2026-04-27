"""Command runner for Infiapp repository tooling."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence

from repo_tools.common import REPO_ROOT


def run(command: Sequence[str]) -> None:
    subprocess.run(list(command), cwd=REPO_ROOT, check=True)


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


def test_web() -> None:
    run(npm_webui_command("test"))


def build_web() -> None:
    run(npm_webui_command("run", "build"))


def test_web_e2e() -> None:
    run(npm_webui_command("run", "test:e2e"))


def compile_python() -> None:
    run(python_command("-m", "compileall", "repo_tools", "agents"))


def check() -> None:
    validate()
    codegen_check()
    test_agents()
    test_web()
    build_web()


COMMANDS = {
    "validate": validate,
    "validate-agents": validate_agents,
    "validate-db": validate_db,
    "codegen": codegen,
    "codegen-check": codegen_check,
    "test-agents": test_agents,
    "test-web": test_web,
    "build-web": build_web,
    "test-web-e2e": test_web_e2e,
    "compile-python": compile_python,
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
