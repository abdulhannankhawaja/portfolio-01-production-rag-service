import re


INJECTION_PATTERNS = (
    re.compile(r"\bignore\b.{0,40}\b(previous|prior|above|all)\b.{0,30}\b(instruction|prompt)s?\b"),
    re.compile(r"\b(disregard|override|forget)\b.{0,40}\b(system|developer|previous|prior)\b"),
    re.compile(r"\b(reveal|print|show|repeat|leak)\b.{0,30}\b(api key|secret|credential|system prompt|developer prompt)s?\b"),
    re.compile(r"\b(jailbreak|prompt injection)\b"),
    re.compile(r"\b(bypass|disable|ignore)\b.{0,30}\b(safety|guardrail|restriction)s?\b"),
)


def text_terms(text: str) -> set[str]:
    words = re.findall(r"[^\W\d_]+", text.casefold(), flags=re.UNICODE)
    terms = {word for word in words if len(word) >= 4}
    for word in words:
        if any(ord(character) > 127 for character in word):
            terms.update(word[index:index + 2] for index in range(len(word) - 1))
    return terms


def validate_question(question: str, max_chars: int) -> str:
    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty")
    if len(question) > max_chars:
        raise ValueError("Question is too long")
    normalized = re.sub(r"\s+", " ", question.casefold())
    if any(pattern.search(normalized) for pattern in INJECTION_PATTERNS):
        raise ValueError("Request blocked by input guardrail")
    return question


def is_grounded(answer: str, chunks: list[dict]) -> bool:
    if not answer or not chunks:
        return False
    indices = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    if not indices or any(index < 1 or index > len(chunks) for index in indices):
        return False
    answer_words = text_terms(answer)
    context_words = set()
    for index in indices:
        context_words.update(text_terms(chunks[index - 1]["text"]))
    return bool(answer_words & context_words)


def contains_sensitive_output(answer: str, secrets: tuple[str | None, ...]) -> bool:
    lowered = answer.casefold()
    return any(secret and len(secret) >= 8 and secret.casefold() in lowered for secret in secrets)
