"""CLI entry point for the Spec2RTL toolchain.

Usage:
    python -m spec2rtl --spec path/to/spec.pdf
    python -m spec2rtl --spec path/to/spec.pdf --config custom_config.yaml
    python -m spec2rtl --spec path/to/spec.pdf --compiler "Vitis HLS"
"""

import argparse
import sys
from pathlib import Path

from spec2rtl.pipeline import Spec2RTLPipeline


def main() -> int:
    """Parse CLI arguments and run the Spec2RTL pipeline.

    Returns:
        Exit code: 0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(
        prog="spec2rtl",
        description=(
            "Spec2RTL-Agent: Automated Specification-to-RTL Generation. "
            "Transforms hardware specification documents into synthesizable "
            "Register Transfer Level (RTL) code."
        ),
    )
    parser.add_argument(
        "--spec",
        type=Path,
        required=True,
        help="Path to the hardware specification document (PDF or text file).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=(
            "Path to a YAML configuration file. "
            "Uses built-in defaults if not provided."
        ),
    )
    parser.add_argument(
        "--compiler",
        type=str,
        default=None,
        help=(
            "Target HLS compiler (e.g., 'Google XLS', 'Vitis HLS'). "
            "Overrides the config file setting."
        ),
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Treat the --spec file as raw text instead of a PDF.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Treat the --spec file as a JSON specification object.",
    )

    args = parser.parse_args()

    if not args.spec.exists():
        print(f"Error: Specification file not found: {args.spec}", file=sys.stderr)
        return 1

    try:
        pipeline = Spec2RTLPipeline(config_path=args.config)

        if args.text:
            spec_text = args.spec.read_text(encoding="utf-8")
            result = pipeline.run_from_text(
                spec_text=spec_text,
                target_compiler=args.compiler,
            )
        elif args.json:
            import json as json_module
            spec_json = json_module.loads(args.spec.read_text(encoding="utf-8"))
            result = pipeline.run_from_json(
                spec_json=spec_json,
                target_compiler=args.compiler,
            )
        else:
            result = pipeline.run(
                spec_path=args.spec,
                target_compiler=args.compiler,
            )

        if result.success:
            print(f"\n🎉 Success! RTL output: {result.rtl_output_path}")
            return 0
        else:
            print(f"\n❌ Pipeline failed: {result.error_log}", file=sys.stderr)
            return 1

    except Exception as exc:
        print(f"\n❌ Pipeline critical failure: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
