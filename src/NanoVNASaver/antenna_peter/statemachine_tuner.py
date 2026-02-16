import logging
import time
from typing import TYPE_CHECKING

from sts3215_micropython.sts3215_portable import calculator

if TYPE_CHECKING:
    from .PeterAntennaControl import PeterAntennaControl
logger = logging.getLogger(__name__)


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

        stdout = ctl._mp_exec(
            label_full="get_bmm",
            cmd="get_bmm()",
        )
        heading_deg = calculator.parse_value_float(
            stdout=stdout,
            label="heading_deg",
        )
        logger.info(f"{heading_deg=}")
        ctl.heading_current.value.setText(f"{heading_deg:0.1f} deg")


        if ctl.heading_checkbox.isChecked():
            

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
