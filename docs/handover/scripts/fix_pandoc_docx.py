"""Make pandoc's .docx output pass strict OOXML schema validation.

Word opens pandoc's output as it is, but stricter tools reject it. Pandoc
writes some child elements in an order the schema does not allow, pads some
ids too short, declares images per file rather than by extension, and its
style template has a stray character inside one formatting block. This
script fixes all of those in place without changing any content.

    python fix_pandoc_docx.py system-maintenance-document.docx

Needs lxml (the system /usr/bin/python3 has it; the `lja` conda env does not).
"""

import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"

# Schema order of child elements (ECMA-376, transitional). Only the parents
# pandoc gets wrong are listed; children not named keep their order at the end.
ORDER = {
    (W, "settings"): """writeProtection view zoom removePersonalInformation removeDateAndTime
        doNotDisplayPageBoundaries displayBackgroundShape printPostScriptOverText printFractionalCharacterWidth
        printFormsData embedTrueTypeFonts embedSystemFonts saveSubsetFonts saveFormsData mirrorMargins
        alignBordersAndEdges bordersDoNotSurroundHeader bordersDoNotSurroundFooter gutterAtTop hideSpellingErrors
        hideGrammaticalErrors activeWritingStyle proofState formsDesign attachedTemplate linkStyles
        stylePaneFormatFilter stylePaneSortMethod documentType mailMerge revisionView trackRevisions
        doNotTrackMoves doNotTrackFormatting documentProtection autoFormatOverride styleLockTheme styleLockQFSet
        defaultTabStop autoHyphenation consecutiveHyphenLimit hyphenationZone doNotHyphenateCaps showEnvelope
        summaryLength clickAndTypeStyle defaultTableStyle evenAndOddHeaders bookFoldRevPrinting bookFoldPrinting
        bookFoldPrintingSheets drawingGridHorizontalSpacing drawingGridVerticalSpacing
        displayHorizontalDrawingGridEvery displayVerticalDrawingGridEvery doNotUseMarginsForDrawingGridOrigin
        drawingGridHorizontalOrigin drawingGridVerticalOrigin doNotShadeFormData noPunctuationKerning
        characterSpacingControl printTwoOnOne strictFirstAndLastChars noLineBreaksAfter noLineBreaksBefore
        savePreviewPicture doNotValidateAgainstSchema saveInvalidXml ignoreMixedContent alwaysShowPlaceholderText
        doNotDemarcateInvalidXml saveXmlDataOnly useXSLTWhenSaving saveThroughXslt showXMLTags
        alwaysMergeEmptyNamespace updateFields hdrShapeDefaults footnotePr endnotePr compat docVars rsids mathPr
        attachedSchema themeFontLang clrSchemeMapping doNotIncludeSubdocsInStats doNotAutoCompressPictures
        forceUpgrade captions readModeInkLockDown smartTagType schemaLibrary shapeDefaults doNotEmbedSmartTags
        decimalSymbol listSeparator""",
    (W, "style"): """name aliases basedOn next link autoRedefine hidden uiPriority semiHidden unhideWhenUsed qFormat
        locked personal personalCompose personalReply rsid pPr rPr tblPr trPr tcPr tblStylePr""",
    (W, "pPr"): """pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd
        tabs suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi
        adjustRightInd snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection
        textAlignment textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange""",
    (W, "tblPr"): """tblStyle tblpPr tblOverlap bidiVisual tblStyleRowBandSize tblStyleColBandSize tblW jc
        tblCellSpacing tblInd tblBorders shd tblLayout tblCellMar tblLook tblCaption tblDescription""",
    (W, "tcPr"): """cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar textDirection tcFitText vAlign
        hideMark""",
    (M, "dPr"): "begChr sepChr endChr grow shp ctrlPr",
}
ORDER = {key: {name: i for i, name in enumerate(names.split())} for key, names in ORDER.items()}


def reorder(root: etree._Element) -> None:
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        qn = etree.QName(el)
        rank = ORDER.get((qn.namespace, qn.localname))
        if rank is None:
            continue
        children = [c for c in el if isinstance(c.tag, str)]
        ordered = sorted(children, key=lambda c: rank.get(etree.QName(c).localname, len(rank)))
        if ordered != children:
            for c in children:
                el.remove(c)
            el.extend(ordered)


def fix_math_rpr(root: etree._Element) -> None:
    # <m:nor/> and <m:sty/> are alternatives in a math run's properties.
    for rpr in root.iter(f"{{{M}}}rPr"):
        if rpr.find(f"{{{M}}}nor") is not None:
            for sty in rpr.findall(f"{{{M}}}sty"):
                rpr.remove(sty)


def fix_xml(name: str, data: bytes) -> bytes:
    root = etree.fromstring(data)
    reorder(root)
    if name == "word/document.xml":
        fix_math_rpr(root)
    if name == "word/styles.xml":
        # Pandoc's default style template contains a stray ">" inside a <w:rPr>.
        for rpr in root.iter(f"{{{W}}}rPr"):
            if rpr.text and rpr.text.strip():
                rpr.text = None
            for child in rpr:
                if child.tail and child.tail.strip():
                    child.tail = None
    if name == "word/numbering.xml":
        for nsid in root.iter(f"{{{W}}}nsid"):
            val = nsid.get(f"{{{W}}}val")
            if val and len(val) < 8:
                nsid.set(f"{{{W}}}val", val.zfill(8))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def fix_content_types(data: bytes) -> bytes:
    text = data.decode("utf-8")
    for ext, mime in (("png", "image/png"), ("jpeg", "image/jpeg"), ("jpg", "image/jpeg"), ("svg", "image/svg+xml")):
        if f'Extension="{ext}"' not in text:
            text = re.sub(r"(<Types[^>]*>)", rf'\1<Default Extension="{ext}" ContentType="{mime}"/>', text, count=1)
    return text.encode("utf-8")


def main(path: str) -> None:
    src = Path(path)
    tmp = Path(tempfile.mkdtemp()) / src.name
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "[Content_Types].xml":
                data = fix_content_types(data)
            elif item.filename in ("word/document.xml", "word/styles.xml", "word/settings.xml", "word/numbering.xml"):
                data = fix_xml(item.filename, data)
            zout.writestr(item, data)
    shutil.move(tmp, src)
    print(f"fixed {src}")


if __name__ == "__main__":
    main(sys.argv[1])
