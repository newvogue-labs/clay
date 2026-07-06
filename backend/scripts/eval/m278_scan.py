"""M278 standalone scanner: analyse any text file for command flags.

Usage:
    python scripts/eval/m278_scan.py <file> [<file>...]
    python scripts/eval/m278_scan.py /tmp/summary_inject.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

from clay.scheduler.commands import CommandDetector


def scan_file(path: str) -> None:
    text = Path(path).read_text(encoding="utf-8")
    flags = CommandDetector().scan(text)
    name = Path(path).name

    if not flags:
        print(f"[{name}] 0 flags ✅")
        return

    print(f"[{name}] {len(flags)} flag(s):")
    for f in flags:
        ctx_start = max(0, f.span_start - 30)
        ctx_end = min(len(text), f.span_end + 30)
        ctx = text[ctx_start:ctx_end].replace("\n", "↵")
        marker = " " * (f.span_start - ctx_start) + "^" * (f.span_end - f.span_start)
        print(f"  {f.category:22s} {f.match!r}")
        print(f"  {'':22s} {ctx}")
        print(f"  {'':22s} {marker}")
        print()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for arg in sys.argv[1:]:
        scan_file(arg)


if __name__ == "__main__":
    main()
