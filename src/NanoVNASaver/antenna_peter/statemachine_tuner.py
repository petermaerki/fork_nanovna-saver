import logging
import time
from typing import TYPE_CHECKING
import enum

from sts3215_micropython.sts3215_portable import calculator

from . import util_heading_calculator, util_vna_sweep
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
        self.impedance_iteration = 0
        self.frequency_iteration = 0

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
        # success = True
        if not self._tune_heading(ctl=ctl):
            return False

        band_changed = self._tune_band_change(ctl=ctl)
        if not band_changed:
            return False
        if ctl.vna.stateVNA is util_vna_sweep.StatemachineVna.VNA_IS_SWEEPING:
            return False
        if ctl.vna.stateVNA is util_vna_sweep.StatemachineVna.RESULTS_OUTDATED:
            self._sweep_vna(ctl=ctl)
            return False
        assert ctl.vna.stateVNA is util_vna_sweep.StatemachineVna.RESULTS_READY
        if not self._tune_impedance_z(ctl=ctl):
            return False
        if not self._tune_servo_f(ctl=ctl):
            return False
        return True

        duration_s = time.monotonic() - self.last_s
        logger.info(f"tune {duration_s} s")
        return duration_s > 10.0

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
        ctl.vna.reset_range(freq_Hz=ctl.frequency_target.f_value)
        ctl.vna.state = util_vna_sweep.StatemachineVna.RESULTS_OUTDATED
        return False

    def _sweep_vna(self, ctl: PeterAntennaControl) -> bool:
        success = ctl.vna.sweep()
        return success

    def _tune_impedance_z(self, ctl: PeterAntennaControl):
        success = False
        servo_z_ta = ctl.impedance_servo_z.f_value
        impedance_target = ctl.impedance_target.f_value
        impedance_current = ctl.impedance_current.f_value
        impedance_difference = impedance_current - impedance_target
        if abs(impedance_difference) < 1.0:
            success = True
            print(f'Impedance ok {impedance_current:0.1f} Ohm')
            return success
        REGELFAKTOR = 1e-3
        MAX__STELLSCHRITT_ta = 0.01
        assert MAX__STELLSCHRITT_ta > 0.0
        stellschritt_ta = impedance_difference * REGELFAKTOR
        stellschritt_ta = min(stellschritt_ta, MAX__STELLSCHRITT_ta)
        stellschritt_ta = max(stellschritt_ta, -MAX__STELLSCHRITT_ta)
        servo_z_ta_new = servo_z_ta + stellschritt_ta
        ctl.impedance_servo_z.set_value(servo_z_ta_new)
        self.impedance_iteration += 1
        print(
            f"Impedance iteration {self.impedance_iteration:d} current {impedance_current:0.1f}  servo_z_ta_new {servo_z_ta_new:0.3f} delta {stellschritt_ta:0.3f}"
        )
        ctl.vna.stateVNA = util_vna_sweep.StatemachineVna.RESULTS_OUTDATED
        return success

    def _tune_servo_f(self, ctl: PeterAntennaControl):
        success = False
        servo_f_ta = ctl.frequency_servo_f.f_value
        target_hz = ctl.frequency_target.f_value
        current_hz = ctl.vna.f_swr_min_Hz
        difference_hz = current_hz - target_hz

        if abs(difference_hz / target_hz) < 1e-4:
            print(f'Frequency ok {current_hz:0.0f} Hz')
            success = True
            return success

        band = BANDS.get_band(freq_hz=ctl.frequency_target.f_value)
        gain_hz_pro_ta = band.servo_f_gain_hz_pro_t
        servo_f_ta_new = servo_f_ta - difference_hz / gain_hz_pro_ta
        assert abs(servo_f_ta - servo_f_ta_new) < 3.0
        ctl.frequency_servo_f.set_value(servo_f_ta_new)
        self.frequency_iteration += 1
        print(
            f"Frequency iteration {self.frequency_iteration:d} current {current_hz:0.0f}  servo_f_ta_new {servo_f_ta_new:0.3f}"
        )
        ctl.vna.stateVNA = util_vna_sweep.StatemachineVna.RESULTS_OUTDATED
        return success
