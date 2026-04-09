"""Tests for archive rotation."""
from datetime import date, timedelta
from pathlib import Path
from chronicles.archiver import rotate_records

def _write_record(chronicles_dir: Path, name: str, days_ago: int) -> Path:
    path = chronicles_dir / "records" / f"{name}.md"
    d = date.today() - timedelta(days=days_ago)
    path.write_text(
        f"---\ndate: {d.isoformat()}\nbranch: test\nstatus: complete\n"
        f"tags: [test]\nagent: claude-code\nduration: 5min\n"
        f"files_changed:\n  - src/a.py\n---\n\n# test\n"
    )
    return path

def test_rotates_old_records(chronicles_dir):
    _write_record(chronicles_dir, "2026-01-01_old-record", days_ago=100)
    _write_record(chronicles_dir, "2026-04-01_new-record", days_ago=5)
    rotate_records(chronicles_dir, after_days=90)
    assert not (chronicles_dir / "records" / "2026-01-01_old-record.md").exists()
    archives = list((chronicles_dir / "archives").rglob("*.md"))
    assert len(archives) == 1
    assert "old-record" in archives[0].name
    assert (chronicles_dir / "records" / "2026-04-01_new-record.md").exists()

def test_archive_uses_quarter_dirs(chronicles_dir):
    _write_record(chronicles_dir, "2026-01-15_q1-record", days_ago=100)
    rotate_records(chronicles_dir, after_days=90)
    archives = list((chronicles_dir / "archives").rglob("*.md"))
    assert len(archives) == 1
    parent = archives[0].parent.name
    assert parent.startswith("2026-") or parent.startswith("2025-")
    assert "Q" in parent

def test_chronicles_md_gets_archived_suffix(chronicles_dir):
    _write_record(chronicles_dir, "2026-01-01_old-record", days_ago=100)
    chron = chronicles_dir / "CHRONICLES.md"
    content = chron.read_text()
    content += "\n## [[2026-01-01_old-record|test]] | ✅ Complete\n> **Objective**: Test\n"
    chron.write_text(content)
    rotate_records(chronicles_dir, after_days=90)
    updated = chron.read_text()
    assert "(archived)" in updated

def test_no_rotation_when_all_fresh(chronicles_dir):
    _write_record(chronicles_dir, "2026-04-01_fresh", days_ago=5)
    rotate_records(chronicles_dir, after_days=90)
    assert (chronicles_dir / "records" / "2026-04-01_fresh.md").exists()
    archives = list((chronicles_dir / "archives").rglob("*.md"))
    assert len(archives) == 0
