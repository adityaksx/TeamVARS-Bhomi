from difflib import SequenceMatcher
import re


def similarity(left: str, right: str) -> float:
    left_tokens = set(re.findall(r"[a-z0-9]+", left.casefold()))
    right_tokens = set(re.findall(r"[a-z0-9]+", right.casefold()))
    if not left_tokens or not right_tokens:
        return 0.0

    token_score = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    sequence_score = SequenceMatcher(
        None,
        " ".join(sorted(left_tokens)),
        " ".join(sorted(right_tokens)),
    ).ratio()
    return max(token_score, sequence_score)


def classify_name_match(left: str, right: str) -> str:
    score = similarity(left, right)
    if score >= 0.92:
        return "same"
    if score >= 0.78:
        return "ambiguous"
    return "different"
