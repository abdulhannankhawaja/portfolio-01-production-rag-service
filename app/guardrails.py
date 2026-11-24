import re


INJECTION_PATTERNS = (
    "ignore previous",
    "ignore all prior",
    "system prompt",
    "developer prompt",
    "reveal api key",
    "jailbreak",
    "bypass",
)


def validate_question(question: str, max_chars: int) -> str:
    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty")
    if len(question) > max_chars:
        raise ValueError("Question is too long")
    lowered = question.lower()
    if any(pattern in lowered for pattern in INJECTION_PATTERNS):
        raise ValueError("Request blocked by input guardrail")
    return question


def is_grounded(answer: str, chunks: list[dict]) -> bool:
    if not answer or not chunks:
        return False
    indices = {
        int(value)
        for value in re.findall(r"\[(\d+)\]", answer)
    }
    if not indices or any(index < 1 or index > len(chunks) for index in indices):
        return False
    answer_words = set(re.findall(r"[A-Za-z]{4,}", answer.casefold()))
    context_words = set()
    for index in indices:
        context_words.update(
            re.findall(r"[A-Za-z]{4,}", chunks[index - 1]["text"].casefold())
        )
    return bool(answer_words & context_words)
