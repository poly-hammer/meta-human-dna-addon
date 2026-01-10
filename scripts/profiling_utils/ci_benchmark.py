"""
CI Benchmark Runner for MetaHuman DNA Addon.

This script is designed to run as part of a CI pipeline to:
1. Load a test DNA file
2. Run profiling benchmarks
3. Export results for comparison
4. Check for performance regressions

Usage:
    # Run benchmark and export results
    blender --background --python ci_benchmark.py -- --iterations 50 --output reports/profiling

    # Compare with baseline
    blender --background --python ci_benchmark.py -- --compare baseline.json current.json --threshold 15

Environment Variables:
    CI_DNA_FILE: Path to DNA file to load (default: tests/test_files/dna/ada.dna)
    CI_OUTPUT_DIR: Directory for output files (default: reports/profiling)
    CI_ITERATIONS: Number of benchmark iterations (default: 50)
"""

from __future__ import annotations

import argparse
import os
import sys

from pathlib import Path


# Setup paths
SCRIPT_DIR = Path(__file__).parent
ADDON_ROOT = SCRIPT_DIR.parent.parent
SRC_PATH = ADDON_ROOT / "src" / "addons"
SCRIPTS_PATH = ADDON_ROOT / "scripts"

# CI-specific paths for sibling repos (when checked out side-by-side in GitHub Actions)
BINDINGS_PATH = ADDON_ROOT.parent / "meta-human-dna-bindings" / "src"
CORE_PATH = ADDON_ROOT.parent / "meta-human-dna-core" / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
if str(SCRIPTS_PATH) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_PATH))

# Add bindings and core paths if they exist (CI environment)
if BINDINGS_PATH.exists() and str(BINDINGS_PATH) not in sys.path:
    sys.path.insert(0, str(BINDINGS_PATH))
if CORE_PATH.exists() and str(CORE_PATH) not in sys.path:
    sys.path.insert(0, str(CORE_PATH))


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    # Find where Blender's args end (after --)
    try:
        idx = sys.argv.index("--")
        args = sys.argv[idx + 1 :]
    except ValueError:
        args = []

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
        default=os.environ.get("CI_DNA_FILE", "tests/test_files/dna/ada.dna"),
        help="Path to DNA file to benchmark",
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


def load_dna_file(dna_path: str) -> bool:
    """Load a DNA file into Blender."""
    import bpy

    dna_path = str(Path(ADDON_ROOT) / dna_path)

    if not Path(dna_path).exists():
        print(f"ERROR: DNA file not found: {dna_path}")
        return False

    print(f"Loading DNA file: {dna_path}")

    try:
        # Import the DNA file
        bpy.ops.meta_human_dna.import_dna(
            filepath=dna_path,
            include_body=True,
        )
        print("  ✓ DNA file loaded successfully")
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

    # Load DNA file
    if not load_dna_file(args.dna_file):
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

    # Export results
    output_path = Path(ADDON_ROOT) / args.output
    files = export_snapshot(
        results,
        output_path,
        format=args.format,
        iterations=args.iterations,
        warmup=args.warmup,
    )

    print(f"\nExported {len(files)} result files:")
    for f in files:
        print(f"  - {f}")

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
