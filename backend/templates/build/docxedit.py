import io
import re
import zipfile
from datetime import datetime
from typing import Callable

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML = "http://www.w3.org/XML/1998/namespace"

_W = f"{{{W}}}"

_FIXED_MTIME = (2024, 1, 1, 0, 0, 0)

_COMMENT_PARTS = {
    "word/comments.xml",
    "word/commentsExtended.xml",
    "word/commentsIds.xml",
    "word/commentsExtensible.xml",
}

_COMMENT_TARGETS = {
    "comments.xml",
    "commentsExtended.xml",
    "commentsIds.xml",
    "commentsExtensible.xml",
}


def _tag(local: str) -> str:
    return f"{_W}{local}"


def normalize(root: etree._Element) -> None:
    """
    Принимаем tracked changes и чистим мусор ДО любых правок.
    Tracked changes — корневая причина дробления runs в исходных образцах:
    Word при наличии <w:ins>/<w:del> разбивает соседние run-ы на границах правок.
    """
    ns = {"w": W}

    for ins in root.findall(".//w:ins", ns):
        parent = ins.getparent()
        if parent is None:
            continue
        idx = list(parent).index(ins)
        for child in list(ins):
            ins.remove(child)
            parent.insert(idx, child)
            idx += 1
        parent.remove(ins)

    for del_el in root.findall(".//w:del", ns):
        p = del_el.getparent()
        if p is not None:
            p.remove(del_el)

    for tag in ("proofErr", "bookmarkStart", "bookmarkEnd",
                "commentRangeStart", "commentRangeEnd"):
        for el in root.findall(f".//w:{tag}", ns):
            p = el.getparent()
            if p is not None:
                p.remove(el)

    for r in root.findall(".//w:r", ns):
        if r.find("w:commentReference", ns) is not None:
            p = r.getparent()
            if p is not None:
                p.remove(r)

    for lang in root.findall(".//w:rPr/w:lang", ns):
        rpr = lang.getparent()
        if rpr is not None:
            rpr.remove(lang)

    for para in root.findall(".//w:p", ns):
        _merge_runs(para)


def _rpr_key(r: etree._Element) -> str:
    rpr = r.find(f"{_W}rPr")
    if rpr is None:
        return ""
    return etree.tostring(rpr, encoding="unicode")


def _merge_runs(para: etree._Element) -> None:
    runs = [child for child in para if child.tag == _tag("r")]
    if len(runs) < 2:
        return

    i = 0
    while i < len(runs) - 1:
        cur = runs[i]
        nxt = runs[i + 1]

        if cur.getparent() is not para or nxt.getparent() is not para:
            i += 1
            continue

        if _rpr_key(cur) != _rpr_key(nxt):
            i += 1
            continue

        cur_t = cur.find(f"{_W}t")
        nxt_t = nxt.find(f"{_W}t")

        if cur_t is None or nxt_t is None:
            i += 1
            continue

        has_non_text_cur = any(
            child.tag not in (f"{_W}rPr", f"{_W}t") for child in cur
        )
        has_non_text_nxt = any(
            child.tag not in (f"{_W}rPr", f"{_W}t") for child in nxt
        )
        if has_non_text_cur or has_non_text_nxt:
            i += 1
            continue

        combined = (cur_t.text or "") + (nxt_t.text or "")
        cur_t.text = combined
        cur_t.set(f"{{{XML}}}space", "preserve")

        para.remove(nxt)
        runs.pop(i + 1)


def para_text(p: etree._Element) -> str:
    parts: list[str] = []
    for el in p.iter():
        if el.tag == _tag("t"):
            parts.append(el.text or "")
        elif el.tag == _tag("tab"):
            parts.append("\t")
        elif el.tag in (_tag("br"), _tag("cr")):
            parts.append("\n")
    return "".join(parts)


def _build_char_map(p: etree._Element):
    """
    Returns list of (w:t node, global_char_start, global_char_end).
    tab/br/cr each occupy 1 position but cannot be split.
    """
    entries = []
    pos = 0
    for el in p.iter():
        if el.tag == _tag("t"):
            text = el.text or ""
            if text:
                entries.append((el, pos, pos + len(text)))
                pos += len(text)
        elif el.tag in (_tag("tab"), _tag("br"), _tag("cr")):
            pos += 1
    return entries


def replace_in_para(p: etree._Element, start: int, end: int, replacement: str) -> None:
    if start >= end:
        return

    char_map = _build_char_map(p)

    touched = [
        (node, cs, ce)
        for node, cs, ce in char_map
        if cs < end and ce > start
    ]
    if not touched:
        return

    for node, cs, ce in touched:
        local_start = max(start - cs, 0)
        local_end = min(end - cs, ce - cs)
        text = node.text or ""

        if cs < end and ce > start:
            if not (node.tag == _tag("t")):
                raise ValueError(
                    f"Replacement span [{start}, {end}) crosses a non-text element at pos {cs}"
                )

        before = text[:local_start]
        after = text[local_end:]

        if node is touched[0][0]:
            node.text = before + replacement + (after if len(touched) == 1 else "")
        else:
            node.text = after

        node.set(f"{{{XML}}}space", "preserve")


def apply_rules(p: etree._Element, rules: list) -> int:
    total = 0
    for pattern, repl in rules:
        text = para_text(p)
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        for m in reversed(matches):
            if callable(repl):
                replacement = repl(m)
            else:
                replacement = m.expand(repl)
            replace_in_para(p, m.start(), m.end(), replacement)
            total += 1
    return total


def _copy_ppr(src: etree._Element) -> etree._Element | None:
    ppr = src.find(f"{_W}pPr")
    if ppr is None:
        return None
    import copy
    return copy.deepcopy(ppr)


def _make_para(text: str, ppr: etree._Element | None = None) -> etree._Element:
    p = etree.Element(f"{_W}p")
    if ppr is not None:
        p.append(ppr)
    r = etree.SubElement(p, f"{_W}r")
    t = etree.SubElement(r, f"{_W}t")
    t.text = text
    if text and (text[0] == " " or text[-1] == " "):
        t.set(f"{{{XML}}}space", "preserve")
    return p


def insert_para_before(p: etree._Element, text: str) -> etree._Element:
    parent = p.getparent()
    idx = list(parent).index(p)
    ppr = _copy_ppr(p)
    new_p = _make_para(text, ppr)
    parent.insert(idx, new_p)
    return new_p


def insert_para_after(p: etree._Element, text: str) -> etree._Element:
    parent = p.getparent()
    idx = list(parent).index(p)
    ppr = _copy_ppr(p)
    new_p = _make_para(text, ppr)
    parent.insert(idx + 1, new_p)
    return new_p


def load(path: str) -> tuple[dict[str, bytes], etree._Element]:
    zip_bytes: dict[str, bytes] = {}
    with zipfile.ZipFile(path, "r") as zf:
        for name in zf.namelist():
            zip_bytes[name] = zf.read(name)

    doc_xml = zip_bytes["word/document.xml"]
    root = etree.fromstring(doc_xml)
    return zip_bytes, root


def _strip_comment_rels(xml_bytes: bytes) -> bytes:
    try:
        tree = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return xml_bytes

    rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    to_remove = []
    for rel in tree.findall(f"{{{rels_ns}}}Relationship"):
        target = rel.get("Target", "").split("/")[-1]
        if target in _COMMENT_TARGETS:
            to_remove.append(rel)
    for rel in to_remove:
        rel.getparent().remove(rel)

    return etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)


def _strip_comment_content_types(xml_bytes: bytes) -> bytes:
    try:
        tree = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return xml_bytes

    ct_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    to_remove = []
    for el in tree:
        part_name = el.get("PartName", "")
        clean = part_name.lstrip("/")
        if clean in _COMMENT_PARTS:
            to_remove.append(el)
    for el in to_remove:
        el.getparent().remove(el)

    return etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)


def save(zip_bytes: dict[str, bytes], root: etree._Element, out_path: str) -> None:
    doc_xml = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    fixed_dt = datetime(*_FIXED_MTIME)

    rels_key = "word/_rels/document.xml.rels"
    ct_key = "[Content_Types].xml"

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(zip_bytes.keys()):
            if name in _COMMENT_PARTS:
                continue

            if name == "word/document.xml":
                data = doc_xml
            elif name == rels_key and rels_key in zip_bytes:
                data = _strip_comment_rels(zip_bytes[name])
            elif name == ct_key:
                data = _strip_comment_content_types(zip_bytes[name])
            else:
                data = zip_bytes[name]

            zi = zipfile.ZipInfo(name, date_time=_FIXED_MTIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, data)
