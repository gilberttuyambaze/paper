import asyncio
from types import SimpleNamespace

from services.contribution_communications import THEMES, compose_contribution_message
from services.paper_processing import PaperProcessingService


class _DB:
    def __init__(self):
        self.added = []
    def add(self, value):
        self.added.append(value)
    async def execute(self, *_args, **_kwargs):
        class _Result:
            def scalar_one_or_none(self): return None
        return _Result()


def test_receipt_enqueues_a_durable_job_without_running_ingestion():
    db = _DB()
    paper = SimpleNamespace(id=7, extraction_status=None, extraction_version=None)
    job = asyncio.run(PaperProcessingService(db).enqueue(paper))
    assert job.paper_id == 7
    assert job.status == "QUEUED"
    assert paper.extraction_status == "QUEUED"
    assert db.added == [job]


def test_contributor_messages_are_grounded_and_support_meaningful_themes():
    paper = SimpleNamespace(id=7, title="Algorithms Final", course_code="CSC312", course_name="Algorithms", department="Computer Science", paper_type="Exam", year=2024)
    user = SimpleNamespace(id="u1", name="Aline", email="aline@example.test")
    receipt = compose_contribution_message("PAPER_RECEIVED", paper, user, 1)
    complete = compose_contribution_message("PAPER_PROCESSING_COMPLETED", paper, user, 2)
    assert "Algorithms Final" in receipt["text"]
    assert "Aline" in receipt["text"]
    assert "safely received" in receipt["text"]
    assert "ready for Study AI" in complete["text"]
    assert receipt["subject"] != complete["subject"]
    assert receipt["text"] != complete["text"]
    assert len(THEMES) >= 4

    # HTML Brand design assertions
    assert "UR Academic Resource Hub" in receipt["html"]
    assert "Academic Platform" in receipt["html"]
    assert "Contribution Received" in receipt["html"]
    assert "View Your Paper" in receipt["html"]
    assert "https://paperhubur.vercel.app/paper/7" in receipt["html"]
    assert "Computer Science" in receipt["html"]
    assert "CSC312 — Algorithms" in receipt["html"]
    assert "Terms of Service" in receipt["html"]
    assert "Privacy Policy" in receipt["html"]
    assert "paperhubur@gmail.com" in receipt["html"]

    assert "Study AI Ready" in complete["html"]
    assert "Explore with Study AI" in complete["html"]
    assert "https://paperhubur.vercel.app/paper/7" in complete["html"]



def test_missing_optional_metadata_is_not_fabricated_into_communication():
    paper = SimpleNamespace(id=9, title="A submitted paper", course_code=None, course_name=None)
    user = SimpleNamespace(id="u2", name=None, email="u2@example.test")
    message = compose_contribution_message("PAPER_RECEIVED", paper, user, 1)
    assert "Hello there" in message["text"]
    assert "None" not in message["text"]


def test_community_upload_route_uses_the_durable_receipt_path():
    from pathlib import Path
    route_path = Path(__file__).resolve().parent.parent / "routers" / "community.py"
    route = route_path.read_text(encoding="utf-8")
    create_start = route.index("async def create_paper(")
    create_end = route.index("\n\n@router.post(\"/papers/{paper_id}/comments\")", create_start)
    body = route[create_start:create_end]
    assert "PaperProcessingService(db).enqueue(paper)" in body
    assert 'event_type="PAPER_RECEIVED"' in body
    assert "await db.flush()" in body
