import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.document_classifier import (
    DocumentClassifier,
    PageType,
    DocumentType,
    PageClassification,
)
from services.document_structure import DocumentStructureParser, StructuredUnit
from services.ocr.base import OCRPageResult, OCRBlock
from services.ocr.local_provider import LocalOCRProvider
from services.ocr.image_preprocessor import (
    PdfPageRenderer,
    extract_page_image_bytes,
    detect_image_mime_type,
    to_data_uri,
)
from services.ocr.factory import get_ocr_provider
from services.document_ingestion import DocumentIngestionService
from services.retrieval import HybridRetrievalService, _extract_target_question_id
from routers.study_ai import STUDY_AI_SYSTEM_PROMPT


class DocumentIntelligenceUnitTests(unittest.TestCase):
    # ==============================================================================
    # 1. Document Classifier Tests
    # ==============================================================================

    def test_classifier_identifies_digital_text_page(self):
        mock_page = MagicMock()
        text = (
            "UNIVERSITY OF RWANDA\n"
            "COLLEGE OF SCIENCE AND TECHNOLOGY\n"
            "FINAL EXAMINATION 2023/2024\n"
            "COURSE: CSC 312 - ALGORITHMS AND COMPLEXITY\n"
            "TIME ALLOWED: 3 HOURS\n\n"
            "Instructions: Answer all questions in Section A and any two in Section B.\n"
            "Section A contains 5 questions carrying 10 marks each.\n"
        ) * 4
        mock_page.extract_text.return_value = text
        mock_page.images = []

        page_info = DocumentClassifier.classify_page(mock_page, page_number=1, raw_text=text)
        self.assertEqual(page_info.page_type, PageType.TEXT)
        self.assertGreater(page_info.quality_score, 0.8)
        self.assertGreater(page_info.char_count, 100)
        self.assertEqual(page_info.suspicious_char_ratio, 0.0)

    def test_classifier_identifies_scanned_image_page(self):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_page.images = ["dummy_image_1"]

        page_info = DocumentClassifier.classify_page(mock_page, page_number=1, raw_text="")
        self.assertEqual(page_info.page_type, PageType.SCANNED)
        self.assertLess(page_info.quality_score, 0.2)
        self.assertEqual(page_info.image_count, 1)

    def test_classifier_identifies_mixed_page(self):
        mock_page = MagicMock()
        mixed_text = (
            "Figure 1: State transition diagram for 3-bit ripple counter. "
            "The circuit consists of 3 JK flip flops connected in series. "
            "Analyze the state propagation delay under a 50MHz clock."
        )
        mock_page.extract_text.return_value = mixed_text
        mock_page.images = ["circuit_diagram"]

        page_info = DocumentClassifier.classify_page(mock_page, page_number=1, raw_text=mixed_text)
        self.assertEqual(page_info.page_type, PageType.MIXED)
        self.assertLessEqual(page_info.quality_score, 0.70)

    # ==============================================================================
    # 2. Layout Structure & Academic Exam Parser Tests
    # ==============================================================================

    def test_layout_parser_extracts_sections_and_questions(self):
        sample_exam = (
            "UNIVERSITY OF RWANDA\n"
            "COLLEGE OF SCIENCE AND TECHNOLOGY\n"
            "END OF SEMESTER EXAMINATIONS\n\n"
            "SECTION A: COMPULSORY QUESTIONS\n\n"
            "Question 1. (20 Marks)\n"
            "Define what is meant by asymptotic time complexity. Give examples of O(n) and O(log n).\n\n"
            "Question 2. (15 Marks)\n"
            "(a) Explain the Master Theorem for divide and conquer recurrences.\n"
            "(b) Solve T(n) = 2T(n/2) + n.\n\n"
            "SECTION B: ATTEMPT ANY TWO QUESTIONS\n\n"
            "Question 3. (25 Marks)\n"
            "Design a Dynamic Programming algorithm for the 0/1 Knapsack problem with complexity O(nW).\n"
        )

        units, current_section = DocumentStructureParser.parse_page_text(sample_exam, page_number=1)

        self.assertGreaterEqual(len(units), 3)
        q_nums = [u.question_number for u in units if u.question_number]
        self.assertTrue("1" in q_nums or any("1" in q for q in q_nums))
        self.assertTrue(any("2" in q for q in q_nums))
        self.assertTrue(any("3" in q for q in q_nums))

        sections = [u.section_title for u in units if u.section_title]
        self.assertTrue(any("SECTION A" in s for s in sections))

    def test_layout_parser_preserves_mathematical_formulas(self):
        math_exam = (
            "Question 4.\n"
            "Let f(x) = \\int_{0}^{\\infty} e^{-x^2} dx.\n"
            "Prove that f(x) = \\frac{\\sqrt{\\pi}}{2}.\n"
            "Calculate the derivative \\frac{df}{dx}."
        )

        units, current_section = DocumentStructureParser.parse_page_text(math_exam, page_number=2)

        self.assertGreater(len(units), 0)
        full_content = " ".join(u.text for u in units)
        self.assertIn("\\int_{0}^{\\infty}", full_content)
        self.assertIn("\\frac{\\sqrt{\\pi}}{2}", full_content)

    # ==============================================================================
    # 3. Image Preprocessing & Retrieval Tests
    # ==============================================================================

    def test_image_preprocessor_utilities(self):
        dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        self.assertEqual(detect_image_mime_type(dummy_png), "image/png")

        dummy_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        self.assertEqual(detect_image_mime_type(dummy_jpg), "image/jpeg")

        uri = to_data_uri(dummy_png)
        self.assertTrue(uri.startswith("data:image/png;base64,"))

        mock_img = MagicMock()
        mock_img.data = b"0" * 4096
        mock_page = MagicMock()
        mock_page.images = [mock_img]

        extracted = extract_page_image_bytes(mock_page)
        self.assertEqual(extracted, b"0" * 4096)

    def test_renderer_page_count_failure_does_not_abort_ingestion(self):
        class BrokenPdfiumDocument:
            def __len__(self):
                return None

        renderer = PdfPageRenderer(b"not used")
        renderer._doc = BrokenPdfiumDocument()
        self.assertIsNone(renderer.render(1))

    def test_embedded_image_without_data_is_ignored(self):
        missing_data_image = MagicMock()
        missing_data_image.data = None
        valid_image = MagicMock()
        valid_image.data = b"x" * 4096
        page = MagicMock()
        page.images = [missing_data_image, valid_image]
        self.assertEqual(extract_page_image_bytes(page), b"x" * 4096)

    def test_question_identifier_detection(self):
        self.assertEqual(_extract_target_question_id("Solve question 4(b) step by step"), "4(b)")
        self.assertEqual(_extract_target_question_id("How do I answer Question 2?"), "2")
        self.assertEqual(_extract_target_question_id("What is the formula in Q3?"), "3")
        self.assertIsNone(_extract_target_question_id("Give me a study guide for this exam"))

    def test_study_ai_prompt_contains_strict_anti_hallucination_rules(self):
        self.assertIn("DOCUMENT-GROUNDED ACADEMIC ASSISTANT MODE", STUDY_AI_SYSTEM_PROMPT)
        self.assertIn("Strict Grounding Rules", STUDY_AI_SYSTEM_PROMPT)
        self.assertIn("NEVER invent, hallucinate, or fabricate exam questions", STUDY_AI_SYSTEM_PROMPT)
        self.assertIn("NEVER assume the paper follows a 'typical' or 'usual' format", STUDY_AI_SYSTEM_PROMPT)
        self.assertIn("I could not find Question X in this examination paper", STUDY_AI_SYSTEM_PROMPT)
        self.assertIn("could not be reliably extracted from this document", STUDY_AI_SYSTEM_PROMPT)


class DocumentIntelligenceAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_ocr_provider_mocked(self):
        provider = LocalOCRProvider(tesseract_cmd="/usr/bin/tesseract")
        with patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.stdout = b"Question 1: Explain ACID database properties in detail."
            mock_run.return_value = mock_proc

            res = await provider.extract_page(b"dummy image bytes", page_number=1)
            self.assertIn("ACID", res.text)
            self.assertGreater(res.confidence, 0.8)
            self.assertEqual(res.provider, "local_ocr")

    async def test_ingestion_pipeline_routes_native_text_correctly(self):
        digital_pdf_text = "SECTION 1\nQuestion 1: Explain Big-O notation.\nQuestion 2: Explain NP-Completeness."

        mock_page = MagicMock()
        mock_page.extract_text.return_value = digital_pdf_text
        mock_page.images = []

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("pypdf.PdfReader", return_value=mock_reader):
            res = await DocumentIngestionService.process_pdf(b"%PDF-1.4 dummy")

            self.assertEqual(res.extraction_status, "completed")
            self.assertFalse(res.ocr_used)
            self.assertEqual(res.extraction_method, "native")
            self.assertGreaterEqual(res.extraction_quality, 0.8)
            self.assertEqual(len(res.pages), 1)
            self.assertIn("Big-O", res.combined_text)

    async def test_ingestion_pipeline_activates_ocr_for_scanned_pdf(self):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_page.images = ["dummy_image_1"]

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        mock_ocr = AsyncMock()
        mock_ocr.extract_page.return_value = OCRPageResult(
            page_number=1,
            text="Question 1 (Scanned): Describe Ohm's Law and calculate resistance.",
            confidence=0.88,
            provider="tesseract",
        )

        with patch("pypdf.PdfReader", return_value=mock_reader):
            with patch("services.document_ingestion.extract_page_image_bytes", return_value=b"fake image bytes"):
                with patch("services.document_ingestion.get_ocr_provider", return_value=mock_ocr):
                    res = await DocumentIngestionService.process_pdf(b"%PDF-1.4 dummy scanned")

                    self.assertEqual(res.extraction_status, "completed")
                    self.assertTrue(res.ocr_used)
                    self.assertIn("Ohm's Law", res.combined_text)
                    self.assertGreater(res.extraction_quality, 0.8)

    async def test_ingestion_reuses_one_renderer_and_reports_page_progress(self):
        pages = []
        for _ in range(2):
            page = MagicMock()
            page.extract_text.return_value = ""
            page.images = ["scan"]
            pages.append(page)
        mock_reader = MagicMock()
        mock_reader.pages = pages

        mock_ocr = AsyncMock()
        mock_ocr.extract_page.side_effect = [
            OCRPageResult(page_number=1, text="Question 1: Explain a concept.", confidence=0.9, provider="rapidocr"),
            OCRPageResult(page_number=2, text="Question 2: Apply the concept.", confidence=0.9, provider="rapidocr"),
        ]
        renderer = MagicMock()
        renderer.render.return_value = b"rendered page"
        events = []

        async def progress(event):
            events.append(event)

        with patch("pypdf.PdfReader", return_value=mock_reader):
            with patch("services.document_ingestion.PdfPageRenderer", return_value=renderer) as make_renderer:
                with patch("services.document_ingestion.get_ocr_provider", return_value=mock_ocr):
                    result = await DocumentIngestionService.process_pdf(
                        b"%PDF-1.4 scanned", progress_callback=progress
                    )

        make_renderer.assert_called_once_with(b"%PDF-1.4 scanned")
        self.assertEqual(renderer.render.call_count, 2)
        renderer.close.assert_called_once()
        self.assertEqual(result.metrics["ocr_calls"], 2)
        self.assertEqual(len(result.metrics["page_metrics"]), 2)
        self.assertTrue(any(event.get("pages_completed") == 2 for event in events))

    async def test_hybrid_retrieval_prioritizes_exact_question_match(self):
        p1 = MagicMock()
        p1.id = 101
        p1.page_number = 1
        p1.question_number = "1"
        p1.section_title = "SECTION A"
        p1.text = "Question 1: Define relational database constraints and primary keys."
        p1.embedding_json = None
        p1.course_code = None
        p1.extraction_confidence = 1.0

        p2 = MagicMock()
        p2.id = 102
        p2.page_number = 2
        p2.question_number = "4(b)"
        p2.section_title = "SECTION B"
        p2.text = "Question 4(b): Calculate the normalized form for R(A, B, C, D) given FD set."
        p2.embedding_json = None
        p2.course_code = None
        p2.extraction_confidence = 1.0

        p3 = MagicMock()
        p3.id = 103
        p3.page_number = 3
        p3.question_number = "5"
        p3.section_title = "SECTION B"
        p3.text = "Question 5: Discuss transaction serializability and 2PL locking protocol."
        p3.embedding_json = None
        p3.course_code = None
        p3.extraction_confidence = 1.0

        all_passages = [p1, p2, p3]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = all_passages
        mock_db.execute.return_value = mock_result
        mock_db.bind = None

        retriever = HybridRetrievalService(mock_db)
        results = await retriever.retrieve(
            query="Solve question 4(b) please",
            paper_id=1,
            limit=2,
        )

        self.assertGreater(len(results), 0)
        top_item = results[0]
        self.assertEqual(top_item.passage.question_number, "4(b)")
        self.assertEqual(top_item.passage.id, 102)
        self.assertTrue(top_item.is_exact_question_match)
        self.assertGreater(top_item.score, 0.6)
