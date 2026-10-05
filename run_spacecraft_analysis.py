#!/usr/bin/env python3
"""Run an opt-in, checksum-pinned spacecraft geometry/thermal analysis.

There are intentionally no default CAD, vehicle attitude, thermal properties,
or lunar albedo inputs. A missing flight configuration is a hard failure.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from science.errors import SciencePipelineError
from science.export import write_json
from science.spacecraft_analysis import analyze_spacecraft_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze a site ephemeris carrying validation records with user-supplied CAD "
            "and thermal boundary set. No synthetic flight defaults are used."
        )
    )
    parser.add_argument("--simulation", type=Path, required=True)
    parser.add_argument("--hardware", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Explicitly replace an existing analysis export",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = args.output.resolve()
    workspace = Path(__file__).resolve().parent
    reserved_files = {
        workspace / "outputs" / "simulation.json",
        workspace / "outputs" / "simulation.csv",
        workspace / "outputs" / "simulation-index.json",
    }
    if (
        output in reserved_files
        or output.is_relative_to(workspace / "outputs" / "candidates")
        or output.is_relative_to(workspace / "apps" / "web" / "public" / "data")
    ):
        print(
            "SPACECRAFT ANALYSIS FAILED: output cannot replace baseline planner data",
            file=sys.stderr,
        )
        return 2
    if output.exists() and not args.overwrite:
        print(
            f"SPACECRAFT ANALYSIS FAILED: output exists; use --overwrite: {output}",
            file=sys.stderr,
        )
        return 2
    try:
        result = analyze_spacecraft_files(
            args.simulation, args.hardware, output_path=output
        )
        write_json(result, output, overwrite=args.overwrite)
    except FileExistsError:
        print(
            f"SPACECRAFT ANALYSIS FAILED: output exists; use --overwrite: {output}",
            file=sys.stderr,
        )
        return 2
    except (SciencePipelineError, ValueError, OSError) as exc:
        print(f"SPACECRAFT ANALYSIS FAILED: {exc}", file=sys.stderr)
        return 2
    print(f"Analysis: {output}")
    print(f"Model: {result['model_id']} · {result['sample_count']} UTC epochs")
    print("Status: CONFIGURED_UNVALIDATED; NOT flight-certified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
