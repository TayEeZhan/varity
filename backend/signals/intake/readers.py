"""Stage 1: get plain text out of an upload.

PDFs are parsed in a separate Python process with a time limit (and memory and CPU
limits on Linux, where Replit runs). A bad PDF can then only kill that process, not the
app every visitor shares. pypdf never runs JavaScript; only the text layer is read.
"""
from __future__ import annotations

import codecs
import html.parser
import io
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib

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
    "TIMEOUT": "Reading the file took too long. Paste the text instead.",
    "NOT_UTF8": "The text file is not UTF-8. Save it as UTF-8 or paste the text.",
    "UNSUPPORTED": "Upload a PDF, Word (.docx), OpenDocument (.odt), RTF, HTML or text (.txt, .md) file.",
    "EMPTY": "The CV is empty.",
}

# Runs in the child process. Exit codes tell the parent what went wrong without parsing text.
_LIMITS = r"""
import io, json, os, sys
if os.name == "posix":
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (int(sys.argv[-2]), int(sys.argv[-2])))
    resource.setrlimit(resource.RLIMIT_CPU, (int(sys.argv[-1]), int(sys.argv[-1])))
"""
_CHILD = _LIMITS + r"""
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
# docx/odt/rtf/html: load this file in the child and run one of the _parse_* functions below.
_CHILD_DOC = _LIMITS + r"""
import importlib.util
spec = importlib.util.spec_from_file_location("_readers_child", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
try:
    out = {"text": getattr(mod, "_parse_" + sys.argv[2])(sys.stdin.buffer.read())}
except mod.ReadError as e:
    out = {"error": e.code}
sys.stdout.write(json.dumps(out))
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
    return _run_child(_CHILD, [str(MAX_PAGES), str(MAX_CHARS)], data)


def _run_child(code: str, args: list[str], data: bytes) -> str:
    command = [sys.executable, "-I", "-c", code, *args, str(MEMORY_LIMIT_BYTES), str(PDF_TIMEOUT_S)]
    try:
        result = subprocess.run(command, input=data, capture_output=True, timeout=PDF_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        raise ReadError("TIMEOUT") from None
    except Exception:
        raise ReadError("UNREADABLE") from None
    if result.returncode != 0:
        raise ReadError(_EXIT_CODES.get(result.returncode, "UNREADABLE"))
    try:
        out = json.loads(result.stdout.decode("utf-8"))
        text = out.get("text")
    except (ValueError, AttributeError):
        raise ReadError("UNREADABLE") from None
    if "error" in out:
        raise ReadError(str(out["error"]))
    if not isinstance(text, str):
        raise ReadError("UNREADABLE")
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


# The formats below are pure-Python parsers. They run in the sandboxed child (see _CHILD_DOC)
# because html.parser can be quadratic on hostile input; the _parse_* functions do the work there.
MAX_ZIP_ENTRIES = 2_000
MAX_XML_BYTES = 2 * 1024 * 1024
MAX_ZIP_TOTAL = 50 * 1024 * 1024
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
_T = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


def _finish(text: str) -> str:
    text = text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")  # no lone surrogates
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
    except (zipfile.BadZipFile, KeyError, NotImplementedError, RuntimeError, OSError, EOFError, ValueError, zlib.error):
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


def _text(p: ET.Element, ns: str, names: tuple[str, ...], odf: bool) -> str:
    """Text of one paragraph, iteratively. Nested paragraphs and mc:Fallback are left out here;
    nested paragraphs are emitted on their own by _paragraphs. docx keeps text in w:t; odt in text and tails."""
    parts: list[str] = []
    stack: list = [p]  # elements to visit, or strings (odt text/tails) to emit
    while stack:
        el = stack.pop()
        if isinstance(el, str):
            parts.append(el)
            continue
        tag = el.tag
        if el is not p and (tag in names or tag == _MC + "Fallback"):
            continue
        if tag == ns + "t" and not odf:
            parts.append(el.text or "")
        elif tag == ns + "tab":
            parts.append("\t")
        elif tag in (ns + "br", ns + "cr", ns + "line-break"):
            parts.append("\n")
        elif odf and tag == ns + "s":
            count = el.get(ns + "c", "1")
            parts.append(" " * (min(int(count), 100) if count.isdigit() else 1))
        else:
            for child in reversed(el):
                if odf and child.tail:
                    stack.append(child.tail)
                stack.append(child)
            if odf and el.text:
                stack.append(el.text)
    return "".join(parts)


def _paragraphs(root: ET.Element, ns: str, names: tuple[str, ...], odf: bool) -> str:
    lines, stack = [], [root]
    while stack:
        el = stack.pop()
        if el.tag == _MC + "Fallback":
            continue
        if el.tag in names:
            lines.append(_text(el, ns, names, odf))
        stack.extend(reversed(el))
    return "\n".join(lines)


def _parse_docx(data: bytes) -> str:
    return _finish(_paragraphs(_zip_xml(data, "word/document.xml"), _W, (_W + "p",), False))


def _parse_odt(data: bytes) -> str:
    return _finish(_paragraphs(_zip_xml(data, "content.xml"), _T, (_T + "p", _T + "h"), True))


_RTF_SKIP = {"fonttbl", "colortbl", "stylesheet", "info", "pict", "header", "footer", "object",
             "themedata", "colorschememapping", "latentstyles", "datastore", "listtable",
             "listoverridetable", "rsidtbl", "generator", "xmlnstbl", "headerl", "headerr",
             "footerl", "footerr"}
# Font charset -> code page, for \'xx bytes in a font such as SimSun (\fcharset134).
_RTF_CHARSETS = {128: "cp932", 129: "cp949", 134: "gbk", 136: "big5", 161: "cp1253", 162: "cp1254",
                 177: "cp1255", 178: "cp1256", 186: "cp1257", 204: "cp1251", 222: "cp874", 238: "cp1250"}
_RTF_CHARS = {"emdash": "—", "endash": "–", "bullet": "•", "lquote": "‘", "rquote": "’",
              "ldblquote": "“", "rdblquote": "”", "emspace": " ", "enspace": " "}
_RTF_TOKEN = re.compile(r"\\([a-zA-Z]+)(-?\d{1,9})?\d* ?|\\'([0-9a-fA-F]{2})|\\([^a-zA-Z])|([{}])|([^\\{}]+)")


def _parse_rtf(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise ReadError("TOO_LARGE")
    if not data.lstrip().startswith(b"{\\rtf"):
        raise ReadError("UNREADABLE")
    # Line breaks are ignored in RTF but still end a control word ("\par" CRLF "Caf"), so they are
    # dropped per token, not before tokenising.
    src = data.decode("latin-1")
    out: list[str] = []
    raw = bytearray()  # \'xx bytes decoded together: a double-byte (CJK) character spans two
    stack: list[tuple[bool, bool, int, str]] = []  # saved (skipping, in font table, \uc length, code page) per group
    skip, in_fonts, uc, page, default_page = False, False, 1, "cp1252", "cp1252"
    fonts: dict[int, str] = {}
    font, pending_fallback, first, closed = 0, 0, False, False
    for m in _RTF_TOKEN.finditer(src):
        word, num, hexa, sym, brace, text = m.groups()
        if text is not None:
            text = text.replace("\r", "").replace("\n", "")
            if not text or (closed and not text.strip("\0 \t")):
                continue
        if closed:  # anything but whitespace after the outer group closes
            raise ReadError("UNREADABLE")
        if hexa is None and raw:
            out.append(raw.decode(page, "replace"))
            raw.clear()
        if brace == "{":
            if len(stack) >= 200:
                raise ReadError("UNREADABLE")
            stack.append((skip, in_fonts, uc, page))
            first = True
            continue
        if brace == "}":
            if not stack:
                raise ReadError("UNREADABLE")
            skip, in_fonts, uc, page = stack.pop()
            closed = not stack
            continue
        opens_group, first = first, False
        if opens_group and word == "fonttbl":
            in_fonts = True
        if opens_group and (sym == "*" or word in _RTF_SKIP):
            skip = True
        if in_fonts:
            if word == "f" and num:
                font = int(num)
            elif word == "fcharset" and num and int(num) in _RTF_CHARSETS:
                fonts[font] = _RTF_CHARSETS[int(num)]
            continue
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
                raw.append(int(hexa, 16))
        elif sym is not None:
            out.append({"~": "\u00a0", "_": "-", "\n": "\n", "\r": "\n"}.get(sym, sym if sym in "\\{}" else ""))
        elif word in ("par", "line", "sect", "page"):
            out.append("\n")
        elif word == "tab":
            out.append("\t")
        elif word in _RTF_CHARS:
            out.append(_RTF_CHARS[word])
        elif word == "ansicpg" and num:
            page = default_page = _codec(f"cp{num}")
        elif word == "f" and num:
            page = fonts.get(int(num), default_page)
        elif word == "uc":
            uc = int(num or 1)
        elif word == "u" and num:
            out.append(chr(int(num) % 65536))  # negative N is N + 65536; surrogate pairs are joined in _finish
            pending_fallback = uc
    if stack or not closed:
        raise ReadError("UNREADABLE")
    if raw:
        out.append(raw.decode(page, "replace"))
    return _finish("".join(out))


def _codec(name: str) -> str:
    try:
        codecs.lookup(name)
        return name
    except LookupError:
        return "cp1252"


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


def _parse_html(data: bytes) -> str:
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


def _read_in_child(kind: str, data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise ReadError("TOO_LARGE")
    return _run_child(_CHILD_DOC, [__file__, kind], data)


def read_docx(data: bytes) -> str:
    return _read_in_child("docx", data)


def read_odt(data: bytes) -> str:
    return _read_in_child("odt", data)


def read_rtf(data: bytes) -> str:
    return _read_in_child("rtf", data)


def read_html(data: bytes) -> str:
    return _read_in_child("html", data)


def read_upload(file_name: str, data: bytes) -> str:
    try:
        return _dispatch(file_name, data)
    except ReadError:
        raise
    except Exception:  # never let a parser bug become an HTTP 500
        raise ReadError("UNREADABLE") from None


def _dispatch(file_name: str, data: bytes) -> str:
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
