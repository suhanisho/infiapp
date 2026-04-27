"""Helpers for repository-wide Python dependency declarations."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from repo_tools.common import REPO_ROOT

PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
NAME_ONLY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
PINNED_REQUIREMENT_RE = re.compile(
    r"^([A-Za-z0-9_.-]+)(\[[A-Za-z0-9_.,-]+\])?==([^\s#]+)$"
)


def normalize_package_name(name: str) -> str:
    """Normalize package names using PEP 503-style rules."""
    return re.sub(r"[-_.]+", "-", name).lower()


def load_pyproject(path: Path = PYPROJECT_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{path.relative_to(REPO_ROOT)} not found")

    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path.relative_to(REPO_ROOT)} is not valid TOML: {exc}") from exc


def load_pinned_python_dependencies(path: Path = PYPROJECT_PATH) -> dict[str, str]:
    pyproject = load_pyproject(path)
    project = pyproject.get("project")
    if not isinstance(project, dict):
        raise ValueError(f"{path.relative_to(REPO_ROOT)} is missing a [project] table")

    dependencies = project.get("dependencies", [])
    if not isinstance(dependencies, list):
        raise ValueError(f"{path.relative_to(REPO_ROOT)} project.dependencies must be a list")

    pinned: dict[str, str] = {}
    for index, dependency in enumerate(dependencies):
        if not isinstance(dependency, str):
            raise ValueError(
                f"{path.relative_to(REPO_ROOT)} project.dependencies[{index}] must be a string"
            )

        match = PINNED_REQUIREMENT_RE.fullmatch(dependency)
        if not match:
            raise ValueError(
                f"{path.relative_to(REPO_ROOT)} project.dependencies[{index}] must pin an "
                f"exact version as 'package==version', got '{dependency}'"
            )

        normalized_name = normalize_package_name(match.group(1))
        if normalized_name in pinned:
            raise ValueError(
                f"{path.relative_to(REPO_ROOT)} duplicates dependency '{match.group(1)}'"
            )

        pinned[normalized_name] = dependency

    return pinned


def validate_dependency_names(
    dependency_names: object,
    *,
    pinned_dependencies: Mapping[str, str],
    label: str,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(dependency_names, list):
        return [f"{label} must be a list"]

    seen: set[str] = set()
    for index, dependency_name in enumerate(dependency_names):
        if not isinstance(dependency_name, str) or not dependency_name:
            errors.append(f"{label}[{index}] must be a non-empty string")
            continue

        if not NAME_ONLY_RE.fullmatch(dependency_name):
            errors.append(
                f"{label}[{index}] '{dependency_name}' must contain a dependency name only"
            )
            continue

        normalized_name = normalize_package_name(dependency_name)
        if normalized_name in seen:
            errors.append(f"{label}[{index}] duplicates '{dependency_name}'")
            continue

        seen.add(normalized_name)
        if normalized_name not in pinned_dependencies:
            errors.append(f"{label}[{index}] '{dependency_name}' is missing from pyproject.toml")

    return errors


def resolve_dependency_names(
    dependency_names: Sequence[str],
    pinned_dependencies: Mapping[str, str] | None = None,
) -> list[str]:
    pinned = pinned_dependencies or load_pinned_python_dependencies()
    resolved: list[str] = []
    seen: set[str] = set()
    missing: list[str] = []

    for dependency_name in dependency_names:
        normalized_name = normalize_package_name(dependency_name)
        pinned_requirement = pinned.get(normalized_name)
        if pinned_requirement is None:
            missing.append(dependency_name)
            continue
        if normalized_name not in seen:
            seen.add(normalized_name)
            resolved.append(pinned_requirement)

    if missing:
        raise ValueError(
            "Dependencies missing from pyproject.toml: " + ", ".join(sorted(set(missing)))
        )

    return resolved
