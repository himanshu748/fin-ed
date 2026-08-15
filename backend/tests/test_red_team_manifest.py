from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "RED_TEAM.md"


def test_red_team_manifest_records_fifteen_completed_current_cases() -> None:
    source = MANIFEST.read_text(encoding="utf-8")
    case_headings = re.findall(r"^## (RT-\d{2}) - .+$", source, flags=re.MULTILINE)

    assert case_headings == [f"RT-{case:02d}" for case in range(1, 16)]
    assert source.count("**Prompt:**") == 15
    assert source.count("**Expected:**") == 15
    assert source.count("**Evidence:**") == 15
    assert source.count("**Result:** Pass") == 15
    assert not re.search(r"[\u2013\u2014]", source)
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
