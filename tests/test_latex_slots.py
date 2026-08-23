import pytest

from app.core.errors import ValidationFailure
from app.services import latex_slots

TEMPLATE = """\\documentclass{article}
\\begin{document}
\\section{Projects}
% DEVSYNC_FEATURED_SLOT_1_START
% DEVSYNC_FEATURED_SLOT_1_END
% DEVSYNC_FEATURED_SLOT_2_START
% DEVSYNC_FEATURED_SLOT_2_END
\\section{Education}
\\section{Experience}
\\section{Technical Skills}
\\end{document}
"""


def test_set_slot_only_changes_designated_region():
    modified = latex_slots.set_slot(TEMPLATE, "featured", 1, "\\resumeItem{Built X}")
    latex_slots.assert_only_slots_changed(TEMPLATE, modified)  # must not raise
    assert "Built X" in modified
    assert "% DEVSYNC_FEATURED_SLOT_2_START" in modified


def test_set_slot_unknown_slot_raises():
    with pytest.raises(ValidationFailure):
        latex_slots.set_slot(TEMPLATE, "featured", 99, "content")


def test_assert_only_slots_changed_detects_protected_region_edit():
    tampered = TEMPLATE.replace("\\documentclass{article}", "\\documentclass{report}")
    with pytest.raises(ValidationFailure):
        latex_slots.assert_only_slots_changed(TEMPLATE, tampered)


def test_assert_only_slots_changed_allows_multiple_slot_edits():
    modified = latex_slots.set_slot(TEMPLATE, "featured", 1, "A")
    modified = latex_slots.set_slot(modified, "featured", 2, "B")
    latex_slots.assert_only_slots_changed(TEMPLATE, modified)  # must not raise


def test_required_sections_present():
    assert latex_slots.required_sections_present(TEMPLATE) is True
    stripped = TEMPLATE.replace("\\section{Education}", "")
    assert latex_slots.required_sections_present(stripped) is False
