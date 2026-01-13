"""Pre-commit hook to auto-bump and sync addon version across all version files.

This hook ensures that the version in:
- src/addons/<addon_name>/__init__.py (bl_info["version"])
- src/addons/<addon_name>/blender_manifest.toml
- pyproject.toml (at repo root)
- uv.lock (at repo root)

Are all in sync and auto-bumps the patch version when addon files are changed.

Usage:
    python check_addon_version.py <addon_name> [--watch <glob_pattern>...]

Example:
    python check_addon_version.py meta_human_dna --watch "src/addons/meta_human_dna/**/*.py"
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys

from pathlib import Path
from typing import NamedTuple


class Version(NamedTuple):
    """Semantic version representation."""

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def to_tuple_str(self) -> str:
        """Return version as Python tuple string, e.g., '(0, 5, 4)'."""
        return f"({self.major}, {self.minor}, {self.patch})"

    def bumped_patch(self) -> Version:
        """Return a new Version with the patch number incremented."""
        return Version(self.major, self.minor, self.patch + 1)

    @classmethod
    def from_string(cls, version_str: str) -> Version:
        """Parse version from string like '0.5.4'."""
        parts = version_str.strip().split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid version string: {version_str}")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))

    @classmethod
    def from_tuple_str(cls, tuple_str: str) -> Version:
        """Parse version from tuple string like '(0, 5, 4)'."""
        # Remove parentheses and split by comma
        clean = tuple_str.strip("() ")
        parts = [p.strip() for p in clean.split(",")]
        if len(parts) != 3:
            raise ValueError(f"Invalid version tuple: {tuple_str}")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))


def get_staged_files() -> list[Path]:
    """Get list of files staged for commit."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [Path(f) for f in result.stdout.strip().split("\n") if f]


def matches_any_pattern(file_path: Path, patterns: list[str]) -> bool:
    """Check if a file path matches any of the given glob patterns."""
    # Normalize path to use forward slashes for consistent matching
    path_str = str(file_path).replace("\\", "/")
    for pattern in patterns:
        # Normalize pattern too
        normalized_pattern = pattern.replace("\\", "/")
        if fnmatch.fnmatch(path_str, normalized_pattern):
            return True
    return False


def has_relevant_changes(
    staged_files: list[Path],
    watch_patterns: list[str],
    version_files: list[Path],
) -> bool:
    """Check if any staged files match watch patterns (excluding version files)."""
    version_file_names = {p.name for p in version_files}

    for file_path in staged_files:
        # Skip version files
        if file_path.name in version_file_names:
            continue

        # Check if file matches any watch pattern
        if matches_any_pattern(file_path, watch_patterns):
            return True

    return False


def read_version_from_init(file_path: Path) -> Version:
    """Read version from addon __init__.py bl_info dict."""
    content = file_path.read_text(encoding="utf-8")
    # Match: "version": (0, 5, 4),
    pattern = r'"version"\s*:\s*\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)'
    match = re.search(pattern, content)
    if not match:
        raise ValueError(f"Could not find version in {file_path}")
    return Version(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def read_version_from_toml(file_path: Path) -> Version:
    """Read version from a TOML file (blender_manifest.toml or pyproject.toml)."""
    content = file_path.read_text(encoding="utf-8")
    # Match: version = "0.5.4"
    pattern = r'^version\s*=\s*"(\d+\.\d+\.\d+)"'
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        raise ValueError(f"Could not find version in {file_path}")
    return Version.from_string(match.group(1))


def read_version_from_uv_lock(file_path: Path, package_name: str) -> Version | None:
    """Read version from uv.lock for a specific package.

    Returns None if the lock file doesn't exist or package not found.
    """
    if not file_path.exists():
        return None

    content = file_path.read_text(encoding="utf-8")

    # Match the package block: [[package]]\nname = "package-name"\nversion = "0.5.4"
    # Use a pattern that finds the package by name and extracts its version
    pattern = rf'\[\[package\]\]\s*\nname\s*=\s*"{re.escape(package_name)}"\s*\nversion\s*=\s*"(\d+\.\d+\.\d+)"'
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        return None
    return Version.from_string(match.group(1))


def read_version_from_version_py(file_path: Path) -> Version | None:
    """Read version from a version.py file with __version__ = "x.y.z".

    Returns None if the file doesn't exist or version not found.
    """
    if not file_path.exists():
        return None

    content = file_path.read_text(encoding="utf-8")
    # Match: __version__ = "0.5.4"
    pattern = r'^__version__\s*=\s*["\'](\d+\.\d+\.\d+)["\']'
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        return None
    return Version.from_string(match.group(1))


def write_version_to_init(file_path: Path, version: Version) -> None:
    """Write version to addon __init__.py bl_info dict."""
    content = file_path.read_text(encoding="utf-8")
    pattern = r'("version"\s*:\s*)\(\d+\s*,\s*\d+\s*,\s*\d+\)'
    replacement = rf"\g<1>{version.to_tuple_str()}"
    new_content = re.sub(pattern, replacement, content)
    # Preserve LF line endings
    file_path.write_text(new_content, encoding="utf-8", newline="\n")


def write_version_to_toml(file_path: Path, version: Version) -> None:
    """Write version to a TOML file."""
    content = file_path.read_text(encoding="utf-8")
    pattern = r'^(version\s*=\s*)"[\d.]+"'
    replacement = rf'\g<1>"{version}"'
    new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    # Preserve LF line endings
    file_path.write_text(new_content, encoding="utf-8", newline="\n")


def write_version_to_uv_lock(file_path: Path, package_name: str, version: Version) -> bool:
    """Write version to uv.lock for a specific package.

    Returns True if the file was updated, False if file doesn't exist or package not found.
    """
    if not file_path.exists():
        return False

    content = file_path.read_text(encoding="utf-8")

    # Match the package block and replace version
    pattern = rf'(\[\[package\]\]\s*\nname\s*=\s*"{re.escape(package_name)}"\s*\nversion\s*=\s*)"[\d.]+"'
    replacement = rf'\g<1>"{version}"'
    new_content, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)

    if count == 0:
        return False

    # Preserve LF line endings
    file_path.write_text(new_content, encoding="utf-8", newline="\n")
    return True


def write_version_to_version_py(file_path: Path, version: Version) -> bool:
    """Write version to a version.py file with __version__ = "x.y.z".

    Returns True if the file was updated, False if file doesn't exist.
    """
    if not file_path.exists():
        return False

    content = file_path.read_text(encoding="utf-8")
    pattern = r'^(__version__\s*=\s*)["\'][\d.]+["\']'
    replacement = rf'\g<1>"{version}"'
    new_content, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)

    if count == 0:
        return False

    # Preserve LF line endings
    file_path.write_text(new_content, encoding="utf-8", newline="\n")
    return True


def stage_file(file_path: Path) -> None:
    """Add a file to the git staging area."""
    subprocess.run(["git", "add", str(file_path)], check=True)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Auto-bump and sync addon version across version files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s meta_human_dna
  %(prog)s meta_human_dna --watch "src/addons/meta_human_dna/**/*.py"
  %(prog)s meta_human_dna --watch "src/addons/meta_human_dna/**/*.py" --watch "src/addons/meta_human_dna/**/*.toml"
        """,
    )
    parser.add_argument(
        "addon_name",
        help="Name of the addon (e.g., 'meta_human_dna')",
    )
    parser.add_argument(
        "--watch",
        action="append",
        dest="watch_patterns",
        default=[],
        metavar="PATTERN",
        help="Glob pattern for files that trigger version bump (can be specified multiple times)",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point for the pre-commit hook.

    Returns:
        0 if successful, 1 if there was an error.
    """
    args = parse_args()

    # Build paths based on addon name
    addon_base_path = Path("src/addons") / args.addon_name
    addon_init_path = addon_base_path / "__init__.py"
    blender_manifest_path = addon_base_path / "blender_manifest.toml"
    pyproject_path = Path("pyproject.toml")
    uv_lock_path = Path("uv.lock")

    # Core package paths (for meta_human_dna_core bindings)
    core_base_path = addon_base_path / "bindings" / "windows" / "amd64" / "meta_human_dna_core"
    core_pyproject_path = core_base_path / "pyproject.toml"
    core_uv_lock_path = core_base_path / "uv.lock"
    core_version_py_path = core_base_path / "src" / "meta_human_dna_core" / "version.py"
    core_package_name = "meta-human-dna-core"

    # Convert addon name to package name format (underscores to hyphens)
    package_name = args.addon_name.replace("_", "-") + "-addon"

    version_files = [addon_init_path, blender_manifest_path, pyproject_path]

    # Default watch patterns if none provided
    watch_patterns = args.watch_patterns or [f"src/addons/{args.addon_name}/**/*"]

    print(f"Addon: {args.addon_name}")
    print(f"Watch patterns: {watch_patterns}")

    # Get staged files
    staged_files = get_staged_files()
    if not staged_files:
        print("No staged files.")
        return 0

    # Check if version files exist
    missing_files = [p for p in version_files if not p.exists()]
    if missing_files:
        print("ERROR: One or more version files not found:")
        for p in missing_files:
            print(f"  - {p}")
        return 1

    # Read current versions from all files
    try:
        init_version = read_version_from_init(addon_init_path)
        manifest_version = read_version_from_toml(blender_manifest_path)
        pyproject_version = read_version_from_toml(pyproject_path)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1

    # Read uv.lock version if it exists
    uv_lock_version = read_version_from_uv_lock(uv_lock_path, package_name)

    # Read core package versions if they exist
    core_pyproject_version = None
    core_uv_lock_version = None
    core_version_py_version = None

    if core_pyproject_path.exists():
        try:
            core_pyproject_version = read_version_from_toml(core_pyproject_path)
        except ValueError:
            pass  # File exists but version not found

    core_uv_lock_version = read_version_from_uv_lock(core_uv_lock_path, core_package_name)
    core_version_py_version = read_version_from_version_py(core_version_py_path)

    print("Current versions:")
    print(f"  __init__.py:           {init_version}")
    print(f"  blender_manifest.toml: {manifest_version}")
    print(f"  pyproject.toml:        {pyproject_version}")
    if uv_lock_version:
        print(f"  uv.lock:               {uv_lock_version}")
    if core_pyproject_version:
        print(f"  core/pyproject.toml:   {core_pyproject_version}")
    if core_uv_lock_version:
        print(f"  core/uv.lock:          {core_uv_lock_version}")
    if core_version_py_version:
        print(f"  core/version.py:       {core_version_py_version}")

    # Check if relevant files have changed (matching watch patterns, excluding version files)
    relevant_changes = has_relevant_changes(staged_files, watch_patterns, version_files)

    # Determine if version files are already staged
    version_files_staged = any(str(f) in [str(p) for p in version_files] for f in staged_files)

    if relevant_changes and not version_files_staged:
        # Auto-bump patch version
        new_version = init_version.bumped_patch()
        print(f"\nRelevant files changed. Auto-bumping patch version: {init_version} -> {new_version}")

        # Update all version files
        write_version_to_init(addon_init_path, new_version)
        write_version_to_toml(blender_manifest_path, new_version)
        write_version_to_toml(pyproject_path, new_version)

        # Update uv.lock if it exists
        if write_version_to_uv_lock(uv_lock_path, package_name, new_version):
            print(f"  Updated uv.lock for package '{package_name}'")
            stage_file(uv_lock_path)

        # Update core package version files if they exist
        if core_pyproject_path.exists():
            write_version_to_toml(core_pyproject_path, new_version)
            print(f"  Updated core/pyproject.toml")
            stage_file(core_pyproject_path)

        if write_version_to_uv_lock(core_uv_lock_path, core_package_name, new_version):
            print(f"  Updated core/uv.lock for package '{core_package_name}'")
            stage_file(core_uv_lock_path)

        if write_version_to_version_py(core_version_py_path, new_version):
            print(f"  Updated core/version.py")
            stage_file(core_version_py_path)

        # Stage the updated version files
        for vf in version_files:
            stage_file(vf)

        print("Version files updated and staged.")
        return 0

    # Check if versions are in sync (include uv.lock and core package versions if they exist)
    all_versions = [init_version, manifest_version, pyproject_version]
    if uv_lock_version:
        all_versions.append(uv_lock_version)
    if core_pyproject_version:
        all_versions.append(core_pyproject_version)
    if core_uv_lock_version:
        all_versions.append(core_uv_lock_version)
    if core_version_py_version:
        all_versions.append(core_version_py_version)

    if len(set(all_versions)) > 1:
        print("\nERROR: Version mismatch detected!")
        print("All version files must have the same version.")
        print(f"  __init__.py:           {init_version}")
        print(f"  blender_manifest.toml: {manifest_version}")
        print(f"  pyproject.toml:        {pyproject_version}")
        if uv_lock_version:
            print(f"  uv.lock:               {uv_lock_version}")
        if core_pyproject_version:
            print(f"  core/pyproject.toml:   {core_pyproject_version}")
        if core_uv_lock_version:
            print(f"  core/uv.lock:          {core_uv_lock_version}")
        if core_version_py_version:
            print(f"  core/version.py:       {core_version_py_version}")
        print("\nPlease sync the versions manually or let this hook auto-bump by")
        print("unstaging the version files and committing your addon changes again.")
        return 1

    print("\nAll versions are in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
