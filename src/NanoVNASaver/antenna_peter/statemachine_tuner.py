import logging
import time
from typing import TYPE_CHECKING

from sts3215_micropython.sts3215_portable import calculator

from . import util_heading_calculator
from .util_freq_band_preset import BANDS

if TYPE_CHECKING:
    from .PeterAntennaControl import PeterAntennaControl

logger = logging.getLogger(__name__)

HEADING_TARGET_TA_MAX = 0.3
HEADING_TARGET_TA_MIN = -0.3

IMPEDANCE_TARGET_TA_MAX = 0.21
"""0.25 moeglich aber steht an"""

IMPEDANCE_TARGET_TA_MIN = -0.12  # -0.25
"""-0.15 moelich"""

FREQUENCY_TARGET_TA_MAX = 37.0
"mechanical Limit of Capacitor. Würde bis auf 37.2 funktionieren."
FREQUENCY_TARGET_TA_MIN = 0.02
"near to homing position"


def _angular_error_deg(target_deg: float, actual_deg: float) -> float:
    delta = (target_deg - actual_deg + 90.0) % 180.0 - 90.0
    return abs(delta)


class StatemachineTuner:
    def __init__(self) -> None:
        self.last_s = time.monotonic()
        self.iteration = 0

    def tune(self, ctl: PeterAntennaControl) -> None:
        try:
            if not ctl.checkbox_tune.isChecked():
                self.last_s = time.monotonic()
                return
            tuned = self._tune(ctl=ctl)
            if tuned:
                ctl.checkbox_tune.setChecked(False)
        except Exception as e:
            logger.exception(e)

    def _tune(self, ctl: PeterAntennaControl) -> bool:
        """
        return True: If tuning completed successfully.
        return False: Requires more steps for tuning.
        exception. Something bad happened.
        """
        self._tune_band_change(ctl=ctl)
        return True

        heading_tuned = self._tune_heading(ctl=ctl)
        return heading_tuned

        duration_s = time.monotonic() - self.last_s
        logger.info(f"tune {duration_s} s")
        return duration_s > 10.0
        """

        tune_success = True
        if ctl.enable_heading:
            measure_heading()
            if heading not is inside tolerance:
                set new servo heading
                tune_success = False

        if ctl.enable_frequency or ctl.enable_impedance:
          measure_s11_vna(band_range)

        if ctl.enable_frequency:
            self.last_step_frequency = True
            if bandwechsel:
                servo_f(position= preset_f_position_band)
                tune_success = False

            f_in_tolerance = is_f_in_tolerance()
            if not f_in_tolerance:
                tune_success = False
            if f_enabled:
                servo_f(position = calculate_new_f_position())
            if z_enabled:
                servo_z(position = calculate_new_z_position())
            #wait_on_servo()
            iteration += 1

        if ctl.enable_impedance:
            if bandwechsel:
                servo_z(position = preset_impedance_position_band)
                return False
            z_in_tolerance = is_z_in_tolerance()
            if not z_in_tolerance:
                tune_success = False

        self.last_s = time.monotonic()
        return tune_success
        """

    def _tune_heading(self, ctl: PeterAntennaControl) -> bool:
        if not ctl.heading_checkbox.isChecked():
            return True

        sample_count = 2
        stdout = ctl._mp_exec(
            label_full="get_bmm",
            cmd=f"get_bmm(sample_count={sample_count})",
        )
        measured_heading_deg = calculator.parse_value_float(
            stdout=stdout,
            label="heading_deg",
        )
        logger.info(f"{measured_heading_deg=}")

        # ctl.heading_current.set_value()
        heading_target_deg = ctl.heading_target.f_value
        error_deg = _angular_error_deg(
            target_deg=heading_target_deg,
            actual_deg=measured_heading_deg,
        )
        if error_deg < 3.0:
            logger.info(
                f"_tune_heading() {heading_target_deg=} {measured_heading_deg=} {error_deg=} OK"
            )
            return True
        servo_targed_t = util_heading_calculator.servo_targed_t(
            servo_t_actual=ctl.heading_servo.f_value,
            heading_actual_deg=measured_heading_deg,
            heading_target_deg=heading_target_deg,
            servo_min_t=HEADING_TARGET_TA_MIN,
            servo_max_t=HEADING_TARGET_TA_MAX,
            debug=False,
        )
        logger.info(
            f"_tune_heading(): heading_servo {heading_target_deg=}. {ctl.heading_servo.f_value:0.3f}->{servo_targed_t:0.3f} ta"
        )
        ctl.heading_servo.set_value(servo_targed_t)
        return False

    def _tune_band_change(self, ctl: PeterAntennaControl) -> bool:
        persist = ctl._position_persist
        persist_band = BANDS.get_band(freq_hz=persist.freq_antenna_hz)
        target_band = BANDS.get_band(freq_hz=ctl.frequency_target.f_value)
        if persist_band.band_m == target_band.band_m:
            return True
        if not target_band.valid:
            logger.warning(f"Invalid band: {target_band}")
            return True
        servo_f_ta = target_band.servo_f_start_ta(
            target_hz=ctl.frequency_target.f_value
        )
        logger.info(
            f"_tune_band_change: band changed go to preset values {servo_f_ta=} {target_band.servo_z_ta=}"
        )
        ctl.frequency_servo_f.set_value(servo_f_ta)
        assert isinstance(target_band.servo_z_ta, float)
        ctl.impedance_servo_z.set_value(target_band.servo_z_ta)
        with ctl._servo_position_persist() as p:
            p.freq_antenna_hz = ctl.frequency_target.f_value
        return False
