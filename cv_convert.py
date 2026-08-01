#!/usr/bin/env python3
import argparse
import os
import re
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

    def normalize_summary_markdown(text: str) -> str:
        """Keep bold markers while removing single-asterisk emphasis.

        Summary paragraphs are rendered with whole-line italics by the
        converter, so any incidental inline italics from generation should be
        stripped to avoid malformed emphasis like "****...***".
        """
        protected = text.replace("**", "__BOLD_MARKER__")
        deitalicized = protected.replace("*", "")
        return deitalicized.replace("__BOLD_MARKER__", "**").strip()

    def normalize_tel_url(url: str) -> str:
        phone = url[4:]
        phone = phone.replace("%2B", "+").replace("%2b", "+")
        return phone

    def normalize_candidate_contact_text(text: str) -> str:
        """Ensure phone values are explicit text, not tel links."""
        pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

        def repl(match: re.Match[str]) -> str:
            label = match.group(1).strip()
            url = match.group(2).strip()
            if url.lower().startswith("mailto:"):
                email_value = url.split(":", 1)[1].strip()
                if "@" in email_value:
                    if label.lower() == "email" or "@" not in label:
                        return f"[{email_value}](mailto:{email_value})"
                return match.group(0)

            if url.lower().startswith("tel:"):
                phone = normalize_tel_url(url)
                if any(ch.isdigit() for ch in label):
                    return label
                return phone
            return match.group(0)

        return pattern.sub(repl, text)

    def emit_pdf_centered_with_links(tag: str, text: str) -> list[str]:
        style = pdf_tag_styles[tag]
        parts: list[str] = []
        text = normalize_candidate_contact_text(text)
        pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
        cursor = 0

        for match in pattern.finditer(text):
            prefix = text[cursor : match.start()]
            if prefix:
                parts.append(f"#text(\"{typst_escape(prefix)}\")")

            label = typst_escape(match.group(1))
            raw_url = match.group(2)
            is_mailto = raw_url.lower().startswith("mailto:")
            if raw_url.lower().startswith("mailto:"):
                raw_url = raw_url.replace("@", "%40")
            url = typst_escape(raw_url)
            if is_mailto:
                # Keep email clickable, but use normal text styling.
                parts.append(f"#link(\"{url}\")[#text(\"{label}\")]")
            else:
                # Social/web links remain visibly clickable.
                parts.append(
                    f"#link(\"{url}\")[#underline[#text(fill: rgb(\"#0563C1\"))[#text(\"{label}\")]]]"
                )
            cursor = match.end()

        suffix = text[cursor:]
        if suffix:
            parts.append(f"#text(\"{typst_escape(suffix)}\")")

        if not parts:
            parts = [f"#text(\"{typst_escape(text)}\")"]

        return [
            "```{=typst}",
            "#align(center)[",
            f"  #set text({style['size']}, weight: \"{style['weight']}\")",
            "  " + " ".join(parts),
            "]",
            "#parbreak()",
            "```",
            "",
        ]

    def emit_pdf_centered(tag: str, text: str) -> list[str]:
        style = pdf_tag_styles[tag]
        escaped_text = typst_escape(text)
        return [
            "```{=typst}",
            "#align(center)[",
            f"  #set text({style['size']}, weight: \"{style['weight']}\")",
            f"  #text(\"{escaped_text}\")",
            "]",
            "#parbreak()",
            "```",
            "",
        ]

    def emit_pdf_section_heading(text: str) -> list[str]:
        escaped_text = typst_escape(text)
        return [
            "```{=typst}",
            f"#text(12pt, weight: \"bold\")[{escaped_text}]",
            "#parbreak()",
            "```",
            "",
        ]

    def emit_pdf_role_heading(text: str) -> list[str]:
        escaped_text = typst_escape(text)
        return [
            "```{=typst}",
            f"#text(10pt, weight: \"bold\")[{escaped_text}]",
            "#parbreak()",
            "```",
            "",
        ]

    def emit_pdf_date_range(text: str) -> list[str]:
        escaped_text = typst_escape(text)
        return [
            "```{=typst}",
            f"#text(9pt)[{escaped_text}]",
            "#parbreak()",
            "```",
            "",
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
                contact_text = normalize_candidate_contact_text(contact_text)
                if target == "pdf":
                    transformed_lines.extend(emit_pdf_centered_with_links("candidate_contact", contact_text))
                else:
                    transformed_lines.append(contact_text)
                continue

        section_match = re.match(r"^#+\s+\[section_heading\]\s*(.+)$", stripped)
        if section_match:
            heading_text = section_match.group(1).strip()
            if target == "pdf":
                transformed_lines.extend(emit_pdf_section_heading(heading_text))
            else:
                transformed_lines.append(f"**{heading_text}**")
            continue

        role_match = re.match(r"^##\s+\[role_heading\]\s*(.+)$", stripped)
        if role_match:
            role_text = role_match.group(1).strip()
            if target == "pdf":
                transformed_lines.extend(emit_pdf_role_heading(role_text))
            else:
                transformed_lines.append(f"**{role_text}**")
            continue

        date_match = re.match(r"^\[date_range\]\s*(.+)$", stripped)
        if date_match:
            date_text = date_match.group(1).strip()
            if target == "pdf":
                transformed_lines.extend(emit_pdf_date_range(date_text))
            else:
                transformed_lines.append(date_text)
            continue

        summary_match = re.match(r"^\[summary_paragraph\]\s*(.+)$", stripped)
        if summary_match:
            summary_text = normalize_summary_markdown(summary_match.group(1).strip())
            transformed_lines.append(f"*{summary_text}*")
            transformed_lines.append("")
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
        default="tailored_dev.pdf",
        help="Output PDF path (default: tailored_dev.pdf)",
    )
    parser.add_argument(
        "--docx",
        default="tailored_dev.docx",
        help="Output DOCX path (default: tailored_dev.docx)",
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
