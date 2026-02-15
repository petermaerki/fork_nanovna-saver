'''Entwurf tuning neu'''


while enabled_heading:
        measure_heading()
        if heading is inside tolerance:
            break
        servo_heading(wait=true)

if bandwechsel:
    servo_f(position= preset_f_position_band)
    servo_z(position = preset_impedance_position_band)
    wait_on_servo()

iteration = 0
while True:
    measure_s11_vna()
    f_in_tolerance = is_f_in_tolerance()
    z_in_tolerance = is_z_in_tolerance()
    if (not f_enabled or f_in_tolerance) and (not z_enabled or z_in_tolerance) and iteration > 0:
        break
    if f_enabled:
        servo_f(position = calculate_new_f_position())
    if z_enabled:
        servo_z(position = calculate_new_z_position())
    wait_on_servo()
    iteration += 1


from dataclasses import dataclass


@dataclass(frozen=True)
class BandPreset:
    band_m: int
    ft8_hz: int
    servo_f_t: float | None
    servo_f_slope_hz_t: float | None
    servo_z_t: float | None


PRESET_POSITIONS: list[BandPreset] = [
    BandPreset(band_m=160, ft8_hz=1_840_000, servo_f_t=None, servo_f_slope_hz_t=None, servo_z_t=None),
    BandPreset(band_m=80, ft8_hz=3_573_000, servo_f_t=None, servo_f_slope_hz_t=None, servo_z_t=None),
    BandPreset(band_m=60, ft8_hz=5_357_000, servo_f_t=None, servo_f_slope_hz_t=None, servo_z_t=None),
    BandPreset(band_m=40, ft8_hz=7_074_000, servo_f_t=None, servo_f_slope_hz_t=None, servo_z_t=None),
    BandPreset(band_m=30, ft8_hz=10_136_000, servo_f_t=None, servo_f_slope_hz_t=None, servo_z_t=None),
    BandPreset(band_m=20, ft8_hz=14_074_000, servo_f_t=None, servo_f_slope_hz_t=None, servo_z_t=None),
    BandPreset(band_m=17, ft8_hz=18_100_000, servo_f_t=None, servo_f_slope_hz_t=None, servo_z_t=None),
    BandPreset(band_m=15, ft8_hz=21_074_000, servo_f_t=None, servo_f_slope_hz_t=None, servo_z_t=None),
    BandPreset(band_m=12, ft8_hz=24_915_000, servo_f_t=None, servo_f_slope_hz_t=None, servo_z_t=None),
    BandPreset(band_m=10, ft8_hz=28_074_000, servo_f_t=None, servo_f_slope_hz_t=None, servo_z_t=None),
]


