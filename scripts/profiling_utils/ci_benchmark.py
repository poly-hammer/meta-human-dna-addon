"""
CI Benchmark Runner for MetaHuman DNA Addon.

This script is designed to run as part of a CI pipeline to:
1. Load a test DNA file
2. Run profiling benchmarks
3. Export results for comparison
4. Check for performance regressions

Usage:
    # Run benchmark and export results
    uv run python scripts/profiling_utils/ci_benchmark.py --iterations 50 --output reports/profiling

    # Compare with baseline
    uv run python scripts/profiling_utils/ci_benchmark.py --compare baseline.json current.json --threshold 15

Environment Variables:
    CI_DNA_FILE: Path to DNA file to load (default: tests/test_files/dna/ada/head.dna)
    CI_OUTPUT_DIR: Directory for output files (default: reports/profiling)
    CI_ITERATIONS: Number of benchmark iterations (default: 50)
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import sys

from pathlib import Path


# Setup paths
SCRIPT_DIR = Path(__file__).parent
ADDON_ROOT = SCRIPT_DIR.parent.parent
SRC_PATH = ADDON_ROOT / "src" / "addons"
SCRIPTS_PATH = ADDON_ROOT / "scripts"

# Determine platform-specific architecture
ARCH = "x64"
if "arm" in platform.processor().lower():
    ARCH = "arm64"
if sys.platform == "win32" and ARCH == "x64":
    ARCH = "amd64"
if sys.platform == "linux" and ARCH == "x64":
    ARCH = "x86_64"

OS_NAME = "windows"
if sys.platform == "darwin":
    OS_NAME = "mac"
elif sys.platform == "linux":
    OS_NAME = "linux"

# CI-specific paths for sibling repos (when checked out side-by-side in GitHub Actions)
BINDINGS_SOURCE_PATH = ADDON_ROOT.parent / "meta-human-dna-bindings"
CORE_SOURCE_PATH = ADDON_ROOT.parent / "meta-human-dna-core"
BINDINGS_DEST_PATH = ADDON_ROOT / "src" / "addons" / "meta_human_dna" / "bindings"

# Add riglogic bindings to path (platform-specific)
RIGLOGIC_BINDINGS_PATH = BINDINGS_SOURCE_PATH / OS_NAME / ARCH
if RIGLOGIC_BINDINGS_PATH.exists():
    sys.path.insert(0, str(RIGLOGIC_BINDINGS_PATH))

# Ensure riglogic module is available
if "riglogic" not in sys.modules:
    try:
        import riglogic

        sys.modules["riglogic"] = riglogic
    except ImportError:
        print(f"WARNING: Could not import riglogic from {RIGLOGIC_BINDINGS_PATH}")

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
if str(SCRIPTS_PATH) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_PATH))


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    # Find where Blender's args end (after --)
    # If running via Blender: blender --background --python script.py -- --iterations 5
    # If running directly: python script.py --iterations 5
    try:
        idx = sys.argv.index("--")
        args = sys.argv[idx + 1 :]
    except ValueError:
        # No -- separator, use all args after the script name
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(description="CI Benchmark Runner")
    parser.add_argument(
        "--iterations",
        type=int,
        default=int(os.environ.get("CI_ITERATIONS", "50")),
        help="Number of benchmark iterations",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=10,
        help="Number of warmup iterations",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=os.environ.get("CI_OUTPUT_DIR", "reports/profiling"),
        help="Output directory for results",
    )
    parser.add_argument(
        "--dna-file",
        type=str,
        default=os.environ.get("CI_DNA_FILE", "tests/test_files/dna/ada/head.dna"),
        help="Path to DNA file to benchmark",
    )
    parser.add_argument(
        "--import-shape-keys",
        action="store_true",
        default=False,
        help="Import shape keys after loading DNA (slower but enables shape key benchmarking)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv", "markdown", "all"],
        default="all",
        help="Export format",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASELINE", "CURRENT"),
        help="Compare two snapshot files for regressions",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=10.0,
        help="Regression threshold percentage",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit with error code if regression detected",
    )
    parser.add_argument(
        "--ignore-hardware-mismatch",
        action="store_true",
        help="Detect regressions even if hardware doesn't match (not recommended)",
    )

    return parser.parse_args(args)


def setup_environment() -> bool:
    """
    Set up the environment for running the benchmark.

    This mirrors the setup done in tests/conftest.py to ensure the addon
    is properly configured with bindings and registered with Blender.
    """
    import bpy

    print("Setting up benchmark environment...")

    # Copy bindings to destination if needed (mirrors conftest.py pytest_configure)
    bindings_specific_source = BINDINGS_SOURCE_PATH / OS_NAME / ARCH
    bindings_specific_dest = BINDINGS_DEST_PATH / OS_NAME / ARCH

    if not bindings_specific_dest.exists():
        if not bindings_specific_source.exists():
            print(f"  ✗ Bindings not found at {bindings_specific_source}")
            print("    Please ensure meta-human-dna-bindings is available.")
            return False

        print(f"  Copying bindings from {bindings_specific_source}...")
        shutil.copytree(src=bindings_specific_source, dst=bindings_specific_dest, dirs_exist_ok=True)

    # Copy core if running in CI and it exists
    core_dest = bindings_specific_dest / "meta_human_dna_core"
    if CORE_SOURCE_PATH.exists() and not core_dest.exists() and os.environ.get("RUNNING_CI"):
        print(f"  Copying core from {CORE_SOURCE_PATH}...")
        shutil.copytree(src=CORE_SOURCE_PATH, dst=core_dest, dirs_exist_ok=True)

    # Register the addon with Blender (mirrors tests/fixtures/addon.py)
    addon_name = "meta_human_dna"
    scripts_folder = ADDON_ROOT / "src"

    # Add script directory to Blender preferences
    script_directory = bpy.context.preferences.filepaths.script_directories.get(addon_name)
    if script_directory:
        bpy.context.preferences.filepaths.script_directories.remove(script_directory)

    script_directory = bpy.context.preferences.filepaths.script_directories.new()
    script_directory.name = addon_name
    script_directory.directory = str(scripts_folder)

    if str(scripts_folder) not in sys.path:
        sys.path.append(str(scripts_folder))

    # Enable the addon
    try:
        bpy.ops.preferences.addon_enable(module=addon_name)
        print(f"  ✓ Addon '{addon_name}' registered and enabled")
    except Exception as e:
        print(f"  ✗ Failed to enable addon: {e}")
        return False

    # Disable auto DNA backups for benchmarking performance
    try:
        bpy.context.preferences.addons[addon_name].preferences.enable_auto_dna_backups = False
        print("  ✓ Auto DNA backups disabled for benchmarking")
    except Exception:
        pass  # Preference may not exist

    return True


def load_dna_file(dna_path: str, import_shape_keys: bool = False) -> bool:
    """
    Load a DNA file into Blender.

    Args:
        dna_path: Path to the DNA file (relative to ADDON_ROOT).
        import_shape_keys: Whether to import shape keys after loading.

    Returns:
        True if successful, False otherwise.

    Note:
        Body evaluation requires a 'body.dna' file in the same directory as the head DNA.
        If no body.dna exists, body metrics will show as 0.000ms.
    """
    import bpy

    dna_path_resolved = Path(ADDON_ROOT) / dna_path
    dna_path_str = str(dna_path_resolved)

    if not dna_path_resolved.exists():
        print(f"ERROR: DNA file not found: {dna_path_str}")
        return False

    # Check if body.dna exists for body benchmarking
    body_dna_path = dna_path_resolved.parent / "body.dna"
    has_body = body_dna_path.exists()

    print(f"Loading DNA file: {dna_path_str}")
    if has_body:
        print(f"  Body DNA found: {body_dna_path}")
    else:
        print("  ⚠️  No body.dna found - body metrics will be zero")

    try:
        # Import the DNA file
        bpy.ops.meta_human_dna.import_dna(
            filepath=dna_path_str,
            include_body=True,
        )
        print("  ✓ DNA file loaded successfully")

        # Import shape keys if requested
        if import_shape_keys:
            print("  Importing shape keys (this may take a while)...")
            try:
                bpy.ops.meta_human_dna.import_shape_keys()
                print("  ✓ Shape keys imported successfully")
            except Exception as e:
                print(f"  ⚠️  Failed to import shape keys: {e}")
                # Don't fail the whole benchmark for shape key issues

        return True
    except Exception as e:
        print(f"  ✗ Failed to load DNA file: {e}")
        return False


def run_benchmark(args: argparse.Namespace) -> int:
    """Run the benchmark and export results."""
    from profiling_utils import run_profiler
    from profiling_utils.exporters import export_snapshot

    print("\n" + "=" * 60)
    print("CI BENCHMARK RUNNER")
    print("=" * 60)

    # Set up environment and register addon
    if not setup_environment():
        return 1

    # Load DNA file
    if not load_dna_file(args.dna_file, import_shape_keys=args.import_shape_keys):
        return 1

    # Run profiler
    print(f"\nRunning benchmark ({args.iterations} iterations, {args.warmup} warmup)...")
    results = run_profiler(
        iterations=args.iterations,
        warmup=args.warmup,
    )

    if results is None:
        print("ERROR: Profiler returned no results")
        return 1

    # Determine output paths
    # - Timestamped results go to the root output folder (e.g., reports/profiling/)
    # - Current snapshot goes to the "current" subfolder for easy comparison
    output_path = Path(ADDON_ROOT) / args.output
    root_output_path = output_path.parent if output_path.name == "current" else output_path
    current_folder = root_output_path / "current"

    # Export timestamped results to root output folder
    files = export_snapshot(
        results,
        root_output_path,
        output_format=args.format,
        iterations=args.iterations,
        warmup=args.warmup,
    )

    print(f"\nExported {len(files)} result files:")
    for f in files:
        print(f"  - {f}")

    # Clear the "current" folder and copy the latest results there
    if current_folder.exists():
        for old_file in current_folder.iterdir():
            old_file.unlink()
        print(f"\n  Cleared existing files in {current_folder}")
    else:
        current_folder.mkdir(parents=True, exist_ok=True)

    # Copy all exported files to current folder with standardized names
    for exported_file in files:
        current_file_path = current_folder / f"current{exported_file.suffix}"
        shutil.copy(exported_file, current_file_path)
        print(f"  Copied {exported_file.name} → {current_file_path.name}")

    # Output summary for CI logs
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY (for CI)")
    print("=" * 60)
    print(f"full_evaluation_mean_ms={results.full_evaluation.mean_ms:.3f}")
    print(f"full_evaluation_p95_ms={results.full_evaluation.p95_ms:.3f}")
    print(f"head_cpp_mean_ms={results.head_manager_calculate.mean_ms:.3f}")
    print(f"body_cpp_mean_ms={results.body_manager_calculate.mean_ms:.3f}")

    if results.full_evaluation.mean_ms > 0:
        fps = 1000 / results.full_evaluation.mean_ms
        print(f"theoretical_fps={fps:.1f}")

    return 0


def run_comparison(args: argparse.Namespace) -> int:
    """Compare two benchmark snapshots for regressions."""
    from profiling_utils.exporters import compare_snapshots

    print("\n" + "=" * 60)
    print("BENCHMARK COMPARISON")
    print("=" * 60)

    baseline_path = Path(args.compare[0])
    current_path = Path(args.compare[1])

    if not baseline_path.exists():
        print(f"ERROR: Baseline file not found: {baseline_path}")
        return 1

    if not current_path.exists():
        print(f"ERROR: Current file not found: {current_path}")
        return 1

    print(f"Baseline: {baseline_path}")
    print(f"Current:  {current_path}")
    print(f"Threshold: {args.threshold}%")
    print()

    comparison = compare_snapshots(
        baseline_path,
        current_path,
        args.threshold,
        require_matching_hardware=not args.ignore_hardware_mismatch,
    )

    print(f"Baseline commit: {comparison['baseline_commit']}")
    print(f"Current commit:  {comparison['current_commit']}")
    print()

    # Print hardware info
    print("Hardware Comparison:")
    print("-" * 60)
    baseline_hw = comparison.get("baseline_hardware", {})
    current_hw = comparison.get("current_hardware", {})
    print(
        f"  Baseline: {baseline_hw.get('cpu_name', 'unknown')}, "
        f"{baseline_hw.get('ram_total_gb', 0):.0f}GB RAM, "
        f"{baseline_hw.get('gpu_name', 'unknown')}"
    )
    print(
        f"  Current:  {current_hw.get('cpu_name', 'unknown')}, "
        f"{current_hw.get('ram_total_gb', 0):.0f}GB RAM, "
        f"{current_hw.get('gpu_name', 'unknown')}"
    )

    if comparison.get("hardware_matches"):
        print("  ✓ Hardware fingerprints match")
    else:
        print("  ⚠️  Hardware fingerprints DO NOT match")
        if comparison.get("hardware_mismatch_warning"):
            print(f"     {comparison['hardware_mismatch_warning']}")
    print()

    # Print comparisons
    print("Metric Comparisons:")
    print("-" * 60)
    for name, data in comparison["comparisons"].items():
        diff_str = f"{data['diff_pct']:+.1f}%"
        arrow = "↑" if data["diff_pct"] > 0 else "↓" if data["diff_pct"] < 0 else "→"
        print(f"  {name}: {data['baseline_ms']:.3f}ms → {data['current_ms']:.3f}ms ({diff_str} {arrow})")
    print()

    # Print regressions
    if comparison["regressions"]:
        print("⚠️  REGRESSIONS DETECTED:")
        for reg in comparison["regressions"]:
            print(f"  - {reg['name']}: +{reg['diff_pct']:.1f}%")
        print()

    # Print improvements
    if comparison["improvements"]:
        print("✓ Improvements:")
        for imp in comparison["improvements"]:
            print(f"  - {imp['name']}: {imp['diff_pct']:.1f}%")
        print()

    # Final result
    if comparison["has_regressions"]:
        print("=" * 60)
        print("RESULT: REGRESSIONS DETECTED")
        print("=" * 60)
        if args.fail_on_regression:
            return 1
    elif not comparison.get("hardware_matches"):
        print("=" * 60)
        print("RESULT: INCONCLUSIVE (hardware mismatch)")
        print("=" * 60)
    else:
        print("=" * 60)
        print("RESULT: NO REGRESSIONS")
        print("=" * 60)

    return 0


def main() -> int:
    """Main entry point."""
    args = parse_args()

    if args.compare:
        return run_comparison(args)
    return run_benchmark(args)


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
