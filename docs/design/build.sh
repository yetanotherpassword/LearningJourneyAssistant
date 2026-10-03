#!/usr/bin/env bash
# Rebuild the three design documents as PDF and Word from their Markdown
# sources, after re-rendering the Mermaid diagrams they embed.
# Run from docs/design/. Needs pandoc, google-chrome, node (npx) and a Python
# with lxml (e.g. PYTHON=/usr/bin/python3). Output goes to docs/ under the
# names the August 2026 pages used, so existing links keep working.
set -euo pipefail
PY="${PYTHON:-python3}"
HERE="$(cd "$(dirname "$0")" && pwd)"
DIAG="$HERE/../handover/diagrams"
OUT="$HERE/.."

if [[ "${SKIP_DIAGRAMS:-}" != "1" ]]; then
  for f in 01-architecture 02-use-cases 03-classes 04-seq-pipeline 05-seq-learning-plan 06-trust-boundaries 07-evidence-lineage 16-seq-generate-from-dashboard; do
    npx -y @mermaid-js/mermaid-cli -i "$DIAG/$f.mmd" -o "$DIAG/$f.png" --size 1800 -s 2 -b white
    npx -y @mermaid-js/mermaid-cli -i "$DIAG/$f.mmd" -o "$DIAG/$f.svg" -b white
  done
fi

build() {  # build <source.md> <output basename without extension>
  local src="$1" base="$2" tmp
  tmp="$(mktemp -d)"
  pandoc "$HERE/$src" -o "$OUT/$base.docx" --toc --toc-depth=2 --resource-path="$HERE" --reference-doc="$HERE/../handover/scripts/reference.docx"
  "$PY" "$HERE/../handover/scripts/fix_pandoc_docx.py" "$OUT/$base.docx"
  pandoc "$HERE/$src" -s --toc --toc-depth=2 --embed-resources \
      --css "$HERE/../handover/scripts/smd.css" --metadata title="$base" \
      --resource-path="$HERE" -o "$tmp/page.html"
  google-chrome --headless=new --disable-gpu --no-pdf-header-footer \
      --print-to-pdf="$OUT/$base.pdf" "file://$tmp/page.html" 2>/dev/null
  echo "wrote $base.pdf and $base.docx"
}

build data-and-algorithm-pipeline.md "LJA — Data & Algorithm Pipeline"
build cli-pipeline.md "LJA -- Pipeline"
build uml-use-case-and-sequence.md "LJA — UML Use Case & Sequence Diagrams"
build requirements-status.md "LJA -- Requirements_status"
