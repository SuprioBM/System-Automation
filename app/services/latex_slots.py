"""Protected-region editing for the fixed résumé LaTeX template.

The agent may only ever change content between a slot's START/END markers
(`% DEVSYNC_<CATEGORY>_SLOT_<N>_START` / `..._END`). `assert_only_slots_changed`
is the actual enforcement: it strips every slot's inner content from both the
original and candidate document and requires the remainder to be byte-identical,
so any modification outside a designated slot -- document class, packages,
margins, headers, unrelated sections -- fails validation rather than being
trusted to have not happened.
"""
from __future__ import annotations

import re

from app.core.errors import ValidationFailure

_SLOT_RE = re.compile(r"(% DEVSYNC_(\w+)_SLOT_(\d+)_START\n)(.*?)(% DEVSYNC_\2_SLOT_\3_END\n)", re.DOTALL)
_ANY_SLOT_RE = re.compile(r"(% DEVSYNC_\w+_SLOT_\d+_START\n).*?(% DEVSYNC_\w+_SLOT_\d+_END\n)", re.DOTALL)

REQUIRED_SECTIONS = ["Education", "Experience", "Technical Skills"]


def _slot_pattern(category: str, index: int) -> re.Pattern:
    tag = f"DEVSYNC_{category.upper()}_SLOT_{index}"
    return re.compile(rf"(% {tag}_START\n)(.*?)(% {tag}_END\n)", re.DOTALL)


def list_slots(tex: str) -> list[tuple[str, int]]:
    return [(m.group(2).lower(), int(m.group(3))) for m in _SLOT_RE.finditer(tex)]


def get_slot(tex: str, category: str, index: int) -> str:
    m = _slot_pattern(category, index).search(tex)
    if not m:
        raise ValidationFailure(f"slot {category}_{index} not found in template -- refusing silent no-op")
    return m.group(2)


def set_slot(tex: str, category: str, index: int, content: str) -> str:
    pattern = _slot_pattern(category, index)
    if not pattern.search(tex):
        raise ValidationFailure(f"slot {category}_{index} not found in template -- refusing silent no-op")
    replacement = content.rstrip("\n") + "\n"
    return pattern.sub(lambda m: m.group(1) + replacement + m.group(3), tex, count=1)


def strip_all_slots(tex: str) -> str:
    return _ANY_SLOT_RE.sub(lambda m: m.group(1) + m.group(2), tex)


def assert_only_slots_changed(original_tex: str, candidate_tex: str) -> None:
    if strip_all_slots(original_tex) != strip_all_slots(candidate_tex):
        raise ValidationFailure(
            "resume modification changed protected LaTeX outside designated "
            "DEVSYNC slot regions -- rejected before compilation"
        )


def required_sections_present(tex: str) -> bool:
    return all(f"section{{{s}}}" in tex or f"section {{{s}}}" in tex for s in REQUIRED_SECTIONS)
