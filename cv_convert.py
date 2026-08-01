#!/usr/bin/env python3
import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ConversionResult:
    pdf_ok: bool
    docx_ok: bool
    export_markdown_path: Path
    used_sanitized_markdown: bool


def strip_yaml_frontmatter(markdown_text: str) -> tuple[str, bool]:
    """Remove a leading YAML frontmatter block if present."""
    lines = markdown_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return markdown_text, False

    for i in range(1, len(lines)):
        marker = lines[i].strip()
        if marker in {"---", "..."}:
            stripped = "\n".join(lines[i + 1 :]).lstrip("\n")
            return stripped, True

    return markdown_text, False


def compile_pdf(markdown_file: Path, output_pdf: Path) -> bool:
    """Compile markdown to PDF using Pandoc with Typst engine when available."""
    if shutil.which("pandoc") and shutil.which("typst"):
        try:
            subprocess.run(
                [
                    "pandoc",
                    str(markdown_file),
                    "-o",
                    str(output_pdf),
                    "--pdf-engine=typst",
                ],
                check=True,
                text=True,
            )
            return True
        except subprocess.CalledProcessError as exc:
            print(f"Pandoc+Typst PDF compilation failed: {exc}", file=sys.stderr)

    if shutil.which("pandoc"):
        try:
            subprocess.run(
                ["pandoc", str(markdown_file), "-o", str(output_pdf)],
                check=True,
                text=True,
            )
            return True
        except subprocess.CalledProcessError as exc:
            print(f"Pandoc PDF compilation failed: {exc}", file=sys.stderr)

    return False


def compile_docx(markdown_file: Path, output_docx: Path) -> bool:
    """Compile markdown to DOCX using Pandoc."""
    if not shutil.which("pandoc"):
        return False

    try:
        subprocess.run(
            ["pandoc", str(markdown_file), "-o", str(output_docx)],
            check=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        print(f"Pandoc DOCX compilation failed: {exc}", file=sys.stderr)
        return False


def convert_markdown_outputs(
    markdown_path: Path,
    output_pdf: Path,
    output_docx: Path,
    sanitized_markdown_path: Path | None = None,
) -> ConversionResult:
    """Convert a markdown CV to PDF and DOCX outputs.

    If leading YAML frontmatter is present, a sanitized markdown file is generated
    for export stability while preserving the original markdown input.
    """
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {markdown_path}")

    markdown_text = markdown_path.read_text(encoding="utf-8")
    export_markdown_text, stripped_frontmatter = strip_yaml_frontmatter(markdown_text)

    export_markdown_path = markdown_path
    if stripped_frontmatter:
        export_markdown_path = sanitized_markdown_path or markdown_path.with_suffix(".export.md")
        export_markdown_path.write_text(export_markdown_text + "\n", encoding="utf-8")

    pdf_ok = compile_pdf(export_markdown_path, output_pdf)
    docx_ok = compile_docx(export_markdown_path, output_docx)

    return ConversionResult(
        pdf_ok=pdf_ok,
        docx_ok=docx_ok,
        export_markdown_path=export_markdown_path,
        used_sanitized_markdown=stripped_frontmatter,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a tailored markdown CV to PDF and DOCX.",
    )
    parser.add_argument(
        "markdown",
        nargs="?",
        default="tailored.md",
        help="Input markdown file (default: tailored.md)",
    )
    parser.add_argument(
        "--pdf",
        default="tailored.pdf",
        help="Output PDF path (default: tailored.pdf)",
    )
    parser.add_argument(
        "--docx",
        default="tailored.docx",
        help="Output DOCX path (default: tailored.docx)",
    )
    parser.add_argument(
        "--sanitized-markdown",
        default="tailored.export.md",
        help="Path for sanitized export markdown when frontmatter is stripped",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    markdown_path = Path(args.markdown)
    output_pdf = Path(args.pdf)
    output_docx = Path(args.docx)
    sanitized_markdown = Path(args.sanitized_markdown)

    try:
        result = convert_markdown_outputs(
            markdown_path=markdown_path,
            output_pdf=output_pdf,
            output_docx=output_docx,
            sanitized_markdown_path=sanitized_markdown,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    if result.used_sanitized_markdown:
        print(f"Detected YAML frontmatter; using sanitized export file: {result.export_markdown_path}")

    if result.pdf_ok:
        print(f"Success! PDF created at: {output_pdf.resolve()}")
    else:
        print("PDF generation failed.", file=sys.stderr)

    if result.docx_ok:
        print(f"Success! DOCX created at: {output_docx.resolve()}")
    else:
        print("DOCX generation failed.", file=sys.stderr)

    if not result.pdf_ok and not result.docx_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
