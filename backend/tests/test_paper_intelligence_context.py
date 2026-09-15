"""Behaviour tests for the general Paper Intelligence Context contract."""

from types import SimpleNamespace

from services.ai.papers import build_paper_intelligence_context, build_question_inventory
from services.ai.response_normalization import normalize_study_response


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
    assert "Inventory 2: SECTION A • Question 1 • pages 2-2" in context.text
    assert "method=ocr; confidence=0.61" in context.text
    # The same context contains evidence for navigation, explanation, comparison,
    # revision, question collection and uncertainty about the failed page.
    assert "Question 1. Explain" in context.text
    assert "Question 2. Design" in context.text
    assert "failed_pages=[4]" in context.text


def test_question_inventory_is_ordered_complete_and_keeps_unnumbered_tasks():
    units = _units() + [
        SimpleNamespace(id=4, page_number=4, passage_index=3, section_title="SECTION C", question_number=None, extraction_method="ocr", extraction_confidence=0.74, text="Vocabulary matching task: match each term to its definition."),
        SimpleNamespace(id=5, page_number=4, passage_index=4, section_title="SECTION C", question_number=None, extraction_method="ocr", extraction_confidence=0.74, text="Write a short response using three of the terms."),
    ]
    inventory = build_question_inventory(units)
    assert [(item["section"], item["question_number"]) for item in inventory] == [
        ("Instructions", None), ("SECTION A", "1"), ("SECTION B", "2"), ("SECTION C", None),
    ]
    # Adjacent unnumbered source units remain one ordered assessment item and
    # are never fabricated into a question number.
    assert inventory[-1]["question_number"] is None
    assert len(inventory[-1]["text"]) == 2


def test_response_normalization_preserves_markdown_and_math_without_ui_noise():
    content, quality = normalize_study_response(
        "# Answer\n\nsvgCopy\n\n| A | B |\n| - | - |\n| 1 | 2 |\n\n\\(E = mc^2\\)\n\nSources\n\nSources\n"
    )
    assert "svgCopy" not in content
    assert "| A | B |" in content
    assert r"\(E = mc^2\)" in content
    assert content.count("Sources") == 1
    assert quality.removed_ui_artifacts == 1
    assert quality.duplicate_source_heading is True


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
