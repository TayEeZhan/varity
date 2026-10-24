"""Stage 1: get plain text out of an upload.

PDFs are parsed in a separate Python process with a time limit (and memory and CPU
limits on Linux, where Replit runs). A bad PDF can then only kill that process, not the
app every visitor shares. pypdf never runs JavaScript; only the text layer is read.
"""
from __future__ import annotations

import html.parser
import io
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

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
    "UNREADABLE": "The file could not be read. Paste the text instead.",
    "OLD_DOC": "Old .doc files are not supported. Save it as .docx or PDF and try again.",
    "UNSAFE": "The file is too large, encrypted or malformed to read safely. Paste the text instead.",
    "TIMEOUT": "Reading the PDF took too long. Paste the text instead.",
    "NOT_UTF8": "The text file is not UTF-8. Save it as UTF-8 or paste the text.",
    "UNSUPPORTED": "Upload a PDF, Word (.docx), OpenDocument (.odt), RTF, HTML or text (.txt, .md) file.",
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


# The formats below are pure-Python parsers run in-process (no subprocess): every input is
# bounded by MAX_BYTES, the zip limits and MAX_CHARS, and the parsers are linear-time.
MAX_ZIP_ENTRIES = 2_000
MAX_XML_BYTES = 10 * 1024 * 1024
MAX_ZIP_TOTAL = 50 * 1024 * 1024
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_T = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


def _finish(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > MAX_CHARS * 2:
        raise ReadError("TOO_LONG")
    if not text.strip():
        raise ReadError("NO_TEXT")
    return text


def _zip_xml(data: bytes, member: str) -> ET.Element:
    if len(data) > MAX_BYTES:
        raise ReadError("TOO_LARGE")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_ZIP_TOTAL:
                raise ReadError("UNSAFE")
            info = zf.getinfo(member)
            if info.flag_bits & 1 or info.file_size > MAX_XML_BYTES:
                raise ReadError("UNSAFE")
            with zf.open(info) as f:
                raw = f.read(MAX_XML_BYTES + 1)
    except (zipfile.BadZipFile, KeyError, NotImplementedError, RuntimeError, OSError, EOFError, ValueError):
        raise ReadError("UNREADABLE") from None
    if len(raw) > MAX_XML_BYTES:
        raise ReadError("UNSAFE")
    low = raw.lower()
    if b"<!doctype" in low or b"<!entity" in low:
        raise ReadError("UNSAFE")
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        raise ReadError("UNREADABLE") from None


def _walk(el: ET.Element, ns: str, parts: list[str], odf: bool) -> None:
    """Append the text under el. docx keeps text in w:t; odt keeps it in element text and tails."""
    if odf and el.text:
        parts.append(el.text)
    for child in el:
        tag = child.tag
        if tag == ns + "t" and not odf:
            parts.append(child.text or "")
        elif tag == ns + "tab":
            parts.append("\t")
        elif tag in (ns + "br", ns + "cr", ns + "line-break"):
            parts.append("\n")
        elif odf and tag == ns + "s":
            count = child.get(ns + "c", "1")
            parts.append(" " * (min(int(count), 100) if count.isdigit() else 1))
        else:
            _walk(child, ns, parts, odf)
        if odf and child.tail:
            parts.append(child.tail)


def _paragraphs(root: ET.Element, ns: str, names: tuple[str, ...], odf: bool) -> str:
    lines = []
    for p in root.iter():
        if p.tag in names:
            parts: list[str] = []
            _walk(p, ns, parts, odf)
            lines.append("".join(parts))
    return "\n".join(lines)


def read_docx(data: bytes) -> str:
    return _finish(_paragraphs(_zip_xml(data, "word/document.xml"), _W, (_W + "p",), False))


def read_odt(data: bytes) -> str:
    return _finish(_paragraphs(_zip_xml(data, "content.xml"), _T, (_T + "p", _T + "h"), True))


_RTF_SKIP = {"fonttbl", "colortbl", "stylesheet", "info", "pict", "header", "footer", "object",
             "themedata", "colorschememapping", "latentstyles", "datastore", "listtable",
             "listoverridetable", "rsidtbl", "generator", "xmlnstbl", "headerl", "headerr",
             "footerl", "footerr"}
_RTF_TOKEN = re.compile(r"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\([^a-zA-Z])|([{}])|([^\\{}]+)")


def read_rtf(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise ReadError("TOO_LARGE")
    if not data.lstrip().startswith(b"{\\rtf"):
        raise ReadError("UNREADABLE")
    src = data.decode("latin-1").replace("\r", "").replace("\n", "")
    out: list[str] = []
    stack: list[tuple[bool, int]] = []  # saved (skipping, \uc fallback length) per open group
    skip, uc, pending_fallback, first = False, 1, 0, False
    for m in _RTF_TOKEN.finditer(src):
        word, num, hexa, sym, brace, text = m.groups()
        if brace == "{":
            if len(stack) >= 200:
                raise ReadError("UNREADABLE")
            stack.append((skip, uc))
            first = True
            continue
        if brace == "}":
            if not stack:
                raise ReadError("UNREADABLE")
            skip, uc = stack.pop()
            continue
        opens_group, first = first, False
        if opens_group and (sym == "*" or word in _RTF_SKIP):
            skip = True
        if skip:
            continue
        if text is not None:
            cut = min(pending_fallback, len(text))
            out.append(text[cut:])
            pending_fallback -= cut
        elif hexa is not None:
            if pending_fallback:
                pending_fallback -= 1
            else:
                out.append(bytes([int(hexa, 16)]).decode("cp1252", "replace"))
        elif sym is not None:
            out.append({"~": "\u00a0", "_": "-"}.get(sym, sym if sym in "\\{}" else ""))
        elif word in ("par", "line", "sect", "page"):
            out.append("\n")
        elif word == "tab":
            out.append("\t")
        elif word == "uc":
            uc = int(num or 1)
        elif word == "u" and num:
            out.append(chr(int(num) % 65536))
            pending_fallback = uc
    if stack:
        raise ReadError("UNREADABLE")
    return _finish("".join(out))


_BLOCK_TAGS = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol",
               "table", "section", "article", "header", "footer", "blockquote"}


class _Html(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        elif tag in _BLOCK_TAGS:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        elif tag in _BLOCK_TAGS:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.out.append(data)


def read_html(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise ReadError("TOO_LARGE")
    try:
        src = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        src = data.decode("cp1252", "replace")
    parser = _Html()
    try:
        parser.feed(src)
        parser.close()
    except Exception:  # html.parser is lenient; a failure here means unusable input
        raise ReadError("UNREADABLE") from None
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(parser.out))
    return _finish(re.sub(r"( ?\n ?)+", "\n", text))


def read_upload(file_name: str, data: bytes) -> str:
    """Pick the reader from the file extension. The PDF reader also checks the magic bytes."""
    lower = file_name.lower()
    if lower.endswith(".pdf"):
        return read_pdf(data)
    if lower.endswith((".txt", ".md")):
        return read_text(data)
    if lower.endswith(".docx"):
        return read_docx(data)
    if lower.endswith(".odt"):
        return read_odt(data)
    if lower.endswith(".rtf"):
        return read_rtf(data)
    if lower.endswith((".html", ".htm")):
        return read_html(data)
    if lower.endswith(".doc"):
        raise ReadError("OLD_DOC")
    raise ReadError("UNSUPPORTED")
