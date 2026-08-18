"""Lightweight question classification service shim.

The real implementation was removed or relocated; restore a minimal
compatibility shim so modules importing `services.question_classification`
do not fail at import time. The methods are intentionally no-ops — the
callers already treat classification as optional and ignore failures.
"""
from __future__ import annotations

from typing import Iterable


class QuestionIndexService:
    def __init__(self, db):
        self.db = db

    async def index_paper(self, paper, passages: Iterable[object]) -> None:
        """No-op indexing for legacy compatibility.

        Accepts the same arguments as the original service but performs no
        classification. Return value is intentionally None.
        """
        return None


__all__ = ["QuestionIndexService"]
