from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Band:
    band_m: int
    ft8_hz: int
    measurement1: Measurement | None
    measurement2: Measurement | None
    servo_z_ta: float | None

    def freq_diff_hz(self, freq_hz: float) -> float:
        return abs(self.ft8_hz - freq_hz)


class Bands(list[Band]):
    def get_band(self, freq_hz: float) -> Band:
        assert isinstance(freq_hz, float)

        best_band: Band = self[0]
        best_freq_diff_hz: float = best_band.freq_diff_hz(freq_hz=freq_hz)

        for band in self[1:]:
            freq_diff_hz = band.freq_diff_hz(freq_hz=freq_hz)
            if freq_diff_hz < best_freq_diff_hz:
                best_freq_diff_hz = freq_diff_hz
                best_band = band

        return best_band


@dataclass(frozen=True)
class Measurement:
    servo_f_ta: float
    freq_hz: float


BANDS: Bands = Bands(
    [
        Band(
            band_m=160,
            ft8_hz=1_840_000,
            measurement1=None,
            measurement2=None,
            servo_z_ta=None,
        ),
        Band(
            band_m=80,
            ft8_hz=3_573_000,
            measurement1=None,
            measurement2=None,
            servo_z_ta=None,
        ),
        Band(
            band_m=60,
            ft8_hz=5_357_000,
            measurement1=None,
            measurement2=None,
            servo_z_ta=None,
        ),
        Band(
            band_m=40,
            ft8_hz=7_074_000,
            measurement1=Measurement(7.0, 7_000_000),
            measurement2=Measurement(8.0, 8_000_000),
            servo_z_ta=None,
        ),
        Band(
            band_m=30,
            ft8_hz=10_136_000,
            measurement1=Measurement(10.0, 10_000_000),
            measurement2=Measurement(11.0, 11_000_000),
            servo_z_ta=None,
        ),
        Band(
            band_m=20,
            ft8_hz=14_074_000,
            measurement1=None,
            measurement2=None,
            servo_z_ta=None,
        ),
        Band(
            band_m=17,
            ft8_hz=18_100_000,
            measurement1=None,
            measurement2=None,
            servo_z_ta=None,
        ),
        Band(
            band_m=15,
            ft8_hz=21_074_000,
            measurement1=None,
            measurement2=None,
            servo_z_ta=None,
        ),
        Band(
            band_m=12,
            ft8_hz=24_915_000,
            measurement1=None,
            measurement2=None,
            servo_z_ta=None,
        ),
        Band(
            band_m=10,
            ft8_hz=28_074_000,
            measurement1=None,
            measurement2=None,
            servo_z_ta=None,
        ),
    ]
)


def main() -> None:
    band = BANDS.get_band(freq_hz=14e6)
    print(f"{band=}")


if __name__ == "__main__":
    main()
