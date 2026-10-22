#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping

import startup_audit
from cv_convert import choose_font
from settings_env import one_shot_env


def normalize_markdown(text: str) -> str:
    """Purpose: Execute normalize markdown for this module's workflow.
    
    Inputs:
    - text: Input text content being parsed, normalized, or inspected.
    
    Returns:
    - `str` value representing the operation result.
    """
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
    """Purpose: Execute ensure heading for this module's workflow.
    
    Inputs:
    - text: Input text content being parsed, normalized, or inspected.
    - heading: Heading title to enforce at the top of formatted markdown.
    
    Returns:
    - `str` value representing the operation result.
    """
    stripped = text.lstrip()
    if stripped.startswith("#"):
        return text

    return f"# {heading}\n\n{text}" if text else f"# {heading}\n"


def resolve_research_pdf_font(env: Mapping[str, str] | None = None) -> str:
    """Purpose: Execute resolve research pdf font for this module's workflow.
    
    Inputs:
    - env: Settings environment holding CV_FONT_PRIORITY (default `os.environ`).
    
    Returns:
    - `str` value representing the operation result.
    """
    preferred_font_raw = (os.environ if env is None else env).get("CV_FONT_PRIORITY", "Calibri,Arial,Helvetica")
    preferred_fonts = [item.strip() for item in preferred_font_raw.split(",") if item.strip()]
    if not preferred_fonts:
        preferred_fonts = ["Calibri", "Arial", "Helvetica"]
    return choose_font(preferred_fonts)


def compile_pdf(markdown_file: Path, output_pdf: Path, font_name: str) -> None:
    """Purpose: Execute compile pdf for this module's workflow.
    
    Inputs:
    - markdown_file: Source markdown file compiled into PDF.
    - output_pdf: Path where formatted PDF output is written.
    - font_name: Font family name supplied to the PDF engine.
    
    Returns:
    - None. This function performs side effects only.
    """
    if not shutil.which("pandoc"):
        raise RuntimeError("pandoc is required to generate research PDF")

    cmd = ["pandoc", str(markdown_file), "-o", str(output_pdf)]
    if shutil.which("typst"):
        cmd.extend(
            [
                "--pdf-engine=typst",
                "-V",
                f"mainfont={font_name}",
                "-V",
                f"sansfont={font_name}",
            ]
        )

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        message = stderr or stdout or "unknown pandoc failure"
        raise RuntimeError(f"PDF generation failed: {message}")


DEFAULT_HEADING = "Research Notes"


def format_markdown(text: str, heading: str = DEFAULT_HEADING) -> str:
    """Purpose: Normalise research markdown for the PDF: blank lines, a top heading, no `---` rules.

    Inputs:
    - text: Raw research markdown (a run's `output_md` or `research_output.md`).
    - heading: Heading title to enforce at the top of formatted markdown.

    Returns:
    - `str` formatted markdown, without a trailing newline.
    """
    processed = normalize_markdown(text)
    processed = ensure_heading(processed, heading)

    # Avoid accidental markdown horizontal-rules from standalone --- separators.
    processed = re.sub(r"(?m)^---+$", "", processed)
    return normalize_markdown(processed)


def render_research_pdf(
    text: str, heading: str = DEFAULT_HEADING, env: Mapping[str, str] | None = None
) -> bytes:
    """Purpose: Format research markdown and render it to PDF bytes in memory (no `output/` files).

    Inputs:
    - text: Raw research markdown.
    - heading: Heading title to enforce at the top of formatted markdown.
    - env: Settings environment holding CV_FONT_PRIORITY (default `os.environ`).

    Returns:
    - `bytes` of the PDF. Raises `RuntimeError` for empty input or a failed pandoc run.
    """
    if not text.strip():
        raise RuntimeError("Research markdown is empty")
    font_name = resolve_research_pdf_font(env)
    with tempfile.TemporaryDirectory(prefix="research-pdf-") as tmp:
        markdown_file = Path(tmp) / "research.md"
        output_pdf = Path(tmp) / "research.pdf"
        markdown_file.write_text(format_markdown(text, heading) + "\n", encoding="utf-8")
        compile_pdf(markdown_file, output_pdf, font_name)
        return output_pdf.read_bytes()


def run(
    input_md: Path, output_md: Path, output_pdf: Path, heading: str, env: Mapping[str, str] | None = None
) -> int:
    """Purpose: Run the operation and return its outcome.
    
    Inputs:
    - input_md: Path to source research markdown file.
    - output_md: Path where formatted markdown output is written.
    - output_pdf: Path where formatted PDF output is written.
    - heading: Heading title to enforce at the top of formatted markdown.
    
    Returns:
    - `int` value representing the operation result.
    """
    if not input_md.exists():
        print(f"Input markdown not found: {input_md}")
        return 1

    source_text = input_md.read_text(encoding="utf-8")
    if not source_text.strip():
        print("Input markdown is empty. Run research first.")
        return 1

    processed = format_markdown(source_text, heading)

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(processed + "\n", encoding="utf-8")
    print(f"Wrote formatted markdown: {output_md}")

    font_name = resolve_research_pdf_font(env)
    print(f"Using research PDF font: {font_name}")

    try:
        compile_pdf(output_md, output_pdf, font_name)
    except RuntimeError as exc:
        print(str(exc))
        return 1

    print(f"Wrote research PDF: {output_pdf}")
    return 0


def parse_args() -> argparse.Namespace:
    """Purpose: Parse and validate args for downstream use.
    
    Inputs:
    - None.
    
    Returns:
    - `argparse.Namespace` value representing the operation result.
    """
    parser = argparse.ArgumentParser(description="Format research output markdown into a plain PDF")
    parser.add_argument(
        "input_md",
        nargs="?",
        default="output/research_output.md",
        help="Input research markdown path (default: output/research_output.md)",
    )
    parser.add_argument(
        "--output-md",
        default="output/research_output.formatted.md",
        help="Formatted markdown output path (default: output/research_output.formatted.md)",
    )
    parser.add_argument(
        "--pdf",
        default="output/research_output.formatted.pdf",
        help="Output PDF path (default: output/research_output.formatted.pdf)",
    )
    parser.add_argument(
        "--title",
        default=DEFAULT_HEADING,
        help="Heading to add when input markdown does not start with one",
    )
    return parser.parse_args()


def main() -> int:
    """Purpose: Execute main for this module's workflow.
    
    Inputs:
    - None.
    
    Returns:
    - `int` value representing the operation result.
    """
    args = parse_args()
    startup_audit.audit_or_exit()
    return run(
        input_md=Path(args.input_md),
        output_md=Path(args.output_md),
        output_pdf=Path(args.pdf),
        heading=args.title,
        env=one_shot_env(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
