import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))  # noqa: E402

from info_tools import get_information


def test_kb_lookup(tmp_path, monkeypatch):
    kb_dir = tmp_path
    file = kb_dir / "apple.txt"
    file.write_text("Apples are nutritious.")
    monkeypatch.setattr("info_tools.DOCS_DIR", kb_dir)
    assert get_information("apple", "kb") == "Apples are nutritious."


def test_invalid_source():
    assert "Invalid source" in get_information("rice", "other")
