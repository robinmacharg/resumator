#!/usr/bin/env python3
import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

THEMES_DIR = Path(__file__).resolve().parent / "themes"
STYLES_FILTER = THEMES_DIR / "styles.lua"
DEFAULT_TYPST_THEME = THEMES_DIR / "default.typ"
DOCX_STYLES = THEMES_DIR / "docx-styles.xml"


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


def styled_block(style: str, text: str) -> list[str]:
    """Wrap text in a pandoc fenced div carrying a theme style name."""
    return [f'::: {{custom-style="{style}"}}', text, ":::", ""]


def apply_semantic_tag_formatting(markdown_text: str) -> str:
    """Turn tagged markdown into semantic markdown for both PDF and DOCX.

    Each known tag becomes a pandoc div/span with custom-style="<name>". The looks
    live in themes/ (default.typ for PDF via styles.lua, docx-styles.xml for DOCX).
    Only text clean-up happens here, never styling.
    """
    transformed_lines: list[str] = []
    requirements_items: list[str] = []

    def normalize_summary_markdown(text: str) -> str:
        """Keep bold markers while removing single-asterisk emphasis.

        Summary paragraphs are whole-line italic in the theme, so incidental
        inline italics from generation are stripped to avoid malformed emphasis.
        """
        protected = text.replace("**", "__BOLD_MARKER__")
        deitalicized = protected.replace("*", "")
        return deitalicized.replace("__BOLD_MARKER__", "**").strip()

    def normalize_plain_text_markdown(text: str) -> str:
        """Strip markdown emphasis markers for fields that should be plain text."""
        cleaned = text.replace("**", "")
        cleaned = cleaned.replace("*", "")
        cleaned = cleaned.replace("`", "")
        return re.sub(r"\s+", " ", cleaned).strip()

    def normalize_date_text(text: str) -> str:
        """Normalize date_range text to date values only (no 'Dates' label)."""
        cleaned = text.replace("**", "").replace("*", "")
        cleaned = re.sub(r"^dates\s*[:\-]?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned.strip()

    def normalize_education_item_text(text: str) -> str:
        """Mark the title of an education entry as an education-title span.

        Expected pattern: <title> - <detail> or <title> — <detail>
        Only the left title portion is marked.
        """
        cleaned = text.strip()
        if not cleaned or cleaned.startswith("**"):
            return cleaned

        for separator in (" — ", " - "):
            if separator in cleaned:
                left, right = cleaned.split(separator, 1)
                return f'[{left.strip()}]{{custom-style="education-title"}}{separator}{right.strip()}'

        return cleaned

    def normalize_candidate_contact_text(text: str) -> str:
        """Ensure phone values are explicit text, not tel links."""
        pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

        def repl(match: re.Match[str]) -> str:
            """Rewrite one contact link: show emails as their address, unwrap tel links."""
            label = match.group(1).strip()
            url = match.group(2).strip()
            if url.lower().startswith("mailto:"):
                email_value = url.split(":", 1)[1].strip()
                if "@" in email_value:
                    if label.lower() == "email" or "@" not in label:
                        return f"[{email_value}](mailto:{email_value})"
                return match.group(0)

            if url.lower().startswith("tel:"):
                phone = url[4:].replace("%2B", "+").replace("%2b", "+")
                if any(ch.isdigit() for ch in label):
                    return label
                return phone
            return match.group(0)

        return pattern.sub(repl, text)

    def extract_tag_payload(line_text: str, tag: str) -> str | None:
        """Extract payload for semantic tags, allowing common prefix variants."""
        match = re.match(rf"^(?:#+\s+)?(?:[-*+]\s+)?\[{re.escape(tag)}\]\s*(.*)$", line_text)
        if not match:
            return None

        payload = match.group(1).strip()
        payload = re.sub(r"^[-*+]\s+", "", payload).strip()
        return payload

    def extract_first_tag_payload(line_text: str, tags: list[str]) -> str | None:
        """Return the payload of the first matching tag alias, or None."""
        for tag in tags:
            payload = extract_tag_payload(line_text, tag)
            if payload is not None:
                return payload
        return None

    def strip_heading_markers(text: str) -> str:
        """Remove leading markdown heading hashes."""
        return re.sub(r"^#+\s*", "", text).strip()

    def flush_requirements() -> None:
        """Emit collected requirement items as one styled list."""
        if requirements_items:
            body = "\n".join(f"- {item}" for item in requirements_items)
            transformed_lines.extend(styled_block("requirements-list", body))
            requirements_items.clear()

    # (tag aliases, style name, payload clean-up)
    styled_tags: list[tuple[list[str], str, object]] = [
        (["candidate_name", "name"], "candidate-name", None),
        (["candidate_title", "title"], "candidate-title", None),
        (["candidate_contact", "contact"], "candidate-contact", normalize_candidate_contact_text),
        (["keywords", "keyword"], "keywords", normalize_plain_text_markdown),
        (["section_heading", "section"], "section-heading", strip_heading_markers),
        (["role_heading", "role"], "role-heading", strip_heading_markers),
        (["date_range", "date"], "date-range", normalize_date_text),
        (["summary_paragraph", "summary"], "summary-item", normalize_summary_markdown),
        (
            ["role_requirements_heading", "requirements_heading"],
            "requirements-heading",
            strip_heading_markers,
        ),
    ]
    list_tags = ["bullet_primary", "bullet_secondary", "project_item"]

    for line in markdown_text.splitlines():
        stripped = line.strip()

        item_text = extract_first_tag_payload(stripped, ["role_requirements_item", "requirements_item"])
        if item_text is not None:
            item_text = item_text[1:].strip() if item_text.startswith("-") else item_text
            if item_text:
                requirements_items.append(item_text)
            continue
        flush_requirements()

        handled = False
        for aliases, style, clean in styled_tags:
            payload = extract_first_tag_payload(stripped, aliases)
            if payload is None:
                continue
            payload = clean(payload) if clean else payload
            if payload:
                transformed_lines.extend(styled_block(style, payload))
            handled = True
            break
        if handled:
            continue

        list_text = extract_first_tag_payload(stripped, list_tags)
        if list_text is not None:
            transformed_lines.append(f"- {list_text}")
            continue

        education_item_text = extract_tag_payload(stripped, "education_item")
        if education_item_text is not None:
            transformed_lines.append(f"- {normalize_education_item_text(education_item_text)}")
            continue

        transformed_lines.append(line)

    flush_requirements()
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


def typst_theme_files(theme: str | None) -> list[Path]:
    """Return the Typst theme files to include: default.typ, then the preset if any."""
    files = [DEFAULT_TYPST_THEME]
    name = (theme or "").strip()
    if not name or name == "default":
        return files

    preset = THEMES_DIR / f"{name}.typ"
    if preset.is_file():
        files.append(preset)
    else:
        print(f"Unknown theme preset '{name}'; using the default theme.", file=sys.stderr)
    return files


def compile_pdf(markdown_file: Path, output_pdf: Path, font_name: str, theme: str | None = None) -> bool:
    """Compile markdown to PDF using Pandoc with Typst engine when available."""
    if shutil.which("pandoc") and shutil.which("typst"):
        theme_args: list[str] = []
        for theme_file in typst_theme_files(theme):
            theme_args.extend(["--include-before-body", str(theme_file)])
        try:
            subprocess.run(
                [
                    "pandoc",
                    str(markdown_file),
                    "-o",
                    str(output_pdf),
                    "--pdf-engine=typst",
                    "--lua-filter",
                    str(STYLES_FILTER),
                    *theme_args,
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


def build_docx_reference(reference_docx: Path) -> bool:
    """Write pandoc's default reference.docx with themes/docx-styles.xml merged in."""
    try:
        default_reference = subprocess.run(
            ["pandoc", "--print-default-data-file", "reference.docx"],
            check=True,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        print(f"Could not read pandoc's default reference.docx: {exc}", file=sys.stderr)
        return False

    extra_styles = re.sub(r"<!--.*?-->", "", DOCX_STYLES.read_text(encoding="utf-8"), flags=re.DOTALL)

    with zipfile.ZipFile(io.BytesIO(default_reference)) as source, zipfile.ZipFile(
        reference_docx, "w", zipfile.ZIP_DEFLATED
    ) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/styles.xml":
                styles = data.decode("utf-8")
                data = styles.replace("</w:styles>", extra_styles.strip() + "\n</w:styles>").encode("utf-8")
            target.writestr(item, data)
    return True


def compile_docx(markdown_file: Path, output_docx: Path, font_name: str) -> bool:
    """Compile markdown to DOCX using Pandoc and the themed reference document."""
    if not shutil.which("pandoc"):
        return False

    page_margin = "1.5cm"
    reference_docx = output_docx.with_name("reference.docx")
    reference_args = ["--reference-doc", str(reference_docx)] if build_docx_reference(reference_docx) else []

    try:
        subprocess.run(
            [
                "pandoc",
                str(markdown_file),
                "-o",
                str(output_docx),
                *reference_args,
                "-V",
                f"mainfont={font_name}",
                "-V",
                f"sansfont={font_name}",
                "-V",
                f"margin={page_margin}",
                "-V",
                f"margin-left={page_margin}",
                "-V",
                f"margin-right={page_margin}",
                "-V",
                f"margin-top={page_margin}",
                "-V",
                f"margin-bottom={page_margin}",
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
    theme: str | None = None,
) -> ConversionResult:
    """Convert a markdown CV to PDF and DOCX outputs.

    The tagged markdown becomes one semantic export file (front matter stripped)
    that both outputs compile from; the looks come from themes/. `theme` names a
    PDF preset in themes/ (default: the CV_THEME env var, else the default theme).
    """
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {markdown_path}")

    preferred_font_raw = os.environ.get("CV_FONT_PRIORITY", "Calibri,Arial,Helvetica")
    preferred_fonts = [item.strip() for item in preferred_font_raw.split(",") if item.strip()]
    if not preferred_fonts:
        preferred_fonts = ["Calibri", "Arial", "Helvetica"]
    chosen_font = choose_font(preferred_fonts)
    if theme is None:
        theme = os.environ.get("CV_THEME")

    markdown_text = markdown_path.read_text(encoding="utf-8")

    semantic_text = apply_semantic_tag_formatting(markdown_text)
    export_text, stripped_frontmatter = strip_yaml_frontmatter(semantic_text)
    export_path = sanitized_markdown_path or markdown_path.with_suffix(".export.md")
    export_path.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(export_text + "\n", encoding="utf-8")

    pdf_ok = compile_pdf(export_path, output_pdf, chosen_font, theme)

    docx_ok = False
    if not pdf_only:
        docx_ok = compile_docx(export_path, output_docx, chosen_font)

    return ConversionResult(
        pdf_ok=pdf_ok,
        docx_ok=docx_ok,
        export_markdown_path=export_path,
        used_sanitized_markdown=stripped_frontmatter,
        chosen_font=chosen_font,
    )


def parse_args() -> argparse.Namespace:
    """Purpose: Parse and validate args for downstream use.
    
    Inputs:
    - None.
    
    Returns:
    - `argparse.Namespace` value representing the operation result.
    """
    parser = argparse.ArgumentParser(
        description="Convert a tailored markdown CV to PDF and DOCX.",
    )
    parser.add_argument(
        "markdown",
        nargs="?",
        default="output/tailored.md",
        help="Input markdown file (default: output/tailored.md)",
    )
    parser.add_argument(
        "--pdf",
        default="output/tailored_dev.pdf",
        help="Output PDF path (default: output/tailored_dev.pdf)",
    )
    parser.add_argument(
        "--docx",
        default="output/tailored_dev.docx",
        help="Output DOCX path (default: output/tailored_dev.docx)",
    )
    parser.add_argument(
        "--sanitized-markdown",
        default="output/tailored.export.md",
        help="Path for sanitized export markdown when frontmatter is stripped",
    )
    parser.add_argument(
        "--pdf-only",
        action="store_true",
        help="Generate only PDF output (skip DOCX conversion)",
    )
    parser.add_argument(
        "--theme",
        default=None,
        help="PDF theme preset in themes/ layered on default.typ, e.g. compact (default: $CV_THEME)",
    )
    return parser.parse_args()


def main() -> None:
    """Purpose: Execute main for this module's workflow.
    
    Inputs:
    - None.
    
    Returns:
    - None. This function performs side effects only.
    """
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
            theme=args.theme,
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
