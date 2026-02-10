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
    BandPreset(160, 1_840_000, None, None, None),
    BandPreset(80, 3_573_000, None, None, None),
    BandPreset(60, 5_357_000, None, None, None),
    BandPreset(40, 7_074_000, None, None, None),
    BandPreset(30, 10_136_000, None, None, None),
    BandPreset(20, 14_074_000, None, None, None),
    BandPreset(17, 18_100_000, None, None, None),
    BandPreset(15, 21_074_000, None, None, None),
    BandPreset(12, 24_915_000, None, None, None),
    BandPreset(10, 28_074_000, None, None, None),
]