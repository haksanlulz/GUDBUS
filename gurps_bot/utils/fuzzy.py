from __future__ import annotations

from rapidfuzz import fuzz, process, utils


def fuzzy_match(
    query: str,
    candidates: list[str],
    limit: int = 5,
    score_cutoff: int = 60,
    *,
    prefix_optimized: bool = False,
) -> list[tuple[str, float]]:
    """(match, score) best-first; prefix_optimized uses partial_ratio, which needs default_process to case-fold"""
    if not query or not candidates:
        return []

    if prefix_optimized:
        scorer = fuzz.partial_ratio
        processor = utils.default_process
    else:
        scorer = fuzz.WRatio
        processor = None

    results = process.extract(
        query,
        candidates,
        scorer=scorer,
        processor=processor,
        limit=limit,
        score_cutoff=score_cutoff,
    )
    return [(match, score) for match, score, _ in results]


def best_match(query: str, candidates: list[str], score_cutoff: int = 60) -> str | None:
    matches = fuzzy_match(query, candidates, limit=1, score_cutoff=score_cutoff)
    return matches[0][0] if matches else None
