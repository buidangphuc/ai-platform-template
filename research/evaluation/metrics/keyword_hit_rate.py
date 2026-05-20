def keyword_hit_rate(*, source_text: str, expected_keywords: list[str]) -> float:
    if not expected_keywords:
        return 0.0
    normalized_source = source_text.lower()
    hits = sum(
        1 for keyword in expected_keywords if keyword.lower() in normalized_source
    )
    return hits / len(expected_keywords)
