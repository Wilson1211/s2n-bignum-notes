#!/usr/bin/env python3
"""Build an inventory of the tactics documented in HOL Light's Help directory.

The Help directory also contains documentation for conversions, theorem rules,
parsers, and general utilities.  This script selects entries whose ``\\TYPE``
declaration has a top-level result type of exactly ``tactic`` instead of
guessing from the filename.  Thus a tactic consumer such as
``prove : term * tactic -> thm`` is not included.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Iterable


# These defaults let the script run without any command-line options.  Each
# output format gets its own filename beside this script.
DEFAULT_HELP_DIR = Path("/home/tong-nong/hol-light/Help")
DEFAULT_OUTPUT_STEMS = {
    "tsv": "help-tactics.tsv",
    "json": "help-tactics.json",
    "markdown": "help-tactics.md",
}

# A Help file starts its documented name with ``\DOC``.  The first pattern
# saves the text after that marker.  The second pattern finds the opening brace
# of the ``\TYPE`` field; ``extract_braced_type`` finds its matching close.
DOC_RE = re.compile(r"^\\DOC[ \t]+(.+?)[ \t]*$", re.MULTILINE)
TYPE_START_RE = re.compile(r"^\\TYPE[ \t]*\{", re.MULTILINE)


def parse_args() -> argparse.Namespace:
    # Describe the command and collect the three choices a user can change:
    # the Help directory, output destination, and output format.
    parser = argparse.ArgumentParser(
        description=(
            "List entries whose documented top-level result type is tactic. "
            "The default output is help-tactics.tsv beside this script."
        )
    )
    parser.add_argument(
        "--help-dir",
        type=Path,
        default=DEFAULT_HELP_DIR,
        help=f"HOL Light Help directory (default: {DEFAULT_HELP_DIR})",
    )
    parser.add_argument(
        "-o",
        "--output",
        help=(
            "output path, or '-' for standard output (default depends on "
            "--format and is beside this script)"
        ),
    )
    parser.add_argument(
        "--format",
        choices=("tsv", "json", "markdown"),
        default="tsv",
        help="output format (default: tsv)",
    )
    return parser.parse_args()


def extract_braced_type(text: str, source: Path) -> str:
    """Extract and whitespace-normalize the balanced braced \\TYPE field."""
    # Find where the type text begins, immediately after ``\TYPE {``.
    match = TYPE_START_RE.search(text)
    if not match:
        raise ValueError(f"{source}: missing braced \\TYPE field")

    start = match.end()
    depth = 1

    # Count nested braces until we reach the brace that closes ``\TYPE``.
    # This is safer than stopping at the first ``}``, because the type field
    # may itself contain braces.
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return " ".join(text[start:index].split())
    raise ValueError(f"{source}: unterminated \\TYPE field")


def returns_tactic(type_signature: str) -> bool:
    """Whether a type's top-level result is the exact HOL Light tactic alias."""
    # The text before ``:`` is the documented name.  The text after it is the
    # actual type expression whose final result we need to check.
    _, separator, result_type = type_signature.partition(":")
    if not separator:
        return False
    result_type = result_type.strip()

    # The boundary before "tactic" matters: thm_tactic and thm_tactical are
    # different HOL Light aliases.  Anchoring at the end rejects signatures
    # that merely accept a tactic, such as tactic -> goalstack.
    return bool(re.search(r"(?:^|->)\s*tactic\s*$", result_type))


def inventory(help_dir: Path) -> tuple[list[dict[str, str]], int]:
    # Stop early with a useful message if the input directory cannot be used.
    if not help_dir.is_dir():
        raise ValueError(f"Help directory does not exist or is not a directory: {help_dir}")

    # Sorting the files makes repeated runs produce the same stable result.
    files = sorted(help_dir.glob("*.hlp"), key=lambda path: path.name.casefold())
    if not files:
        raise ValueError(f"no .hlp files found in: {help_dir}")

    records: list[dict[str, str]] = []
    for path in files:
        # Read the documented name and type from one Help file.
        text = path.read_text(encoding="utf-8")
        doc_match = DOC_RE.search(text)
        if not doc_match:
            raise ValueError(f"{path}: missing \\DOC field")

        name = doc_match.group(1).strip()
        type_signature = extract_braced_type(text, path)

        # Keep only entries that return a tactic.  Other Help entries document
        # conversions, theorem rules, parsers, and general utilities.
        if not returns_tactic(type_signature):
            continue

        records.append(
            {
                "name": name,
                "type": type_signature,
                "help_file": path.name,
            }
        )

    # Present tactics alphabetically, with the original spelling as a stable
    # tie-breaker when two names differ only by letter case.
    records.sort(key=lambda record: (record["name"].casefold(), record["name"]))
    return records, len(files)


def render_tsv(records: Iterable[dict[str, str]]) -> str:
    # Use Python's CSV writer so tabs, quotes, and line endings are escaped in
    # a consistent way.
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=("name", "type", "help_file"),
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue()


def markdown_cell(value: str) -> str:
    # Escape characters that would otherwise break a Markdown table cell.
    return value.replace("\\", "\\\\").replace("|", "\\|")


def render_markdown(records: Iterable[dict[str, str]]) -> str:
    # Start the Markdown document with an explanation and a table header.
    lines = [
        "# HOL Light Help tactic inventory",
        "",
        "This list includes entries whose `\\TYPE` declaration has a top-level result type of exactly `tactic`.",
        "",
        "| Name | Type | Help file |",
        "|---|---|---|",
    ]

    # Add one table row for every tactic record.
    for record in records:
        cells = (record["name"], record["type"], record["help_file"])
        lines.append("| " + " | ".join(markdown_cell(cell) for cell in cells) + " |")
    return "\n".join(lines) + "\n"


def render(records: list[dict[str, str]], output_format: str) -> str:
    # Send all records to the renderer selected by ``--format``.
    if output_format == "tsv":
        return render_tsv(records)
    if output_format == "json":
        return json.dumps(records, indent=2, ensure_ascii=False) + "\n"
    return render_markdown(records)


def write_atomic(path: Path, content: str) -> None:
    # Make the destination directory when it does not already exist.
    path.parent.mkdir(parents=True, exist_ok=True)

    # Keep the permissions of an existing output file.  New files use normal
    # read/write permissions for the owner and read permissions for others.
    try:
        output_mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        output_mode = 0o644
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True
    )

    # Write to a temporary file first, then replace the destination in one
    # operation.  A failed run therefore cannot leave a half-written list.
    try:
        os.fchmod(descriptor, output_mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
            output.write(content)
        os.replace(temporary_name, path)
    except BaseException:
        # Remove the temporary file if writing or replacing fails.
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    # Parse the user's choices, build the inventory, and turn it into text.
    args = parse_args()
    try:
        records, files_scanned = inventory(args.help_dir.resolve())
        content = render(records, args.format)

        # ``-`` means print the list for another command to consume.  Otherwise
        # write either the requested path or the default file beside the script.
        if args.output == "-":
            sys.stdout.write(content)
            destination = "standard output"
        else:
            output_path = (
                Path(args.output).expanduser()
                if args.output
                else Path(__file__).resolve().parent / DEFAULT_OUTPUT_STEMS[args.format]
            )
            write_atomic(output_path.resolve(), content)
            destination = str(output_path.resolve())

        print(
            f"Scanned {files_scanned} Help files; wrote {len(records)} entries to {destination}",
            file=sys.stderr,
        )
        return 0
    except (OSError, UnicodeError, ValueError) as error:
        # Expected input and file errors become a short message and a nonzero
        # exit status instead of a long Python traceback.
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    # Return ``main``'s status code to the shell when this file is run directly.
    raise SystemExit(main())
