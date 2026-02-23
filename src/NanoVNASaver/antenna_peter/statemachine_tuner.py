import logging
import time
from typing import TYPE_CHECKING

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


class StatemachineTuner:
    def __init__(self) -> None:
        self.last_s = time.monotonic()
        self.impedance_iteration_plus = 0
        self.frequency_iteration_plus = 0

    def reset_iterations(self, ctl: "PeterAntennaControl"):
        self.impedance_iteration_plus = 0
        self.frequency_iteration_plus = 0
        self.heading_iteration_plus = 0
        ctl.vna.state_vna = util_vna_sweep.StatemachineVna.RESULTS_OUTDATED

    def tune(self, ctl: "PeterAntennaControl") -> None:
        try:
            if not ctl.checkbox_tune.isChecked():
                self.last_s = time.monotonic()
                return
            tuned = self._tune(ctl=ctl)
            if tuned:
                ctl.checkbox_tune.setChecked(False)
        except Exception as e:
            logger.exception(e)

    def _tune(self, ctl: "PeterAntennaControl") -> bool:
        """
        return True: If tuning completed successfully.
        return False: Requires more steps for tuning.
        exception. Something bad happened.
        """
        # success = True
        if not self._tune_heading(ctl=ctl):
            return False

        band_changed = self.tune_band_change(ctl=ctl)
        if not band_changed:
            return False
        if ctl.vna.state_vna is util_vna_sweep.StatemachineVna.VNA_IS_SWEEPING:
            return False
        if ctl.vna.state_vna is util_vna_sweep.StatemachineVna.RESULTS_OUTDATED:
            self._sweep_vna(ctl=ctl)
            return False
        assert ctl.vna.state_vna is util_vna_sweep.StatemachineVna.RESULTS_READY
        if not self._tune_impedance_z(ctl=ctl):
            return False
        if not self._tune_servo_f(ctl=ctl):
            return False
        return True

        duration_s = time.monotonic() - self.last_s
        logger.info(f"tune {duration_s} s")
        return duration_s > 10.0

    def _tune_heading(self, ctl: "PeterAntennaControl") -> bool:
        if not ctl.heading_checkbox.isChecked():
            return True

        measured_heading_deg = self.get_heading(sample_count=3, ctl=ctl)


        # ctl.heading_current.set_value()
        heading_target_deg = ctl.heading_target.f_value
        delta = (
            heading_target_deg - measured_heading_deg + 90.0
        ) % 180.0 - 90.0
        error_deg = abs(delta)
        set_iteratoins_plus = 0
        if error_deg < 3.0:
            self.heading_iteration_plus += 1
            if self.heading_iteration_plus >= set_iteratoins_plus+1:
                if self.heading_iteration_plus == set_iteratoins_plus+1:
                    logger.info(
                        f"Heading ok now {measured_heading_deg:0.0f} target {heading_target_deg:0.0f}  error {error_deg:0.0f}"
                )
                return True
        else:
            self.heading_iteration_plus = 0

        servo_h_sign = -1.0
        servo_targed_t = servo_h_sign* util_heading_calculator.servo_targed_t(
            servo_t_actual=servo_h_sign*ctl.heading_servo.f_value,
            heading_actual_deg=measured_heading_deg,
            heading_target_deg=heading_target_deg,
            servo_min_t=HEADING_TARGET_TA_MIN,
            servo_max_t=HEADING_TARGET_TA_MAX,
            debug=False,
        )
        logger.info(
            f"Heading now {measured_heading_deg:0.0f} -> {heading_target_deg:0.0f}  servo_h {ctl.heading_servo.f_value:0.3f}->{-servo_targed_t:0.3f}"
        )
        ctl.heading_servo.set_value(servo_targed_t)
        time_s = time.monotonic()
        self._heading_history = []
        while time.monotonic() - time_s < 20.0:
            if self.heading_is_stable(ctl):
                break
        return False
    
    def heading_is_stable(self, ctl) -> bool:
        # Speichere die letzten 20 Messwerte
        if not hasattr(self, "_heading_history"):
            self._heading_history = []
        measured_heading_deg = self.get_heading(sample_count=5, ctl=ctl)
        print(f"Heading meas {len(self._heading_history)}: {measured_heading_deg:.1f}")
        self._heading_history.append(measured_heading_deg)
        if len(self._heading_history) > 20:
            self._heading_history.pop(0)
        if len(self._heading_history) < 20:
            return False
        min_heading = min(self._heading_history)
        max_heading = max(self._heading_history)
        return (max_heading - min_heading) <= 3.0

    def get_heading(self, sample_count = 2, ctl=None) -> float:
        stdout = ctl._mp_exec(
            label_full="get_bmm",
            cmd=f"get_bmm(sample_count={sample_count})",
        )
        measured_heading_deg = calculator.parse_value_float(
            stdout=stdout,
            label="heading_deg",
        )
        ctl.heading_current.set_value(measured_heading_deg)
        return measured_heading_deg

    def tune_band_change(self, ctl: "PeterAntennaControl") -> bool:
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
            f"tune_band_change: preset values {servo_f_ta=} {target_band.servo_z_ta=}"
        )
        ctl.frequency_servo_f.set_value(servo_f_ta)
        assert isinstance(target_band.servo_z_ta, float)
        ctl.impedance_servo_z.set_value(target_band.servo_z_ta)
        with ctl._servo_position_persist() as p:
            p.freq_antenna_hz = ctl.frequency_target.f_value
        ctl.vna.reset_range(freq_Hz=ctl.frequency_target.f_value)
        ctl.vna.state_vna = util_vna_sweep.StatemachineVna.RESULTS_OUTDATED
        return False

    def _sweep_vna(self, ctl: "PeterAntennaControl") -> bool:
        success = ctl.vna.sweep()
        return success

    def _tune_impedance_z(self, ctl: "PeterAntennaControl"):
        if not ctl.impedance_tune_enable.isChecked():
            return True
        success = False
        servo_z_ta = ctl.impedance_servo_z.f_value
        impedance_target = ctl.impedance_target.f_value
        impedance_current = ctl.impedance_current.f_value
        impedance_difference = impedance_current - impedance_target
        impedance_error_ohm = abs(impedance_difference)
        set_iteratoins_plus = 1
        if impedance_error_ohm < 2.5:
            self.impedance_iteration_plus += 1
            if self.impedance_iteration_plus >= set_iteratoins_plus+1:
                if self.impedance_iteration_plus == set_iteratoins_plus+1:
                    logger.info(
                        f"Impedance ok {impedance_current:0.1f} Ohm target {impedance_target:0.1f} error {impedance_error_ohm:0.1f}"
                    )
                success = True
                return success
        else:
            self.impedance_iteration_plus = 0

        REGELFAKTOR = 1e-3
        MAX__STELLSCHRITT_ta = 0.01
        assert MAX__STELLSCHRITT_ta > 0.0
        stellschritt_ta = impedance_difference * REGELFAKTOR
        stellschritt_ta = min(stellschritt_ta, MAX__STELLSCHRITT_ta)
        stellschritt_ta = max(stellschritt_ta, -MAX__STELLSCHRITT_ta)
        servo_z_ta_new = servo_z_ta + stellschritt_ta
        ctl.impedance_servo_z.set_value(servo_z_ta_new)
        logger.info(
            f"Impedance iteration_plus {self.impedance_iteration_plus:d} now {impedance_current:0.1f}  servo_z_ta {servo_z_ta:0.3f} -> {servo_z_ta_new:0.3f}"
        )
        ctl.vna.state_vna = util_vna_sweep.StatemachineVna.RESULTS_OUTDATED
        return success

    def _tune_servo_f(self, ctl: "PeterAntennaControl"):
        if not ctl.frequency_tune_enable.isChecked():
            return True
        success = False
        servo_f_ta = ctl.frequency_servo_f.f_value
        target_hz = ctl.frequency_target.f_value
        current_hz = ctl.vna.f_swr_min_Hz
        difference_hz = current_hz - target_hz
        set_iteratoins_plus = 1
        if abs(difference_hz) < 400:
            self.frequency_iteration_plus += 1
            if self.frequency_iteration_plus >= set_iteratoins_plus+1:
                if self.frequency_iteration_plus == set_iteratoins_plus+1:
                    logger.info(
                    f"Frequency ok {current_hz:0.0f}Hz target {target_hz:0.0f}Hz error {difference_hz:0.0f}Hz"
                )
                success = True
                return success
        else:
            self.frequency_iteration_plus = 0

        band = BANDS.get_band(freq_hz=ctl.frequency_target.f_value)
        gain_hz_pro_ta = band.servo_f_gain_hz_pro_t
        servo_f_ta_new = servo_f_ta - difference_hz / gain_hz_pro_ta
        assert abs(servo_f_ta - servo_f_ta_new) < 3.0
        ctl.frequency_servo_f.set_value(servo_f_ta_new)

        logger.info(
            f"Frequency iteration_plus {self.frequency_iteration_plus:d} current {current_hz:0.0f}  servo_f_ta {servo_f_ta:0.3f} -> {servo_f_ta_new:0.3f}"
        )
        ctl.vna.state_vna = util_vna_sweep.StatemachineVna.RESULTS_OUTDATED
        return success
