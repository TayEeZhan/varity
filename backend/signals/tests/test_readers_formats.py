import io
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


@pytest.mark.parametrize("data", [b"{\\rtf1 unclosed", b"not rtf", b"{\\rtf1 x}}"])
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
        read_upload("cv.docx", docx("<w:p><w:r><w:t>hello hello hello</w:t></w:r></w:p>"))
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
