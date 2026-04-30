from __future__ import annotations

import argparse
import sys

from src.recognition import champions_sprite_matcher


def _parse_species_ids(raw: str) -> set[int]:
    values: set[int] = set()
    for token in (raw or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            values.add(int(token))
        except Exception:
            continue
    return values


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download Pokemon Champions menu sprites from Bulbagarden Archives."
    )
    parser.add_argument(
        "--no-shiny",
        action="store_true",
        help="Download only normal sprites.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if local file exists.",
    )
    parser.add_argument(
        "--species-ids",
        default="",
        help="Optional comma-separated National Dex IDs (e.g. 25,94,130).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of files to save (for test runs).",
    )
    args = parser.parse_args()

    species_ids = _parse_species_ids(args.species_ids)
    result = champions_sprite_matcher.download_catalog(
        force=bool(args.force),
        include_shiny=not bool(args.no_shiny),
        species_ids=species_ids or None,
        limit=int(args.limit) if args.limit and args.limit > 0 else None,
    )

    print("saved_entries={}".format(result.get("saved_entries", 0)))
    print("added_entries={}".format(result.get("added_entries", 0)))
    print("cache_root={}".format(result.get("cache_root", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
