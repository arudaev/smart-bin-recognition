#!/usr/bin/env python3
"""Validate the taxonomy, every region pack, and locale coverage.

Runs in CI. A failure here is a build failure – a half-translated safety
instruction or a region pack citing nothing is worse than shipping neither.

    python ml/scripts/validate_taxonomy.py
    python ml/scripts/validate_taxonomy.py --locales en de uk ru tr ar es fr hi
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sbr.taxonomy import (  # noqa: E402
    REPO_ROOT,
    load_all_region_packs,
    load_taxonomy,
)

LOCALES_DIR = REPO_ROOT / "web" / "src" / "i18n"

LAUNCH_LOCALES = ["en", "de", "uk", "ru", "tr", "ar", "es", "fr", "hi"]


def check_locales(taxonomy, locales: list[str]) -> list[str]:
    """Every item, stream, form factor and family must resolve in every locale."""
    problems: list[str] = []

    required = (
        {f"item.{item}" for item in taxonomy.items}
        | {stream.i18n_key for stream in taxonomy.streams.values()}
        | {s.note_key for s in taxonomy.streams.values() if s.note_key}
        | {form.i18n_key for form in taxonomy.form_factors.values()}
    )

    for locale in locales:
        path = LOCALES_DIR / f"{locale}.json"
        if not path.exists():
            problems.append(f"locale {locale!r}: bundle not found at {path}")
            continue

        bundle = json.loads(path.read_text(encoding="utf-8"))
        missing = sorted(key for key in required if key not in bundle)
        if missing:
            head = ", ".join(missing[:8])
            suffix = f" (+{len(missing) - 8} more)" if len(missing) > 8 else ""
            problems.append(f"locale {locale!r}: {len(missing)} missing keys: {head}{suffix}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locales", nargs="*", default=LAUNCH_LOCALES)
    parser.add_argument(
        "--skip-locales",
        action="store_true",
        help="Skip locale coverage – for use before web/ exists.",
    )
    args = parser.parse_args()

    problems: list[str] = []

    taxonomy = load_taxonomy()
    problems += taxonomy.validate()
    print(
        f"taxonomy v{taxonomy.version}: "
        f"{len(taxonomy.streams)} streams, "
        f"{len(taxonomy.form_factors)} form factors, "
        f"{len(taxonomy.items)} items"
    )

    packs = load_all_region_packs()
    for region_id, pack in packs.items():
        pack_problems = pack.validate(taxonomy)
        problems += pack_problems
        flag = "OK " if not pack_problems else "FAIL"
        publishable = "publishable" if pack.is_publishable else "NOT publishable"
        print(
            f"  [{flag}] {region_id} v{pack.pack_version} "
            f"({pack.status}, {len(pack.rules)} rules, {publishable})"
        )

    if not args.skip_locales:
        problems += check_locales(taxonomy, args.locales)
    else:
        print("  (locale coverage skipped)")

    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
