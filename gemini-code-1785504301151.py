import subprocess

# 1. Run your AI generation logic here to create 'tailored_resume.md'

# 2. Convert tailored Markdown to Word using a custom template
subprocess.run([
    "pandoc", "tailored_resume.md",
    "-o", "output_resume.docx",
    "--reference-doc=styles_template.docx"  # Defines your fonts, margins, header styles
])

# 3. Convert tailored Markdown to PDF via Typst or WeasyPrint
subprocess.run([
    "pandoc", "tailored_resume.md",
    "-o", "output_resume.pdf",
    "--pdf-engine=typst"
])