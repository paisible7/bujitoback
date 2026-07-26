from __future__ import annotations


def strip_emojis(value: str | None) -> str:
    """
    Remove most emoji/pictograph characters from text while keeping accents and
    normal punctuation. This is used to enforce "text-only" notifications.
    """
    if not value:
        return ""

    out: list[str] = []
    for ch in value:
        cp = ord(ch)
        # Emoji glue / variation selectors.
        if cp in (0x200D, 0xFE0F, 0xFE0E):
            continue
        if _is_emoji_codepoint(cp):
            continue
        out.append(ch)

    # Normalize spacing after removals.
    return " ".join("".join(out).split())


def _is_emoji_codepoint(cp: int) -> bool:
    # Covers most emoji blocks, including 🚀 (U+1F680).
    if 0x1F600 <= cp <= 0x1F64F:
        return True  # Emoticons
    if 0x1F300 <= cp <= 0x1F5FF:
        return True  # Misc Symbols and Pictographs
    if 0x1F680 <= cp <= 0x1F6FF:
        return True  # Transport and Map Symbols
    if 0x1F700 <= cp <= 0x1F77F:
        return True
    if 0x1F780 <= cp <= 0x1F7FF:
        return True
    if 0x1F800 <= cp <= 0x1F8FF:
        return True
    if 0x1F900 <= cp <= 0x1F9FF:
        return True  # Supplemental Symbols and Pictographs
    if 0x1FA00 <= cp <= 0x1FA6F:
        return True
    if 0x1FA70 <= cp <= 0x1FAFF:
        return True
    if 0x1F1E6 <= cp <= 0x1F1FF:
        return True  # Flags
    if 0x2600 <= cp <= 0x26FF:
        return True  # Misc symbols
    if 0x2700 <= cp <= 0x27BF:
        return True  # Dingbats
    return False

