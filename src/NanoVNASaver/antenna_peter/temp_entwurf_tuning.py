from __future__ import annotations
from dataclasses import dataclass
import pathlib
'''Entwurf tuning neu'''

"""
while enabled_heading:
        measure_heading()
        if heading is inside tolerance:
            break
        servo_heading(wait=true)

if bandwechsel:
    servo_f(position= preset_f_position_band)
    servo_z(position = preset_impedance_position_band)
    #wait_on_servo()

iteration = 0
while True:
    measure_s11_vna(band_range)
    f_in_tolerance = is_f_in_tolerance()
    z_in_tolerance = is_z_in_tolerance()
    if (not f_enabled or f_in_tolerance) and (not z_enabled or z_in_tolerance) and iteration > 0:
        break
    if f_enabled:
        servo_f(position = calculate_new_f_position())
    if z_enabled:
        servo_z(position = calculate_new_z_position())
    #wait_on_servo()
    iteration += 1
"""


@dataclass(frozen=True)
class Band:
    band_m: int
    ft8_hz: int
    servo_measurement1: Measurement | None
    servo_measurement2: Measurement | None
    servo_z_ta: float | None


    def freq_diff_hz(self, freq_hz:float)->Band:
            return abs(self.ft8_hz - freq_hz)


class Bands(list[Band]):
    def get_band(self, freq_hz:float)->Band:
        assert isinstance(freq_hz, float)

        best_band:Band=self[0]
        best_freq_diff_hz:float = best_band.freq_diff_hz(freq_hz=freq_hz)

        for band in self[1:]:
            freq_diff_hz=band.freq_diff_hz(freq_hz=freq_hz)
            if freq_diff_hz < best_freq_diff_hz:
                best_freq_diff_hz=freq_diff_hz
                best_band=band

        return best_band


@dataclass(frozen=True)
class Measurement:
    servo_f_ta:float 
    freq_hz:float

BANDS: Bands =Bands( [
    Band(band_m=160, ft8_hz=1_840_000 ,mesurement1=None, measurement2=None, servo_z_ta=None),
    Band(band_m=80, ft8_hz=3_573_000 ,mesurement1=None, measurement2=None, servo_z_ta=None),
    Band(band_m=60, ft8_hz=5_357_000 ,mesurement1=None, measurement2=None, servo_z_ta=None),
    Band(band_m=40, ft8_hz=7_074_000 ,mesurement1=None, measurement2=None, servo_z_ta=None),
    Band(band_m=30, ft8_hz=10_136_000 ,mesurement1=None, measurement2=None, servo_z_ta=None),
    Band(band_m=20, ft8_hz=14_074_000 ,mesurement1=None, measurement2=None, servo_z_ta=None),
    Band(band_m=17, ft8_hz=18_100_000 ,mesurement1=None, measurement2=None, servo_z_ta=None),
    Band(band_m=15, ft8_hz=21_074_000 ,mesurement1=None, measurement2=None, servo_z_ta=None),
    Band(band_m=12, ft8_hz=24_915_000 ,mesurement1=None, measurement2=None, servo_z_ta=None),
    Band(band_m=10, ft8_hz=28_074_000 ,mesurement1=None, measurement2=None, servo_z_ta=None),
])




def main()->None:
    band = BANDS.get_band(freq_hz=14e6)
    print(f"{band=}")


if __name__ == "__main__":
    main()
'''
servo_z kann sehr verschieden sein: draussen, daher gerne robust und universell
servo_f kann ich steigung gut messen, wird immer etwa gleich sein

from scipy import optimize

'''