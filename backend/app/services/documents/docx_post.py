"""Пост-обработка уже отрендеренного .docx: чистка ТЗ-легенды и
служебных Word-комментариев перед выдачей файла пользователю."""


import logging

logger = logging.getLogger(__name__)


def _strip_tech_spec_legend(docx_bytes: bytes) -> bytes:
    """Remove legend paragraphs from a rendered tech_spec_request docx.

    Deletes paragraphs from the first one containing «ЛЕГЕНДА» up to and
    including the first paragraph consisting solely of em-dashes (—), which
    acts as a visual separator.  If «ЛЕГЕНДА» is not found the original bytes
    are returned unchanged (custom subsidy template without a legend block).

    Wrapped in try/except: on any error returns the original bytes so the
    caller always receives a valid document.
    """
    try:
        from io import BytesIO as _BytesIO
        from docx import Document as _Document

        bio = _BytesIO(docx_bytes)
        doc = _Document(bio)
        paras = doc.paragraphs

        # Find start index: first paragraph containing «ЛЕГЕНДА»
        start_idx = None
        for i, p in enumerate(paras):
            if "ЛЕГЕНДА" in p.text:
                start_idx = i
                break

        if start_idx is None:
            return docx_bytes

        # Find end index: first paragraph after start consisting only of em-dashes
        end_idx = None
        for i in range(start_idx, len(paras)):
            stripped = paras[i].text.strip()
            if stripped and all(ch == "—" for ch in stripped):
                end_idx = i
                break

        if end_idx is None:
            # No separator found — remove from start to end of legend block
            end_idx = start_idx

        # Remove paragraphs in reverse order to keep indices stable
        for i in range(end_idx, start_idx - 1, -1):
            p_el = paras[i]._element
            p_el.getparent().remove(p_el)

        out = _BytesIO()
        doc.save(out)
        return out.getvalue()
    except Exception as _exc:
        logger.warning("_strip_tech_spec_legend: failed to strip legend, returning original: %s", _exc)
        return docx_bytes


def _strip_word_comments(docx_bytes: bytes) -> bytes:
    """Remove Word review comments from a rendered .docx file.

    Contract templates carry Word comments with Russian hints explaining
    {{tags}} to whoever edits the .docx TEMPLATE. docxtpl's render passes
    them through untouched (word/comments.xml survives into the output),
    so without this the hints meant for the template author would reach
    the counterparty inside the final document.

    Does a full removal (not just hiding the markers), so Word does not
    flag the result as damaged content:
      - drops the comment parts themselves: word/comments.xml and the
        Word 2016+ side-car parts commentsExtended.xml, commentsIds.xml,
        commentsExtensible.xml, whichever are present;
      - removes <w:commentRangeStart>, <w:commentRangeEnd> and
        <w:commentReference> from every word/*.xml part that has them
        (normally just document.xml); a <w:r> left with nothing but its
        (now-removed) commentReference is dropped too, so no empty runs
        remain;
      - removes the matching entries from [Content_Types].xml and
        word/_rels/document.xml.rels.

    Wrapped in try/except: on any error the original bytes are returned
    unchanged so the caller always gets a valid document.
    """
    import zipfile as _zipfile
    from io import BytesIO as _BytesIO
    from lxml import etree as _etree

    W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    W = f"{{{W_NS}}}"

    COMMENT_PART_NAMES = {
        "word/comments.xml",
        "word/commentsExtended.xml",
        "word/commentsIds.xml",
        "word/commentsExtensible.xml",
    }
    COMMENT_MARKERS = (b"w:commentRangeStart", b"w:commentRangeEnd", b"w:commentReference")

    def _strip_markers(xml_bytes: bytes) -> bytes:
        root = _etree.fromstring(xml_bytes)
        for tag in ("commentRangeStart", "commentRangeEnd"):
            for el in list(root.iter(f"{W}{tag}")):
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)
        for ref in list(root.iter(f"{W}commentReference")):
            run = ref.getparent()
            if run is None:
                continue
            run.remove(ref)
            if run.tag == f"{W}r" and not [c for c in run if c.tag != f"{W}rPr"]:
                grandparent = run.getparent()
                if grandparent is not None:
                    grandparent.remove(run)
        return _etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    def _strip_content_types(xml_bytes: bytes, dropped_parts: set) -> bytes:
        root = _etree.fromstring(xml_bytes)
        targets = {"/" + p for p in dropped_parts}
        for override in list(root):
            if override.tag.endswith("Override") and override.get("PartName") in targets:
                root.remove(override)
        return _etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    def _strip_rels(xml_bytes: bytes, dropped_parts: set) -> bytes:
        root = _etree.fromstring(xml_bytes)
        basenames = {p.rsplit("/", 1)[-1] for p in dropped_parts}
        for rel in list(root):
            if rel.tag.endswith("Relationship") and rel.get("Target", "").rsplit("/", 1)[-1] in basenames:
                root.remove(rel)
        return _etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    try:
        with _zipfile.ZipFile(_BytesIO(docx_bytes), "r") as zin:
            names = set(zin.namelist())
            dropped_parts = COMMENT_PART_NAMES & names
            if not dropped_parts:
                return docx_bytes  # no comments to remove

            out_buf = _BytesIO()
            with _zipfile.ZipFile(out_buf, "w", _zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    name = item.filename
                    if name in dropped_parts:
                        continue  # drop the comment part entirely
                    data = zin.read(name)
                    if name == "[Content_Types].xml":
                        data = _strip_content_types(data, dropped_parts)
                    elif name == "word/_rels/document.xml.rels":
                        data = _strip_rels(data, dropped_parts)
                    elif name.startswith("word/") and name.endswith(".xml") and any(m in data for m in COMMENT_MARKERS):
                        data = _strip_markers(data)
                    zout.writestr(item, data)
            return out_buf.getvalue()
    except Exception as _exc:
        logger.warning("_strip_word_comments: failed to strip comments, returning original: %s", _exc)
        return docx_bytes
