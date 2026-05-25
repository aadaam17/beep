#!/usr/bin/env python3
"""
Beep CLI Entry
- Launches the classic command shell or the Textual UI
"""

from __future__ import annotations

import sys

from app import run_command_shell, run_shell


def main(argv: list[str] | None = None) -> int:
    """Dispatch into the classic shell or the Textual shell UI."""

    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["shell"]:
        run_shell()
        return 0

    if not args:
        run_command_shell()
        return 0

    print("Start Beep first, then run commands inside it.")
    print("Use `python cli.py` for the classic command shell.")
    print("Use `python cli.py shell` for the Textual interactive app.")
    print(f"Ignoring direct argv command: {' '.join(args)}")
    run_command_shell()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
