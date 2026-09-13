"""Behaviour tests for the general Paper Intelligence Context contract."""

from types import SimpleNamespace

from services.ai.papers import build_paper_intelligence_context


def _paper():
    return SimpleNamespace(
        id=42, title="Algorithms Final", course_code="CSC312", course_name="Algorithms",
        paper_type="Final examination", year=2026, extraction_status="partial",
        extraction_method="hybrid", extraction_quality=0.72, failed_pages="[4]",
    )


def _units():
    return [
        SimpleNamespace(id=1, page_number=1, passage_index=0, section_title="Instructions", question_number=None, extraction_method="native", extraction_confidence=0.99, text="Answer Section A and one question from Section B."),
        SimpleNamespace(id=2, page_number=2, passage_index=1, section_title="SECTION A", question_number="1", extraction_method="native", extraction_confidence=0.98, text="Question 1. Explain asymptotic complexity and compare O(n) with O(log n)."),
        SimpleNamespace(id=3, page_number=3, passage_index=2, section_title="SECTION B", question_number="2", extraction_method="ocr", extraction_confidence=0.61, text="Question 2. Design a dynamic-programming algorithm for knapsack."),
    ]


def test_complete_context_supports_many_natural_requests_without_intent_routing():
    context = build_paper_intelligence_context(paper=_paper(), passages=_units(), max_tokens=4000, query="teach me the complexity comparison")
    assert context.selection_mode == "complete"
    assert "NAVIGATION MANIFEST (complete, ordered)" in context.text
    assert "Question 1 → SECTION A (Page 2)" in context.text
    assert "method=ocr; confidence=0.61" in context.text
    # The same context contains evidence for navigation, explanation, comparison,
    # revision, question collection and uncertainty about the failed page.
    assert "Question 1. Explain" in context.text
    assert "Question 2. Design" in context.text
    assert "failed_pages=[4]" in context.text


def test_large_context_keeps_complete_map_and_ordered_grounded_selection():
    units = _units() + [
        SimpleNamespace(id=10 + i, page_number=5 + i, passage_index=3 + i, section_title="SECTION C", question_number=str(3 + i), extraction_method="native", extraction_confidence=0.9, text=("graph traversal shortest path evidence " * 80))
        for i in range(4)
    ]
    context = build_paper_intelligence_context(paper=_paper(), passages=units, max_tokens=800, query="shortest path")
    assert context.selection_mode == "structure_preserving_selection"
    assert "SECTION A" in context.text and "SECTION B" in context.text and "SECTION C" in context.text
    assert "Do not claim omitted text was inspected" in context.text
    assert context.source_ids
