import io
import time
import zipfile

import pytest

from intake import readers
from intake.readers import ReadError, read_upload

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
T = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


def make_zip(member: str, xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member, xml)
    return buf.getvalue()


def docx(body: str) -> bytes:
    return make_zip("word/document.xml", f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>')


def test_docx_paragraphs_and_tab():
    data = docx("<w:p><w:r><w:t>Jane Doe</w:t><w:tab/><w:t>Dev</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>Python</w:t><w:br/><w:t>SQL</w:t></w:r></w:p>")
    assert read_upload("CV.DOCX", data) == "Jane Doe\tDev\nPython\nSQL"


def test_odt_paragraphs_and_tab():
    xml = (f'<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="{T}">'
           '<office:body><office:text><text:h>Jane Doe</text:h>'
           '<text:p>Python<text:tab/>SQL<text:s text:c="2"/>Go<text:line-break/>Rust</text:p>'
           '</office:text></office:body></office:document-content>')
    assert read_upload("cv.odt", make_zip("content.xml", xml)) == "Jane Doe\nPython\tSQL  Go\nRust"


def test_rtf_escapes_and_skipped_groups():
    bs = b"\\"
    rtf = rb"{\rtf1\ansi{\fonttbl{\f0 Arial;}}{\*\generator Word;}Caf\'e9\par It" + bs + b"u8217?s" + rb"\tab ok}"
    assert read_upload("cv.rtf", rtf) == "Caf" + chr(0xE9) + "\nIt" + chr(0x2019) + "s\tok"


def test_rtf_line_breaks_code_pages_and_trailing_nul():
    # Shaped like WordPad / RichTextBox output: CRLF after control words, SimSun bytes, a NUL after the end.
    rtf = (rb"{\rtf1\ansi\ansicpg1252{\fonttbl{\f0\fnil\fcharset0 Calibri;}{\f1\fnil\fcharset134 SimSun;}}" b"\r\n"
           rb"\pard\f0 Python\par" b"\r\n" rb"Caf\'e9 \emdash  \f1\'d6\'d0\'ce\'c4\f0\par" b"\r\n}\r\n\0")
    assert read_upload("cv.rtf", rtf) == "Python\nCaf" + chr(0xE9) + " " + chr(0x2014) + " " + chr(0x4E2D) + chr(0x6587) + "\n"


@pytest.mark.parametrize("data", [b"{\\rtf1 unclosed", b"not rtf", b"{\\rtf1 x}}", b"{\\rtf1 x} trailing"])
def test_rtf_malformed(data):
    with pytest.raises(ReadError) as e:
        read_upload("cv.rtf", data)
    assert e.value.code == "UNREADABLE"


def test_html_drops_script_and_style():
    html = (b"<html><style>p{x:y}</style><script>alert(1)</script><h1>Jane</h1>"
            b"<p>R&amp;D &eacute;</p><ul><li>One</li><li>Two</li></ul></html>")
    assert read_upload("cv.htm", html).strip() == "Jane\nR&D " + chr(0xE9) + "\nOne\nTwo"


def test_zip_bomb_rejected(monkeypatch):
    monkeypatch.setattr(readers, "MAX_XML_BYTES", 10)
    with pytest.raises(ReadError) as e:
        readers._parse_docx(docx("<w:p><w:r><w:t>hello hello hello</w:t></w:r></w:p>"))  # in-process: patch must apply
    assert e.value.code == "UNSAFE"


def test_zip_declared_size_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<a/>")
    data = bytearray(buf.getvalue())
    # Declare a 11 MB uncompressed size in both the local and central headers.
    big = (11 * 1024 * 1024).to_bytes(4, "little")
    for sig, off in ((b"PK\x01\x02", 24), (b"PK\x03\x04", 22)):
        i = data.index(sig)
        data[i + off:i + off + 4] = big
    with pytest.raises(ReadError) as e:
        read_upload("cv.docx", bytes(data))
    assert e.value.code == "UNSAFE"


def test_doctype_rejected():
    xml = f'<!DOCTYPE x [<!ENTITY a "b">]><w:document xmlns:w="{W}"><w:body/></w:document>'
    with pytest.raises(ReadError) as e:
        read_upload("cv.docx", make_zip("word/document.xml", xml))
    assert e.value.code == "UNSAFE"


def test_not_a_zip_and_missing_member():
    for data in (b"plain", make_zip("other.xml", "<a/>")):
        with pytest.raises(ReadError) as e:
            read_upload("cv.docx", data)
        assert e.value.code == "UNREADABLE"


def test_empty_docx_has_no_text():
    with pytest.raises(ReadError) as e:
        read_upload("cv.docx", docx("<w:p/>"))
    assert e.value.code == "NO_TEXT"


def test_old_doc_and_unknown_extension():
    with pytest.raises(ReadError) as e:
        read_upload("cv.doc", b"\xd0\xcf\x11\xe0")
    assert e.value.code == "OLD_DOC"
    assert e.value.message == "Old .doc files are not supported. Save it as .docx or PDF and try again."
    with pytest.raises(ReadError) as e:
        read_upload("cv.exe", b"x")
    assert e.value.message == "Upload a PDF, Word (.docx), OpenDocument (.odt), RTF, HTML or text (.txt, .md) file."


BS = chr(92)


def rtf(body: str) -> bytes:
    return (("{" + BS + "rtf1" + BS + "ansi ") + body.replace("~", BS) + "}").encode("latin-1")


def code_of(name: str, data: bytes) -> str:
    with pytest.raises(ReadError) as e:
        read_upload(name, data)
    return e.value.code


def test_html_quadratic_input_is_bounded():
    start = time.monotonic()
    try:
        read_upload("cv.html", b"<a" * 200_000)
    except ReadError as e:
        assert e.code in ("TIMEOUT", "UNREADABLE", "NO_TEXT")
    assert time.monotonic() - start < 15


def test_deeply_nested_runs_do_not_crash():
    n = 5000
    assert read_upload("cv.docx", docx("<w:p>" + "<w:r>" * n + "<w:t>deep</w:t>" + "</w:r>" * n + "</w:p>")) == "deep"


def test_corrupt_deflate_stream_is_unreadable():
    data = bytearray(docx("<w:p><w:r><w:t>" + "hello " * 500 + "</w:t></w:r></w:p>"))
    i = data.index(b"PK") + 30 + len("word/document.xml")  # start of the deflate stream
    data[i:i + 8] = bytes([255]) * 8
    assert code_of("cv.docx", bytes(data)) == "UNREADABLE"
    with pytest.raises(ReadError):  # also the direct (in-process) parser: zlib.error is mapped
        readers._parse_docx(bytes(data))


def test_rtf_huge_unicode_number_is_read_not_crash():
    assert read_upload("cv.rtf", rtf("a~u" + "9" * 5000 + "?b")).startswith("a")


def test_rtf_negative_unicode_joins_surrogate_pairs_and_never_leaves_lone_ones():
    assert read_upload("cv.rtf", rtf("A~u-10179?~u-8704?B")) == "A" + chr(0x1F600) + "B"
    text = read_upload("cv.rtf", rtf("A~u-10179?B"))
    text.encode("utf-8")  # a lone surrogate would raise here
    assert text == "A" + chr(0xFFFD) + "B"


def test_rtf_backslash_newline_is_a_paragraph_break():
    assert read_upload("cv.rtf", rtf("Hello~" + chr(10) + "World")) == "Hello\nWorld"


def test_docx_nested_paragraphs_and_fallback_emit_text_once():
    mc = "http://schemas.openxmlformats.org/markup-compatibility/2006"
    xml = (f'<w:document xmlns:w="{W}" xmlns:mc="{mc}"><w:body><w:p><w:r><w:t>Outer</w:t></w:r>'
           '<mc:AlternateContent><mc:Choice><w:p><w:r><w:t>Box</w:t></w:r></w:p></mc:Choice>'
           '<mc:Fallback><w:p><w:r><w:t>Box</w:t></w:r></w:p></mc:Fallback></mc:AlternateContent>'
           '<w:r><w:t>End</w:t></w:r></w:p></w:body></w:document>')
    assert read_upload("cv.docx", make_zip("word/document.xml", xml)) == "OuterEnd\nBox"


def test_many_empty_paragraphs_rejected_by_xml_cap():
    assert code_of("cv.docx", docx("<w:p/>" * 400_000)) == "UNSAFE"
