import argparse
import sys

from .validator import validate_file


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="etavalidator", description="Pre-flight check for ETA e-invoice JSON.")
    p.add_argument("files", nargs="+", help="JSON file(s): one document, a list, or {\"documents\": [...]}")
    p.add_argument("--lang", choices=["en", "ar"], default="en")
    p.add_argument("--tolerance", default="0.01", help="Allowed rounding difference in EGP (default 0.01)")
    p.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = p.parse_args(argv)

    worst = 0
    for f in args.files:
        issues = validate_file(f, tolerance=args.tolerance)
        errors = [i for i in issues if i.level == "error"]
        warns = [i for i in issues if i.level == "warning"]
        status = "FAIL" if errors or (args.strict and warns) else "OK"
        print(f"{f}: {status} ({len(errors)} error(s), {len(warns)} warning(s))")
        for i in issues:
            print(f"  [{i.level.upper()}] {i.path}: {i.message(args.lang)}")
        if errors or (args.strict and warns):
            worst = 1
    return worst


if __name__ == "__main__":
    sys.exit(main())
