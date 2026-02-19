from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Band:
    band_m: int
    ft8_hz: int
    measurement1: Measurement | None
    measurement2: Measurement | None
    servo_z_ta: float | None

    @property
    def valid(self) -> bool:
        return (
            (self.measurement1 is not None)
            and (self.measurement1 is not None)
            and (self.servo_z_ta is not None)
        )

    def freq_diff_hz(self, freq_hz: float) -> float:
        return abs(self.ft8_hz - freq_hz)

    def servo_f_start_ta(self, target_hz: float) -> float:
        assert isinstance(target_hz, float)
        assert self.valid, self
        # Interpolate or extrapolate using measurement1 and measurement2 if both are present
        m1 = self.measurement1
        m2 = self.measurement2
        assert m1 is not None and m2 is not None, self
        if m2.freq_hz == m1.freq_hz:
            return m1.servo_f_ta
        # Linear interpolation/extrapolation
        return m1.servo_f_ta + (target_hz - m1.freq_hz) * (
            m2.servo_f_ta - m1.servo_f_ta
        ) / (m2.freq_hz - m1.freq_hz)


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
            measurement1=Measurement(25.0, 7.099e6),
            measurement2=Measurement(26.0, 6.940e6),
            servo_z_ta=-0.1,
        ),
        Band(
            band_m=30,
            ft8_hz=10_136_000,
            measurement1=Measurement(12.0, 1.1066e7),
            measurement2=Measurement(13.0, 1.0504e7),
            servo_z_ta=0.1,
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
