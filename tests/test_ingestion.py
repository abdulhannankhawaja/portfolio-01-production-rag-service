import re

from app.ingestion import extract_text, split_text


class WordTokenizer:
    def __call__(self, text, **kwargs):
        return {
            "offset_mapping": [
                (match.start(), match.end())
                for match in re.finditer(r"\S+", text)
            ]
        }


def test_tokenizer_aware_chunks_respect_size_and_overlap():
    chunks = split_text(
        [(1, "alpha beta gamma delta epsilon zeta")],
        chunk_size=3,
        overlap=1,
        tokenizer=WordTokenizer(),
    )

    assert len(chunks) > 1
    assert all(len(chunk["text"].split()) <= 3 for chunk in chunks)
    assert chunks[0]["text"].split()[-1] == chunks[1]["text"].split()[0]


def test_docx_extraction_does_not_invent_a_page_number():
    import io
    from docx import Document

    document = Document()
    document.add_heading("Risk Management", level=1)
    document.add_paragraph("This is actual DOCX test content.")
    content = io.BytesIO()
    document.save(content)

    extracted = extract_text(content.getvalue(), "guide.docx")

    assert extracted
    assert all(page is None for page, _, _ in extracted)
    assert extracted[-1][2] == "Risk Management"
