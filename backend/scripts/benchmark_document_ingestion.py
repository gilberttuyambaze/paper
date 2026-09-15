"""Measure Paper Intelligence extraction for a local PDF fixture.

This deliberately exercises the same classifier, renderer, OCR provider and
structure parser as the paper worker, without changing a database row. Use it
before and after a deployment/configuration change; it emits JSON suitable for
attaching to an incident or comparing in CI.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from services.document_ingestion import DocumentIngestionService


async def main(path: Path, max_pages: int) -> None:
    pdf_bytes = path.read_bytes()
    result = await DocumentIngestionService.process_pdf(pdf_bytes, max_pages=max_pages)
    print(json.dumps({
        "fixture": path.name,
        "pages": result.page_count,
        "status": result.extraction_status,
        "method": result.extraction_method,
        "quality": result.extraction_quality,
        "failed_pages": result.failed_pages,
        "sections": len(result.structure.sections),
        "questions": len(result.structure.detected_questions),
        "metrics": result.metrics,
    }, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Profile Paper Intelligence ingestion for a PDF fixture")
    parser.add_argument("pdf", type=Path, help="Local text, scanned, or mixed PDF fixture")
    parser.add_argument("--max-pages", type=int, default=150)
    args = parser.parse_args()
    if not args.pdf.is_file():
        parser.error(f"PDF fixture not found: {args.pdf}")
    asyncio.run(main(args.pdf, max(1, args.max_pages)))
