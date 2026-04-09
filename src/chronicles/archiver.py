"""Archive rotation — moves old records to archives/YYYY-QN/."""
from __future__ import annotations
import re
from datetime import date, timedelta
from pathlib import Path

def rotate_records(chronicles_dir: Path, after_days: int = 90) -> list[Path]:
    records_dir = chronicles_dir / "records"
    if not records_dir.exists():
        return []
    cutoff = date.today() - timedelta(days=after_days)
    moved: list[Path] = []
    for record in sorted(records_dir.glob("*.md")):
        record_date = _extract_date(record)
        if record_date is None or record_date >= cutoff:
            continue
        quarter = (record_date.month - 1) // 3 + 1
        archive_dir = chronicles_dir / "archives" / f"{record_date.year}-Q{quarter}"
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / record.name
        record.rename(dest)
        moved.append(dest)
        _mark_archived(chronicles_dir, record.stem)
    return moved

def _extract_date(record_path: Path) -> date | None:
    dates: list[date] = []
    match = re.match(r"(\d{4}-\d{2}-\d{2})_", record_path.name)
    if match:
        try:
            dates.append(date.fromisoformat(match.group(1)))
        except ValueError:
            pass
    content = record_path.read_text()
    fm_match = re.search(r"^date:\s*(\d{4}-\d{2}-\d{2})", content, re.MULTILINE)
    if fm_match:
        try:
            dates.append(date.fromisoformat(fm_match.group(1)))
        except ValueError:
            pass
    return min(dates) if dates else None

def _mark_archived(chronicles_dir: Path, record_stem: str) -> None:
    chron_path = chronicles_dir / "CHRONICLES.md"
    if not chron_path.exists():
        return
    content = chron_path.read_text()
    pattern = re.compile(rf"(\[\[{re.escape(record_stem)}[^\]]*\]\][^\n]*)")
    match = pattern.search(content)
    if match and "(archived)" not in match.group(1):
        content = content.replace(match.group(1), match.group(1) + " (archived)")
        chron_path.write_text(content)
