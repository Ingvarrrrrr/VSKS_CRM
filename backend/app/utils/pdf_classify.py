"""PDF classification via pdf-inspector, run out-of-process for safety.

Determines which pages of a PDF actually need OCR, replacing the current naive
heuristic ("extracted text is empty" == scanned). pdf-inspector parses
untrusted binary PDF data and is young code (first release March 2026); its
own SECURITY.md lists memory-safety issues from malicious PDFs and DoS via
unbounded resource allocation as in-scope risks. To keep the FastAPI process
safe, the library is NEVER imported here — it only runs inside a short-lived
subprocess (see pdf_classify_worker.py), fed over stdin, with a wall-clock
timeout and (on POSIX) an address-space limit. Do not "optimize" this by
importing pdf_inspector in-process — the isolation is the point.

Callers MUST check `PdfInspection.ok`; when False, fall back to the existing
OCR/extraction path unconditionally.
"""
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Wall-clock timeout for the classification subprocess.
WORKER_TIMEOUT_SECONDS = 20.0

# Address-space limit for the worker process (POSIX only — see _limit_worker_memory).
# RLIMIT_AS caps VIRTUAL address space, not resident memory (RSS) — the two are
# very different for this worker. CPython itself plus a Rust library that uses
# rayon (a thread pool sized to the CPU count, each thread carrying its own
# reserved stack) can reserve several hundred MB of virtual address space
# before touching a single real page. A tight 512 MB cap made the worker hit
# RLIMIT_AS and die on effectively every invocation, and inspect_pdf's fallback
# is silent — so classification quietly never ran. 2 GB still bounds runaway
# allocation from a malicious/malformed PDF, it just no longer collides with
# normal interpreter + rayon overhead.
WORKER_MEMORY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024

# Above this size we skip classification entirely rather than hand a huge
# file to a young, untrusted-input parser.
MAX_CONTENT_BYTES = 60 * 1024 * 1024

# Directory containing the `app` package (backend/), used as the worker
# subprocess's cwd/PYTHONPATH so `python -m app.utils.pdf_classify_worker`
# resolves regardless of the parent process's own working directory.
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Module-level counter of consecutive inspect_pdf failures, used to escalate
# a silent-but-persistent breakage (e.g. pdf-inspector missing on the server)
# from a warning to an error after it has failed repeatedly in a row.
_consecutive_failures = 0


def _note_inspect_failure(error: str) -> None:
    """Track a consecutive inspect_pdf failure; escalate once it repeats.

    A single failure is unremarkable (one bad PDF). Three or more in a row
    means classification is not working at all and every PDF is silently
    falling back to the legacy OCR/extraction path — that deserves an error
    log, not a warning that scrolls by unnoticed.
    """
    global _consecutive_failures
    _consecutive_failures += 1
    if _consecutive_failures >= 3:
        logger.error(
            "inspect_pdf: %d consecutive classification failures — PDF classification "
            "is not working, all PDFs are falling back to the legacy path. Last error: %s",
            _consecutive_failures, error,
        )


def _note_inspect_success() -> None:
    global _consecutive_failures
    _consecutive_failures = 0


@dataclass
class PdfInspection:
    pdf_type: str = "unknown"          # 'text' | 'scanned' | 'image' | 'mixed' | 'unknown'
    confidence: float = 0.0            # 0.0 если неизвестно
    ocr_pages: list = field(default_factory=list)  # 1-based номера страниц, которым нужен OCR
    markdown: str | None = None        # markdown от pdf-inspector, если он его дал
    page_count: int = 0                # 0 если неизвестно
    has_encoding_issues: bool = False  # битая кодировка шрифта → текстовый слой это мусор
    ok: bool = False                   # False = классификация не удалась, откатываемся на старый путь
    error: str | None = None


def _normalize_pdf_type(raw) -> str:
    """Map a pdf-inspector pdf_type label onto our narrow vocabulary.

    pdf-inspector 0.2.6 returns plain snake_case strings: "text_based",
    "scanned", "image_based", "mixed" (see docs/python.md). Those exact
    values are checked first; a compact (no underscores/hyphens) substring
    match is kept as a fallback in case a future point release changes casing.
    image_based is checked before the text_based/"text" substring check so a
    value like "image_based" can never be mis-matched as containing "text".
    """
    if not raw:
        return "unknown"
    text = str(raw).strip()
    lower = text.lower()

    if lower == "image_based":
        return "image"
    if lower == "text_based":
        return "text"
    if lower == "scanned":
        return "scanned"
    if lower == "mixed":
        return "mixed"

    # Fallback for CamelCase/hyphenated variants — order matters: image before text.
    compact = lower.replace("_", "").replace("-", "")
    if "imagebased" in compact or compact == "image":
        return "image"
    if "scanned" in compact:
        return "scanned"
    if "mixed" in compact:
        return "mixed"
    if "textbased" in compact or compact == "text":
        return "text"
    return "unknown"


def _limit_worker_memory():
    """preexec_fn for subprocess.run: cap RLIMIT_AS on POSIX. No-op elsewhere.

    Windows has no `resource` module and subprocess.run doesn't support
    preexec_fn there at all, so this must never be wired in on win32.
    """
    import resource
    try:
        resource.setrlimit(
            resource.RLIMIT_AS,
            (WORKER_MEMORY_LIMIT_BYTES, WORKER_MEMORY_LIMIT_BYTES),
        )
    except Exception:
        # Best-effort: some environments (containers without the cap) may reject this.
        pass


def inspect_pdf(content: bytes, timeout: float = WORKER_TIMEOUT_SECONDS) -> PdfInspection:
    """Classify a PDF (text/scanned/image/mixed) in an isolated subprocess.

    Never raises. Any failure (timeout, missing library, malformed output,
    oversized input) yields PdfInspection(ok=False, error=...).
    """
    if not content:
        _note_inspect_failure("empty content")
        return PdfInspection(ok=False, error="empty content")

    if len(content) > MAX_CONTENT_BYTES:
        msg = f"PDF слишком большой для классификации ({len(content)} байт > {MAX_CONTENT_BYTES})"
        logger.warning("inspect_pdf: %s", msg)
        _note_inspect_failure(msg)
        return PdfInspection(ok=False, error=msg)

    try:
        preexec_fn = _limit_worker_memory if sys.platform != "win32" else None

        # Explicit cwd + PYTHONPATH: don't rely on the parent process's cwd
        # being the package root — `-m app.utils.pdf_classify_worker` only
        # resolves if `app` is importable from the subprocess's working dir.
        worker_env = os.environ.copy()
        existing_pythonpath = worker_env.get("PYTHONPATH", "")
        worker_env["PYTHONPATH"] = (
            _BACKEND_ROOT + os.pathsep + existing_pythonpath
            if existing_pythonpath else _BACKEND_ROOT
        )

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "app.utils.pdf_classify_worker"],
                input=content,
                capture_output=True,
                timeout=timeout,
                preexec_fn=preexec_fn,
                cwd=_BACKEND_ROOT,
                env=worker_env,
            )
        except subprocess.TimeoutExpired:
            logger.warning("inspect_pdf: worker timed out after %ss", timeout)
            _note_inspect_failure(f"worker timed out after {timeout}s")
            return PdfInspection(ok=False, error=f"классификация PDF превысила таймаут ({timeout}с)")
        except Exception as e:
            logger.warning("inspect_pdf: failed to launch worker: %s", e)
            _note_inspect_failure(f"failed to launch worker: {e}")
            return PdfInspection(ok=False, error=f"не удалось запустить классификатор PDF: {e}")

        stdout = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
        if not stdout:
            logger.warning(
                "inspect_pdf: worker produced no stdout (returncode=%s, stderr=%s)",
                proc.returncode, (proc.stderr or b"").decode("utf-8", errors="replace")[:500],
            )
            _note_inspect_failure(f"worker produced no stdout (returncode={proc.returncode})")
            return PdfInspection(ok=False, error="классификатор PDF не вернул результат")

        # Worker may print extra lines (warnings from native deps) before the JSON —
        # take the last non-empty line, which is where main() prints its result.
        last_line = stdout.splitlines()[-1]
        try:
            data = json.loads(last_line)
        except Exception as e:
            logger.warning("inspect_pdf: could not parse worker output as JSON: %s", e)
            _note_inspect_failure(f"could not parse worker output as JSON: {e}")
            return PdfInspection(ok=False, error=f"мусор в выводе классификатора PDF: {e}")

        if not isinstance(data, dict):
            _note_inspect_failure("worker returned non-dict JSON")
            return PdfInspection(ok=False, error="классификатор PDF вернул неожиданный формат")

        if data.get("error"):
            logger.warning("inspect_pdf: worker reported error: %s", data["error"])
            _note_inspect_failure(str(data["error"]))
            return PdfInspection(ok=False, error=str(data["error"]))

        raw_ocr_pages = data.get("ocr_pages") or []
        ocr_pages: list[int] = []
        if isinstance(raw_ocr_pages, list):
            for p in raw_ocr_pages:
                try:
                    ocr_pages.append(int(p))
                except (TypeError, ValueError):
                    continue

        raw_confidence = data.get("confidence")
        confidence = float(raw_confidence) if isinstance(raw_confidence, (int, float)) else 0.0

        markdown = data.get("markdown")
        markdown = markdown if isinstance(markdown, str) else None

        raw_page_count = data.get("page_count")
        page_count = int(raw_page_count) if isinstance(raw_page_count, (int, float)) else 0

        raw_encoding_issues = data.get("has_encoding_issues")
        has_encoding_issues = bool(raw_encoding_issues) if raw_encoding_issues is not None else False

        _note_inspect_success()
        return PdfInspection(
            pdf_type=_normalize_pdf_type(data.get("pdf_type")),
            confidence=confidence,
            ocr_pages=ocr_pages,
            markdown=markdown,
            page_count=page_count,
            has_encoding_issues=has_encoding_issues,
            ok=True,
            error=None,
        )
    except Exception as e:
        logger.warning("inspect_pdf: unexpected failure: %s", e)
        _note_inspect_failure(f"unexpected failure: {e}")
        return PdfInspection(ok=False, error=f"неожиданная ошибка классификации PDF: {e}")


def needs_ocr(insp: PdfInspection) -> bool:
    """True if the inspected PDF (or any of its pages) likely needs OCR.

    A broken font encoding makes a text layer garbage even when pdf-inspector
    classifies the document as 'text' — that case must still be routed to OCR.
    """
    if insp.pdf_type in ("scanned", "image", "mixed"):
        return True
    if insp.has_encoding_issues:
        return True
    if insp.ocr_pages:
        return True
    return False
