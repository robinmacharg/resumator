#!/usr/bin/env python3
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


def normalize_markdown(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    normalized: list[str] = []
    blank_count = 0

    for line in lines:
        stripped_trailing = line.rstrip()
        if stripped_trailing == "":
            blank_count += 1
            if blank_count <= 2:
                normalized.append("")
            continue

        blank_count = 0
        normalized.append(stripped_trailing)

    while normalized and normalized[-1] == "":
        normalized.pop()

    return "\n".join(normalized)


def ensure_heading(text: str, heading: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith("#"):
        return text

    return f"# {heading}\n\n{text}" if text else f"# {heading}\n"


def compile_pdf(markdown_file: Path, output_pdf: Path) -> None:
    if not shutil.which("pandoc"):
        raise RuntimeError("pandoc is required to generate research PDF")

    cmd = ["pandoc", str(markdown_file), "-o", str(output_pdf)]
    if shutil.which("typst"):
        cmd.append("--pdf-engine=typst")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        message = stderr or stdout or "unknown pandoc failure"
        raise RuntimeError(f"PDF generation failed: {message}")


def run(input_md: Path, output_md: Path, output_pdf: Path, heading: str) -> int:
    if not input_md.exists():
        print(f"Input markdown not found: {input_md}")
        return 1

    source_text = input_md.read_text(encoding="utf-8")
    if not source_text.strip():
        print("Input markdown is empty. Run research first.")
        return 1

    processed = normalize_markdown(source_text)
    processed = ensure_heading(processed, heading)

    # Avoid accidental markdown horizontal-rules from standalone --- separators.
    processed = re.sub(r"(?m)^---+$", "", processed)
    processed = normalize_markdown(processed)

    output_md.write_text(processed + "\n", encoding="utf-8")
    print(f"Wrote formatted markdown: {output_md}")

    try:
        compile_pdf(output_md, output_pdf)
    except RuntimeError as exc:
        print(str(exc))
        return 1

    print(f"Wrote research PDF: {output_pdf}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Format research output markdown into a plain PDF")
    parser.add_argument(
        "input_md",
        nargs="?",
        default="research_output.md",
        help="Input research markdown path (default: research_output.md)",
    )
    parser.add_argument(
        "--output-md",
        default="research_output.formatted.md",
        help="Formatted markdown output path (default: research_output.formatted.md)",
    )
    parser.add_argument(
        "--pdf",
        default="research_output.formatted.pdf",
        help="Output PDF path (default: research_output.formatted.pdf)",
    )
    parser.add_argument(
        "--title",
        default="Research Notes",
        help="Heading to add when input markdown does not start with one",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run(
        input_md=Path(args.input_md),
        output_md=Path(args.output_md),
        output_pdf=Path(args.pdf),
        heading=args.title,
    )


if __name__ == "__main__":
    raise SystemExit(main())
