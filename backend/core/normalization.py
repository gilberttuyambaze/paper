import re
from typing import List


DEGREE_PREFIXES = [
    r"b\s*\.?\s*sc\s*\.?",
    r"bsc",
    r"bachelor of science",
    r"bachelor\'s of science",
    r"bachelor",
    r"msc",
    r"m\s*\.?\s*sc\s*\.?",
    r"master of science",
    r"phd",
]


def normalize_programme_text(text: str) -> str:
    """Deterministic normalization for programme text.

    Preserves original for audit elsewhere. This function lowers case,
    strips punctuation, normalizes common degree prefixes and ampersands,
    collapses whitespace, and removes harmless degree noise like BSc/B.Sc.
    It does not attempt aggressive semantic shortening.
    """
    if text is None:
        return ""

    s = text.strip()
    # normalize unicode spaces
    s = re.sub(r"\s+", " ", s)
    # lower
    s = s.lower()
    # replace ampersand with 'and'
    s = s.replace("&", " and ")
    # remove punctuation except keep + and - inside tokens? remove all punctuation
    s = re.sub(r"[\"'`.,:;()\[\]{}<>?/\\@#%^*~|]", " ", s)
    # normalize degree prefixes
    for pat in DEGREE_PREFIXES:
        s = re.sub(r"\b" + pat + r"\b", "", s)
    # remove leading filler words left after stripping degree prefixes
        # collapse multiple spaces
        s = re.sub(r"\s+", " ", s)
        # remove leading filler words left after stripping degree prefixes (allow leading spaces)
        s = re.sub(r"^\s*(in|of|the)\s+", "", s)
    s = s.strip()

    return s


def tokenize_normalized(text: str) -> List[str]:
    n = normalize_programme_text(text)
    if not n:
        return []
    return n.split(" ")
