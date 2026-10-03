#!/usr/bin/env bash
# Rebuild the System Maintenance Document's Word copy from its Markdown source.
# Run from docs/handover/. Needs pandoc, and a Python with lxml (e.g. PYTHON=/usr/bin/python3).
set -euo pipefail
PY="${PYTHON:-python3}"
pandoc system-maintenance-document.md -o system-maintenance-document.docx --toc --toc-depth=2 --resource-path=. --reference-doc=scripts/reference.docx
"$PY" scripts/fix_pandoc_docx.py system-maintenance-document.docx

# PDF: via HTML and headless Chrome, so the contents list and the equations are
# drawn by the browser rather than left as Word fields.
TMP="$(mktemp -d)"
pandoc system-maintenance-document.md -s --toc --toc-depth=2 --mathml --embed-resources \
    --css scripts/smd.css --metadata title="Learning Journey Assistant: System Maintenance Document" \
    --resource-path=. -o "$TMP/smd.html"
google-chrome --headless=new --disable-gpu --no-pdf-header-footer --print-to-pdf="$PWD/system-maintenance-document.pdf" "file://$TMP/smd.html" 2>/dev/null
echo "wrote system-maintenance-document.docx and .pdf"
