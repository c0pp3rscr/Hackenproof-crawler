"""CLI entry point: crawl HackenProof programs into a sortable Excel workbook.

Usage:
    python src/main.py                       # crawl all programs -> hackenproof_programs.xlsx
    python src/main.py -o programs.xlsx      # custom output path
    python src/main.py --limit 20            # crawl only the first 20 (quick test)
    python src/main.py --workers 12          # tune concurrency
"""

from __future__ import annotations

import argparse
import sys
import time

from crawler import crawl, fetch_program_slugs, make_session
from excel import write_workbook


def _progress(done: int, total: int, item) -> None:
    label = getattr(item, "name", None) or (
        f"! {item.__class__.__name__}: {item}" if isinstance(item, Exception) else str(item)
    )
    bar_width = 30
    filled = int(bar_width * done / total) if total else bar_width
    bar = "#" * filled + "-" * (bar_width - filled)
    sys.stdout.write(f"\r[{bar}] {done}/{total}  {label[:40]:<40}")
    sys.stdout.flush()
    if done == total:
        sys.stdout.write("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Crawl HackenProof bug-bounty programs into an Excel sheet."
    )
    parser.add_argument(
        "-o", "--output", default="hackenproof_programs.xlsx",
        help="output .xlsx path (default: hackenproof_programs.xlsx)",
    )
    parser.add_argument(
        "-w", "--workers", type=int, default=8,
        help="number of concurrent fetch workers (default: 8)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="only crawl the first N programs (for a quick test run)",
    )
    args = parser.parse_args(argv)

    start = time.time()
    print("Fetching program list from sitemap ...")
    slugs = fetch_program_slugs(make_session())
    if args.limit:
        slugs = slugs[: args.limit]
    print(f"Found {len(slugs)} program(s). Crawling with {args.workers} workers ...")

    programs = crawl(slugs, workers=args.workers, on_progress=_progress)

    if not programs:
        print("No programs were parsed successfully. "
              "The site may be serving a Cloudflare challenge from this network.")
        return 1

    path = write_workbook(programs, args.output)
    elapsed = time.time() - start
    print(f"Wrote {len(programs)} programs to {path} in {elapsed:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
