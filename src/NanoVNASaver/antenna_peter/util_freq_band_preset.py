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

    @property
    def servo_f_gain_hz_pro_t(self) -> float:
        assert self.valid, self
        m1 = self.measurement1
        m2 = self.measurement2
        assert m1 is not None and m2 is not None, self
        assert m2.servo_f_ta != m1.servo_f_ta
        gain_hz_pro_t = (m2.freq_hz - m1.freq_hz) / (
            m2.servo_f_ta - m1.servo_f_ta
        )
        return gain_hz_pro_t


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
            # measurement1=Measurement(26.0, 1840092), # pcb
            # measurement2=Measurement(27.0, 1837600), # pcb
            # servo_z_ta=0.075, # pcb
            measurement1=Measurement(23.0, 1842240), # comet vacuum
            measurement2=Measurement(24.0, 1839680), # comet vacuum
            servo_z_ta=0.085, # comet vacuum
        ),
        Band(
            band_m=80,
            ft8_hz=3_573_000,
            measurement1=Measurement(28.0, 3578744),
            measurement2=Measurement(29.0, 3559915),
            servo_z_ta=0.13,
        ),
        Band(
            band_m=60,
            ft8_hz=5_357_000,
            measurement1=Measurement(9.0, 5411265),
            measurement2=Measurement(10.0, 5352700),
            servo_z_ta=0.14,
        ),
        Band(
            band_m=40,
            ft8_hz=7_074_000,
            measurement1=Measurement(25.0, 7.099e6),
            measurement2=Measurement(26.0, 6.940e6),
            servo_z_ta=0.15,
        ),
        Band(
            band_m=30,
            ft8_hz=10_136_000,
            measurement1=Measurement(12.0, 1.1066e7),
            measurement2=Measurement(13.0, 1.0504e7),
            servo_z_ta=0.14,
        ),
        Band(
            band_m=20,
            ft8_hz=14_074_000,
            measurement1=Measurement(8.0, 1.464e7),
            measurement2=Measurement(9.0, 1.346e7),
            servo_z_ta=0.1,
        ),
        Band(
            band_m=17,
            ft8_hz=18_100_000,
            measurement1=Measurement(5.0, 20686919),
            measurement2=Measurement(6.0, 18049346),
            servo_z_ta=0.06,
        ),
        Band(
            band_m=15,
            ft8_hz=21_074_000,
            measurement1=Measurement(5.0, 2.128e7),
            measurement2=Measurement(6.0, 1.62554e7),
            servo_z_ta=0.02,
        ),
        Band(
            band_m=12,
            ft8_hz=24_915_000,
            measurement1=Measurement(3.0, 26780300),
            measurement2=Measurement(4.0, 24197000),
            servo_z_ta=-0.02,
        ),
        Band(
            band_m=10,
            ft8_hz=28_074_000,
            measurement1=Measurement(2.0, 28467500),
            measurement2=Measurement(3.0, 26780300),
            servo_z_ta=0.09,
        ),
    ]
)


def main() -> None:
    band = BANDS.get_band(freq_hz=14e6)
    print(f"{band=}")


if __name__ == "__main__":
    main()
