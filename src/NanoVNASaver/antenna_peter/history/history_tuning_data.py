from __future__ import annotations

import dataclasses
import datetime
import json
import pathlib

HISTORY_FILE = pathlib.Path(__file__).parent / "history_tuning_data.jsonl"


@dataclasses.dataclass
class TuningHistoryEntry:
    datetime_utc: str
    servo_h_ta: float
    servo_f_ta: float
    servo_z_ta: float
    frequency_target_hz: int
    heading_target_deg: int

    @staticmethod
    def create_now(
        servo_h_ta: float,
        servo_f_ta: float,
        servo_z_ta: float,
        frequency_target_hz: float,
        heading_target_deg: float,
    ) -> "TuningHistoryEntry":
        return TuningHistoryEntry(
            datetime_utc=datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
            servo_h_ta=servo_h_ta,
            servo_f_ta=servo_f_ta,
            servo_z_ta=servo_z_ta,
            frequency_target_hz=round(frequency_target_hz),
            heading_target_deg=round(heading_target_deg),
        )

    def to_json_line(self) -> str:
        return json.dumps(dataclasses.asdict(self), sort_keys=True)


def append(entry: TuningHistoryEntry, filename: pathlib.Path = HISTORY_FILE) -> None:
    with filename.open("a", encoding="utf-8") as f:
        f.write(entry.to_json_line() + "\n")
    _trim_if_needed(filename)


def _trim_if_needed(filename: pathlib.Path, max_entries: int = 1000, keep_entries: int = 900) -> None:
    lines = [l for l in filename.read_text(encoding="utf-8").splitlines() if l.strip()]
    if len(lines) > max_entries:
        filename.write_text("\n".join(lines[-keep_entries:]) + "\n", encoding="utf-8")


def load_all(filename: pathlib.Path = HISTORY_FILE) -> list[TuningHistoryEntry]:
    if not filename.exists():
        return []
    entries = []
    for line in filename.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(TuningHistoryEntry(**json.loads(line)))
    return entries
