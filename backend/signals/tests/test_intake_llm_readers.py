"""Tests for the LLM call (with a fake client) and the upload readers (with real tiny PDFs)."""
import io
from types import SimpleNamespace

import pytest
from pypdf import PdfReader, PdfWriter

from intake.llm_extract import LlmUnavailable, SpendGate, build_user_prompt, extract_mentions
from intake.models import Extraction, Mention
from intake.readers import ReadError, read_pdf, read_text, read_upload

GOOD = Extraction(mentions=[Mention(phrase="Python", evidence_quote="Python", context="work", years_quote=None)])


class FakeClient:
    def __init__(self, stop_reason="end_turn", parsed=GOOD):
        self.calls = []
        self.messages = SimpleNamespace(parse=self._parse)
        self._stop, self._parsed = stop_reason, parsed

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(stop_reason=self._stop, parsed_output=self._parsed,
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=500))


def test_extract_returns_parsed_output_and_settles_real_cost():
    gate, client = SpendGate(1.0), FakeClient()
    assert extract_mentions("Python dev", client=client, gate=gate) == GOOD
    assert gate.spent == pytest.approx(1000 * 0.10 / 1e6 + 500 * 0.50 / 1e6)
    sent = client.calls[0]
    assert sent["output_format"] is Extraction and "tool_choice" not in sent


@pytest.mark.parametrize("stop, code", [("refusal", "REFUSAL"), ("max_tokens", "TRUNCATED")])
def test_unusable_answers_raise(stop, code):
    with pytest.raises(LlmUnavailable) as caught:
        extract_mentions("cv", client=FakeClient(stop_reason=stop), gate=SpendGate(1.0))
    assert caught.value.code == code


def test_missing_output_raises():
    with pytest.raises(LlmUnavailable, match="INVALID_OUTPUT"):
        extract_mentions("cv", client=FakeClient(parsed=None), gate=SpendGate(1.0))


def test_spend_limit_blocks_before_the_call():
    client = FakeClient()
    with pytest.raises(LlmUnavailable, match="SPEND_LIMIT"):
        extract_mentions("cv", client=client, gate=SpendGate(0.0))
    assert client.calls == []


def test_no_key_means_no_call(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LlmUnavailable, match="NO_KEY"):
        extract_mentions("cv", gate=SpendGate(1.0))


def test_retry_note_uses_fixed_text_only():
    prompt = build_user_prompt("CV text", ("QUOTE_NOT_FOUND", "attacker words"))
    assert "some quotes were not found" in prompt and "attacker words" not in prompt


# ---------------------------------------------------------------- readers


def make_pdf(pages):
    """A minimal valid PDF with one line of Helvetica text per page."""
    count = len(pages)
    font = 3 + 2 * count
    objects = {1: "<< /Type /Catalog /Pages 2 0 R >>",
               2: f"<< /Type /Pages /Kids [{' '.join(f'{3 + 2 * i} 0 R' for i in range(count))}] /Count {count} >>",
               font: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
    for i, text in enumerate(pages):
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        objects[3 + 2 * i] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
                              f"/Resources << /Font << /F1 {font} 0 R >> >> >>")
        objects[4 + 2 * i] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
    out, offsets = b"%PDF-1.4\n", {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n{objects[number]}\nendobj\n".encode()
    xref, size = len(out), max(objects) + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
    out += "".join(f"{offsets[n]:010d} 00000 n \n" for n in range(1, size)).encode()
    return out + f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def test_pdf_text_is_read_in_a_child_process():
    assert "Built APIs in Python" in read_pdf(make_pdf(["Built APIs in Python"]))


@pytest.mark.parametrize("data, code", [
    (b"hello", "NOT_PDF"),
    (b"%PDF-1.4 garbage", "UNREADABLE"),
    (make_pdf(["p"] * 5), "TOO_MANY_PAGES"),
    (make_pdf([" "]), "NO_TEXT"),
], ids=["not-pdf", "garbage", "five-pages", "no-text"])
def test_bad_pdfs_are_refused(data, code):
    with pytest.raises(ReadError) as caught:
        read_pdf(data)
    assert caught.value.code == code


def test_encrypted_pdf_is_refused():
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf(["secret"]))))
    writer.encrypt("pw")
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ReadError) as caught:
        read_pdf(buffer.getvalue())
    assert caught.value.code == "ENCRYPTED"


def test_text_readers():
    assert read_text("Python\n".encode("utf-8-sig")) == "Python\n"
    with pytest.raises(ReadError, match="NOT_UTF8"):
        read_text(b"\xff\xfe\xfa")
    with pytest.raises(ReadError, match="UNSUPPORTED"):
        read_upload("cv.xlsx", b"x")
