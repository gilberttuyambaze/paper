"""Field-aware normalization for user supplied metadata and storage names."""

import re
import unicodedata
from collections.abc import Iterable
from pathlib import PurePosixPath


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = unicodedata.normalize("NFKC", str(value)).replace("\u00a0", " ")
    value = re.sub(r"[\r\n\t]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_identifier(value: str | None) -> str | None:
    value = normalize_text(value)
    return value.lower() if value else value


def normalize_slug(value: str | None) -> str | None:
    value = normalize_text(value)
    if not value:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return slug.strip("-") or None


def normalize_email(value: str) -> str:
    return normalize_text(value).lower()  # type: ignore[union-attr]


def normalize_phone(value: str | None) -> str | None:
    value = normalize_text(value)
    if not value:
        return None
    digits = re.sub(r"\D+", "", value)
    if len(digits) >= 10:
        return digits[-10:]
    return digits or None


def _isbn10_valid(value: str) -> bool:
    if len(value) != 10 or not re.fullmatch(r"\d{9}[\dXx]", value):
        return False
    return sum((10 - index) * (10 if char.upper() == "X" else int(char)) for index, char in enumerate(value)) % 11 == 0


def _isbn13_valid(value: str) -> bool:
    if len(value) != 13 or not value.isdigit():
        return False
    checksum = sum((1 if index % 2 == 0 else 3) * int(char) for index, char in enumerate(value[:12]))
    return (10 - checksum % 10) % 10 == int(value[-1])


def normalize_isbn(value: str | None) -> str | None:
    """Extract the first valid ISBN in deterministic left-to-right order."""
    value = normalize_text(value)
    if not value:
        return None
    candidates = re.findall(r"(?<!\d)(?:97[89][\d\s-]{9,16}|[\d][\d\s-]{8,14}[\dXx])(?!\d)", value)
    for candidate in candidates:
        compact = re.sub(r"[\s-]", "", candidate)
        if _isbn13_valid(compact) or _isbn10_valid(compact):
            return compact.upper()
    compact = re.sub(r"[^0-9Xx]", "", value)
    if _isbn13_valid(compact) or _isbn10_valid(compact):
        return compact.upper()
    raise ValueError("ISBN could not be recognized. Enter a valid ISBN-10 or ISBN-13.")


def normalize_filename(filename: str | None, fallback: str = "document") -> str:
    value = unicodedata.normalize("NFKD", filename or "").encode("ascii", "ignore").decode("ascii")
    value = value.replace("\\", "/").split("/")[-1]
    value = re.sub(r"[\x00-\x1f\x7f]", "", value).strip().strip(".")
    suffix = PurePosixPath(value).suffix.lower()
    basename = value[: -len(suffix)] if suffix else value
    basename = re.sub(r"[^A-Za-z0-9]+", "-", basename).strip("-").lower() or fallback
    return f"{basename[:96]}{suffix[:12]}"


def build_storage_key(bucket: str, namespace: str, filename: str | None, identity: str | int | None = None) -> str:
    safe_name = normalize_filename(filename, fallback="document")
    identity_part = re.sub(r"[^A-Za-z0-9_-]+", "-", str(identity or "upload"))[:32]
    key = f"{bucket.strip().lower()}/{namespace.strip().lower()}/{identity_part}-{safe_name}"
    return key[:255] if len(key) <= 255 else f"{key[:255 - len(PurePosixPath(safe_name).suffix)]}{PurePosixPath(safe_name).suffix}"


def normalize_storage_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("\\", "/").strip("/")
    parts = [part for part in value.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("Storage path contains an invalid segment")
    safe_parts = [re.sub(r"[^A-Za-z0-9._-]+", "-", part).strip("-") for part in parts]
    if not all(safe_parts):
        raise ValueError("Storage path contains an invalid segment")
    safe_parts[-1] = normalize_filename(safe_parts[-1])
    key = "/".join(safe_parts)
    if len(key) <= 255:
        return key
    suffix = PurePosixPath(key).suffix
    return f"{key[:255 - len(suffix)]}{suffix}"


def normalize_unique(values: Iterable[object | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_text(str(value)) if value is not None else None
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def normalize_array_ids(values: Iterable[object | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = normalize_text(str(value))
        if not text:
            continue
        normalized = re.sub(r"[^A-Za-z0-9_-]+", "", text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
