#!/usr/bin/env python3
import argparse
import os
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
    chosen_font: str


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


def apply_semantic_tag_formatting(markdown_text: str, target: str = "generic") -> str:
    """Apply formatting transforms for known semantic tags.

    Increment 1: candidate_name becomes the document H1 heading.
    PDF specialization: candidate_name becomes centered, larger raw Typst text.
    """
    transformed_lines: list[str] = []

    # Keep this mapping centralized so DOCX-specific transforms can be added
    # later with minimal change.
    pdf_tag_styles: dict[str, dict[str, str]] = {
        "candidate_name": {"size": "18pt", "weight": "bold"},
        "candidate_title": {"size": "12pt", "weight": "bold"},
        "candidate_contact": {"size": "10pt", "weight": "bold"},
    }

    def typst_escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"')

    def emit_pdf_centered(tag: str, text: str) -> list[str]:
        style = pdf_tag_styles[tag]
        escaped_text = typst_escape(text)
        return [
            "```{=typst}",
            "#align(center)[",
            f"  #set text({style['size']}, weight: \"{style['weight']}\")",
            f"  #text(\"{escaped_text}\")",
            "]",
            "```",
        ]

    for line in markdown_text.splitlines():
        stripped = line.strip()

        if stripped.startswith("[candidate_name]"):
            name_text = stripped[len("[candidate_name]") :].strip()
            if name_text:
                if target == "pdf":
                    transformed_lines.extend(emit_pdf_centered("candidate_name", name_text))
                else:
                    transformed_lines.append(f"# {name_text}")
                continue

        if stripped.startswith("[candidate_title]"):
            title_text = stripped[len("[candidate_title]") :].strip()
            if title_text:
                if target == "pdf":
                    transformed_lines.extend(emit_pdf_centered("candidate_title", title_text))
                else:
                    transformed_lines.append(f"**{title_text}**")
                continue

        if stripped.startswith("[candidate_contact]"):
            contact_text = stripped[len("[candidate_contact]") :].strip()
            if contact_text:
                if target == "pdf":
                    transformed_lines.extend(emit_pdf_centered("candidate_contact", contact_text))
                else:
                    transformed_lines.append(contact_text)
                continue

        transformed_lines.append(line)

    return "\n".join(transformed_lines)


def list_available_font_families() -> set[str]:
    """Collect locally available font family names for simple matching."""
    families: set[str] = set()

    if shutil.which("fc-list"):
        try:
            result = subprocess.run(
                ["fc-list", ":", "family"],
                check=True,
                capture_output=True,
                text=True,
            )
            for line in result.stdout.splitlines():
                for name in line.split(","):
                    cleaned = name.strip().lower()
                    if cleaned:
                        families.add(cleaned)
        except subprocess.CalledProcessError:
            pass

    for font_dir in [
        Path("/Library/Fonts"),
        Path.home() / "Library" / "Fonts",
        Path("/System/Library/Fonts"),
    ]:
        if not font_dir.exists():
            continue
        for entry in font_dir.iterdir():
            base = entry.stem.lower()
            for token in ["calibri", "arial", "helvetica"]:
                if token in base:
                    families.add(token)

    return families


def choose_font(preferred_fonts: list[str]) -> str:
    """Choose first installed font from preferred list, otherwise return first item."""
    available = list_available_font_families()
    for font in preferred_fonts:
        if font.lower() in available:
            return font
    return preferred_fonts[0]


def compile_pdf(markdown_file: Path, output_pdf: Path, font_name: str) -> bool:
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
                    "-V",
                    f"mainfont={font_name}",
                    "-V",
                    f"sansfont={font_name}",
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


def compile_docx(markdown_file: Path, output_docx: Path, font_name: str) -> bool:
    """Compile markdown to DOCX using Pandoc."""
    if not shutil.which("pandoc"):
        return False

    try:
        subprocess.run(
            [
                "pandoc",
                str(markdown_file),
                "-o",
                str(output_docx),
                "-V",
                f"mainfont={font_name}",
                "-V",
                f"sansfont={font_name}",
            ],
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
    pdf_only: bool = False,
) -> ConversionResult:
    """Convert a markdown CV to PDF and DOCX outputs.

    If leading YAML frontmatter is present, a sanitized markdown file is generated
    for export stability while preserving the original markdown input.
    """
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {markdown_path}")

    preferred_font_raw = os.environ.get("CV_FONT_PRIORITY", "Calibri,Arial,Helvetica")
    preferred_fonts = [item.strip() for item in preferred_font_raw.split(",") if item.strip()]
    if not preferred_fonts:
        preferred_fonts = ["Calibri", "Arial", "Helvetica"]
    chosen_font = choose_font(preferred_fonts)

    markdown_text = markdown_path.read_text(encoding="utf-8")

    pdf_markdown_text = apply_semantic_tag_formatting(markdown_text, target="pdf")
    pdf_export_text, pdf_stripped_frontmatter = strip_yaml_frontmatter(pdf_markdown_text)
    pdf_export_path = sanitized_markdown_path or markdown_path.with_suffix(".export.md")
    pdf_export_path.write_text(pdf_export_text + "\n", encoding="utf-8")

    pdf_ok = compile_pdf(pdf_export_path, output_pdf, chosen_font)

    docx_ok = False
    if not pdf_only:
        docx_markdown_text = apply_semantic_tag_formatting(markdown_text, target="docx")
        docx_export_text, _ = strip_yaml_frontmatter(docx_markdown_text)
        docx_export_path = markdown_path.with_suffix(".docx.export.md")
        docx_export_path.write_text(docx_export_text + "\n", encoding="utf-8")
        docx_ok = compile_docx(docx_export_path, output_docx, chosen_font)

    return ConversionResult(
        pdf_ok=pdf_ok,
        docx_ok=docx_ok,
        export_markdown_path=pdf_export_path,
        used_sanitized_markdown=pdf_stripped_frontmatter,
        chosen_font=chosen_font,
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
    parser.add_argument(
        "--pdf-only",
        action="store_true",
        help="Generate only PDF output (skip DOCX conversion)",
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
            pdf_only=args.pdf_only,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    if result.used_sanitized_markdown:
        print(f"Detected YAML frontmatter; using sanitized export file: {result.export_markdown_path}")

    print(f"Using output font: {result.chosen_font}")

    if result.pdf_ok:
        print(f"Success! PDF created at: {output_pdf.resolve()}")
    else:
        print("PDF generation failed.", file=sys.stderr)

    if args.pdf_only:
        print("DOCX generation skipped (--pdf-only).")
    elif result.docx_ok:
        print(f"Success! DOCX created at: {output_docx.resolve()}")
    else:
        print("DOCX generation failed.", file=sys.stderr)

    if args.pdf_only and not result.pdf_ok:
        sys.exit(1)

    if not args.pdf_only and not result.pdf_ok and not result.docx_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
