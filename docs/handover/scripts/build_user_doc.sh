#!/usr/bin/env bash
# Rebuild the User Document's Word copy from its Markdown source.
# Run from docs/handover/. Needs pandoc, and a Python with lxml (e.g. PYTHON=/usr/bin/python3).
set -euo pipefail
PY="${PYTHON:-python3}"
pandoc user-document.md -o user-document.docx --toc --toc-depth=2 --resource-path=.
"$PY" scripts/fix_pandoc_docx.py user-document.docx

# PDF: via HTML and headless Chrome, so the contents list and the equations are
# drawn by the browser rather than left as Word fields.
TMP="$(mktemp -d)"
pandoc user-document.md -s --toc --toc-depth=2 --mathml --embed-resources \
    --css scripts/smd.css --css scripts/user-doc.css --metadata title="Learning Journey Assistant: User Document" \
    --resource-path=. -o "$TMP/smd.html"
google-chrome --headless=new --disable-gpu --no-pdf-header-footer --print-to-pdf="$PWD/user-document.pdf" "file://$TMP/smd.html" 2>/dev/null
echo "wrote user-document.docx and .pdf"
