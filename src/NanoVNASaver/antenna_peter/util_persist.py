from __future__ import annotations

import dataclasses
import json
import pathlib


@dataclasses.dataclass
class ServoPositionPersistent:
    """
    The state of the servo befor power off or crash.
    It will be used to calculate the required movement to the next position
    """

    servo_h_ta: float = 0.0
    servo_z_ta: float = 0.0
    freq_antenna_hz: float = 42.0

    def __post_init__(self):
        assert isinstance(self.servo_h_ta, float)
        assert isinstance(self.servo_z_ta, float)
        assert isinstance(self.freq_antenna_hz, float)

    @staticmethod
    def unlink(filename: pathlib.Path) -> None:
        assert isinstance(filename, pathlib.Path)
        filename.unlink(missing_ok=True)

    @staticmethod
    def get_persist(filename: pathlib.Path) -> ServoPositionPersistent:
        assert isinstance(filename, pathlib.Path)
        try:
            json_text = filename.read_text()
        except FileNotFoundError:
            return ServoPositionPersistent()
        json_dict = json.loads(json_text)
        return ServoPositionPersistent(**json_dict)

    @staticmethod
    def save(filename: pathlib.Path, persist: ServoPositionPersistent) -> None:
        assert isinstance(filename, pathlib.Path)

        assert isinstance(persist, ServoPositionPersistent)

        filename.write_text(
            json.dumps(
                dataclasses.asdict(persist),
                indent=4,
                sort_keys=True,
            )
        )
