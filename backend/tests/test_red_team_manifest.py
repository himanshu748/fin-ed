from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "RED_TEAM.md"


def test_red_team_manifest_records_ten_completed_day_two_cases() -> None:
    source = MANIFEST.read_text(encoding="utf-8")
    case_headings = re.findall(r"^## RT-\d{2} — .+$", source, flags=re.MULTILINE)

    assert len(case_headings) == 10
    assert len(set(case_headings)) == 10
    assert source.count("**Prompt:**") == 10
    assert source.count("**Expected:**") == 10
    assert source.count("**Observed:**") == 10
    assert source.count("**Result:** Pass") == 10
    assert not re.search(r"\b(?:TBD|TODO|NOT RUN)\b", source, flags=re.IGNORECASE)


def test_red_team_manifest_covers_the_agent_specific_risks() -> None:
    source = MANIFEST.read_text(encoding="utf-8").casefold()

    for required in (
        "otp",
        "recommendation",
        "guaranteed",
        "f&o",
        "₹50",
        "₹20",
        "tax",
        "hidden instructions",
        "repeat",
        "code-mixed",
    ):
        assert required.casefold() in source
