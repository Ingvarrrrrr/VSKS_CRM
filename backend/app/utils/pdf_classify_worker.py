"""Isolated worker process for pdf-inspector.

Reads raw PDF bytes from stdin, runs `pdf_inspector.process_pdf_bytes` on
them, and prints a single-line JSON result to stdout. MUST NOT be imported
directly into the FastAPI process — pdf-inspector parses untrusted binary
data (see its SECURITY.md: memory-safety issues and unbounded resource
allocation from malicious PDFs are in scope), so it is only ever invoked
out-of-process via `pdf_classify.inspect_pdf`.

Always exits with code 0: on any failure it prints {"error": "..."} instead of
raising, so the caller can parse stdout unconditionally.

Usage: python -m app.utils.pdf_classify_worker < document.pdf
"""
import json
import sys


def main() -> None:
    try:
        data = sys.stdin.buffer.read()
        if not data:
            print(json.dumps({"error": "no input data on stdin"}))
            return

        try:
            import pdf_inspector
        except ImportError as e:
            print(json.dumps({"error": f"pdf_inspector not installed: {e}"}))
            return

        try:
            result = pdf_inspector.process_pdf_bytes(data)
        except Exception as e:
            print(json.dumps({"error": f"process_pdf_bytes failed: {e}"}))
            return

        # PdfResult attributes per pdf-inspector 0.2.6 docs (docs/python.md):
        # pdf_type: str ("text_based"|"scanned"|"image_based"|"mixed"),
        # confidence: float, markdown: str|None, pages_needing_ocr: list[int]
        # (1-based), page_count: int, has_encoding_issues: bool. Still read via
        # getattr with a default of None — a worker crash on a missing/renamed
        # attribute in a future point release must not take down the caller.
        raw_pdf_type = getattr(result, "pdf_type", None)
        raw_confidence = getattr(result, "confidence", None)
        raw_ocr_pages = getattr(result, "pages_needing_ocr", None)
        raw_markdown = getattr(result, "markdown", None)
        raw_page_count = getattr(result, "page_count", None)
        raw_encoding_issues = getattr(result, "has_encoding_issues", None)

        out = {
            "pdf_type": str(raw_pdf_type) if raw_pdf_type is not None else None,
            "confidence": float(raw_confidence) if isinstance(raw_confidence, (int, float)) else None,
            "ocr_pages": list(raw_ocr_pages) if raw_ocr_pages is not None else None,
            "markdown": raw_markdown if isinstance(raw_markdown, str) else None,
            "page_count": int(raw_page_count) if isinstance(raw_page_count, (int, float)) else None,
            "has_encoding_issues": bool(raw_encoding_issues) if raw_encoding_issues is not None else None,
        }
        print(json.dumps(out, ensure_ascii=False))
    except Exception as e:  # last-resort guard — never crash the worker
        try:
            print(json.dumps({"error": f"worker crashed: {e}"}))
        except Exception:
            print('{"error": "worker crashed and could not serialize error"}')


if __name__ == "__main__":
    main()
