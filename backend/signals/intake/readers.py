"""Stage 1: get plain text out of an upload.

PDFs are parsed in a separate Python process with a time limit (and memory and CPU
limits on Linux, where Replit runs). A bad PDF can then only kill that process, not the
app every visitor shares. pypdf never runs JavaScript; only the text layer is read.
"""
from __future__ import annotations

import json
import subprocess
import sys

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 4
MAX_CHARS = 20_000
PDF_TIMEOUT_S = 10
MEMORY_LIMIT_BYTES = 512 * 1024 * 1024

MESSAGES = {
    "TOO_LARGE": "The file is larger than 5 MB.",
    "NOT_PDF": "This is not a PDF file.",
    "ENCRYPTED": "The PDF is password-protected. Paste the text instead.",
    "TOO_MANY_PAGES": f"The PDF has more than {MAX_PAGES} pages.",
    "TOO_LONG": f"The CV is longer than {MAX_CHARS:,} characters.",
    "NO_TEXT": "No text was found. It may be a scanned PDF. Paste the text instead.",
    "UNREADABLE": "The PDF could not be read. Paste the text instead.",
    "TIMEOUT": "Reading the PDF took too long. Paste the text instead.",
    "NOT_UTF8": "The text file is not UTF-8. Save it as UTF-8 or paste the text.",
    "UNSUPPORTED": "Upload a PDF, .txt or .md file.",
    "EMPTY": "The CV is empty.",
}

# Runs in the child process. Exit codes tell the parent what went wrong without parsing text.
_CHILD = r"""
import io, json, os, sys
if os.name == "posix":
    import resource
    limit = int(sys.argv[3])
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    resource.setrlimit(resource.RLIMIT_CPU, (int(sys.argv[4]), int(sys.argv[4])))
from pypdf import PdfReader
max_pages, max_chars = int(sys.argv[1]), int(sys.argv[2])
reader = PdfReader(io.BytesIO(sys.stdin.buffer.read()), strict=True)
if reader.is_encrypted:
    sys.exit(3)
if len(reader.pages) > max_pages:
    sys.exit(4)
parts, total = [], 0
for page in reader.pages:
    text = page.extract_text() or ""
    total += len(text)
    if total > max_chars * 2:
        sys.exit(5)
    parts.append(text)
sys.stdout.write(json.dumps({"text": "\n".join(parts)}))
"""
_EXIT_CODES = {3: "ENCRYPTED", 4: "TOO_MANY_PAGES", 5: "TOO_LONG"}


class ReadError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
        self.message = MESSAGES.get(code, MESSAGES["UNREADABLE"])


def read_pdf(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise ReadError("TOO_LARGE")
    if not data.startswith(b"%PDF-"):
        raise ReadError("NOT_PDF")
    command = [sys.executable, "-I", "-c", _CHILD, str(MAX_PAGES), str(MAX_CHARS),
               str(MEMORY_LIMIT_BYTES), str(PDF_TIMEOUT_S)]
    try:
        result = subprocess.run(command, input=data, capture_output=True, timeout=PDF_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        raise ReadError("TIMEOUT") from None
    if result.returncode != 0:
        raise ReadError(_EXIT_CODES.get(result.returncode, "UNREADABLE"))
    try:
        text = json.loads(result.stdout.decode("utf-8"))["text"]
    except (ValueError, KeyError):
        raise ReadError("UNREADABLE") from None
    if not text.strip():
        raise ReadError("NO_TEXT")
    return text


def read_text(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise ReadError("TOO_LARGE")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ReadError("NOT_UTF8") from None
    if not text.strip():
        raise ReadError("EMPTY")
    return text


def read_upload(file_name: str, data: bytes) -> str:
    """Pick the reader from the file extension. The PDF reader also checks the magic bytes."""
    lower = file_name.lower()
    if lower.endswith(".pdf"):
        return read_pdf(data)
    if lower.endswith((".txt", ".md")):
        return read_text(data)
    raise ReadError("UNSUPPORTED")
