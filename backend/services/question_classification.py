from __future__ import annotations
import re
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from models.papers import PaperPassage, PaperQuestion, QuestionClassification, QuestionTopic, Papers

CLASSIFIER_VERSION = "heuristic-topic-classifier-v1"
TOPIC_RULES = {"Normalization": ("third normal form", "functional dependency", "candidate key", "normalization"), "SQL": ("select ", " join ", "sql", "query"), "Transactions": ("transaction", "acid", "isolation", "commit"), "Indexing": ("index", "b-tree", "hash index")}

def split_questions(text: str) -> list[tuple[str | None, str]]:
    matches = list(re.finditer(r"(?i)(?:\bquestion\s*|\bq\s*)?(\d{1,2})\s*[.)]", text))
    if len(matches) < 2: return [(None, text)] if len(text) >= 40 else []
    return [(match.group(1), text[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip()) for index, match in enumerate(matches) if len(text[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip()) >= 25]

class QuestionClassifier:
    def classify(self, text: str) -> tuple[list[tuple[str, str | None, int]], list[str], int, str, int]:
        lower = f" {text.lower()} "
        topics = [(topic, None, min(95, 55 + 12 * sum(term in lower for term in terms))) for topic, terms in TOPIC_RULES.items() if any(term in lower for term in terms)]
        types = []
        if re.search(r"\b(compare|difference|distinguish)\b", lower): types.append("Comparison")
        if re.search(r"\b(define|what is|state)\b", lower): types.append("Definition")
        if re.search(r"\b(calculate|compute|solve|derive)\b|[=∑√]", lower): types.append("Calculation")
        if re.search(r"\b(write a program|implement|code)\b", lower): types.append("Programming")
        if re.search(r"\b(explain|discuss|describe)\b", lower): types.append("Explanation")
        if re.search(r"\b(a\)|b\)|i\)|ii\))", lower): types.append("Short answer")
        steps = len(re.findall(r"\b(and|then|using|show|prove)\b", lower)) + len(re.findall(r"\([a-zivx]+\)", lower))
        difficulty = "Hard" if steps >= 4 or len(text) > 700 else "Medium" if steps >= 2 or len(text) > 250 else "Easy" if types else "Unknown"
        confidence = 75 if difficulty != "Unknown" else 35
        return topics, types, 80 if types else 35, difficulty, confidence

class QuestionIndexService:
    def __init__(self, db: AsyncSession): self.db = db; self.classifier = QuestionClassifier()
    async def index_paper(self, paper: Papers, passages: list[PaperPassage]) -> int:
        question_ids = select(PaperQuestion.id).where(PaperQuestion.paper_id == paper.id)
        await self.db.execute(delete(QuestionTopic).where(QuestionTopic.question_id.in_(question_ids)))
        await self.db.execute(delete(QuestionClassification).where(QuestionClassification.question_id.in_(question_ids)))
        await self.db.execute(delete(PaperQuestion).where(PaperQuestion.paper_id == paper.id))
        count = 0
        for passage in passages:
            for number, text in split_questions(passage.text):
                question = PaperQuestion(paper_id=paper.id, passage_id=passage.id, question_number=number, text=text, page_start=passage.page_number, page_end=passage.page_number, course_code=paper.course_code, academic_year=paper.year, classification_status="processing")
                self.db.add(question); await self.db.flush()
                topics, types, type_confidence, difficulty, difficulty_confidence = self.classifier.classify(text)
                for topic, subtopic, confidence in topics: self.db.add(QuestionTopic(question_id=question.id, topic=topic, subtopic=subtopic, confidence=confidence, source="rules", classifier_version=CLASSIFIER_VERSION))
                self.db.add(QuestionClassification(question_id=question.id, question_types=",".join(types) or None, type_confidence=type_confidence, difficulty=difficulty, difficulty_confidence=difficulty_confidence, difficulty_method="heuristic", classifier_version=CLASSIFIER_VERSION))
                question.classification_status = "completed" if topics or types else "partial"; count += 1
        await self.db.commit(); return count
