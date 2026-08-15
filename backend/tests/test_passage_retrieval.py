from services.pdf_text import chunk_page_text, extract_pdf_pages
from services.retrieval import _cosine, _terms


def test_chunking_preserves_large_text_with_overlap():
    text = "Database normalization reduces redundancy. " * 80
    chunks = chunk_page_text(text, chunk_size=240, overlap=60)
    assert len(chunks) > 2
    assert all(len(chunk) >= 40 for chunk in chunks)
    assert "normalization" in chunks[0].lower()


def test_malformed_or_image_bytes_do_not_create_passages():
    assert extract_pdf_pages(b"not a PDF") == []
    assert extract_pdf_pages(b"\x89PNG\r\n\x1a\n" + b"0" * 100) == []


def test_semantic_cosine_and_exact_terms_support_hybrid_ranking():
    assert _terms("CSC 310 database normalization") >= {"csc", "310", "database", "normalization"}
    assert _cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
