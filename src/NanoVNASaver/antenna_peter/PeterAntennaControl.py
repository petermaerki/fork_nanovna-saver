import logging
import pathlib
from typing import TYPE_CHECKING

import numpy as np
from PySide6 import QtWidgets

from ..Controls.Control import Control
from ..Controls.SweepControl import FrequencyInputWidget
from ..Hardware.VNA import VNA
from ..Marker.Widget import Marker
from ..RFTools import Datapoint
from . import util_mpremote

if TYPE_CHECKING:
    from ..NanoVNASaver.NanoVNASaver import NanoVNASaver as vna_app

logger = logging.getLogger(__name__)


DIRECTORY_OF_THIS_FILE = pathlib.Path(__file__).parent
FILENAME_MICROPYTHON_INITIALIZATION = DIRECTORY_OF_THIS_FILE / "micropython" / "initialization.py"
MICROPYTHON_MAIN = FILENAME_MICROPYTHON_INITIALIZATION.read_text()

class PeterAntennaControl(Control):
    def __init__(self, app: "vna_app"):
        super().__init__(app, "Peter Antenna control")

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.VLine)

        input_layout = QtWidgets.QFormLayout()

        self.checkbox_tune = QtWidgets.QCheckBox()
        input_layout.addRow(QtWidgets.QLabel("Tune"), self.checkbox_tune)

        self.button_set_values = QtWidgets.QPushButton("Set & Sweep")
        input_layout.addRow(
            QtWidgets.QLabel("Set Values"), self.button_set_values
        )

        self.input_set_Hz = QtWidgets.QLineEdit("3.0e6")
        input_layout.addRow(
            QtWidgets.QLabel("Set swr min [Hz]"), self.input_set_Hz
        )

        self.layout.addRow(input_layout)

        self.button_set_values.pressed.connect(self.on_button_set_values)
        self.checkbox_tune.checkStateChanged.connect(self.on_tune_state_change)

        util_mpremote.mp_exec(cmd=MICROPYTHON_MAIN)

    def on_tune_state_change(self):
        checked = self.checkbox_tune.isChecked()
        if checked:
            self.on_button_set_values()

    def _setStartStopFrequencyFloat(self, tag: str, freq_Hz: float):
        self._setStartStopFrequency(tag, f"{freq_Hz:0.0f} Hz")

    def _setStartStopFrequency(self, tag: str, text: str):
        input = self.app.sweep_control.inputs[tag]
        assert isinstance(input, FrequencyInputWidget)
        input.setText(text)

    def _setMakerFrequencyFloat(
        self,
        index: int,
        freq_Hz: float | None,
        freq_default_Hz: float,
    ):
        if freq_Hz is None:
            freq_Hz = freq_default_Hz
        self._setMakerFrequency(index, f"{freq_Hz:0.0f} Hz")

    def _setMakerFrequency(self, index: int, text: str):
        marker = self.app.markers[index]
        assert isinstance(marker, Marker)
        marker.setFrequency(text)

    def _setDatapointCount(self, count: int):
        # See: src/NanoVNASaver/Windows/DeviceSettings.py, def updateNrDatapoints()
        vna = self.app.vna
        assert isinstance(vna, VNA)
        vna.datapoints = count
        logger.debug("DP: %s", vna.datapoints)
        self.app.sweep.set_points(self.app.vna.datapoints)
        self.app.sweep_control.update_step_size()

    def on_button_set_values(self):
        self._setDatapointCount(201)

        # self._setStartStopFrequency("Start", "2MHz")
        # self._setStartStopFrequency("Stop", "30MHz")
        self._setStartStopFrequency("Start", "2MHz")
        self._setStartStopFrequency("Stop", "3MHz")
        self._setMakerFrequency(0, "8MHz")
        self._setMakerFrequency(-1, "16MHz")

        self.app.sweep_start()

    def sweepFinished_peter_antenna(self):
        try:
            f_swr_p2_64_l_Hz, f_swr_min_Hz, f_swr_p2_64_h_Hz = (
                self.find_min_swr()
            )
            self.find_sweep_start_stop(
                f_swr_p2_64_l_Hz,
                f_swr_min_Hz,
                f_swr_p2_64_h_Hz,
            )
        except Exception as e:
            logger.exception(e)

    def find_min_swr(self):
        with self.app.dataLock:
            s11: list[Datapoint]
            s11 = self.app.data.s11[:]

            swr = np.asarray([d.vswr for d in s11])
            freq_Hz = np.asarray([float(d.freq) for d in s11])

        idx_min = np.argmin(swr)
        swr_min = swr[idx_min]

        f_swr_min_Hz = None
        f_swr_p2_64_l_Hz = None
        f_swr_p2_64_h_Hz = None

        if swr_min < 2.0:
            f_swr_min_Hz = freq_Hz[idx_min]
            target_swr = 2.64

            left_idx = np.where(swr[:idx_min] >= target_swr)[0]
            right_idx = np.where(swr[idx_min:] >= target_swr)[0]

            f_swr_p2_64_l_Hz = freq_Hz[left_idx[-1]] if len(left_idx) else None
            f_swr_p2_64_h_Hz = (
                freq_Hz[idx_min + right_idx[0]] if len(right_idx) else None
            )

        self._setMakerFrequencyFloat(0, f_swr_p2_64_l_Hz, freq_Hz[0])
        self._setMakerFrequencyFloat(1, f_swr_min_Hz, freq_Hz[0])
        self._setMakerFrequencyFloat(2, f_swr_p2_64_h_Hz, freq_Hz[0])

        return f_swr_p2_64_l_Hz, f_swr_min_Hz, f_swr_p2_64_h_Hz

    def find_sweep_start_stop(
        self,
        f_swr_p2_64_l_Hz: float,
        f_swr_min_Hz: float,
        f_swr_p2_64_h_Hz: float,
    ):
        F_USEFUL_MIN_Hz = 1.0e6
        F_USEFUL_MAX_Hz = 30.0e6
        SWEEP_RANGE_OVERLAP = 1.3  # range biger than plus minus 2.64 band
        assert SWEEP_RANGE_OVERLAP > 1.1

        # set_f_swr_min_Hz = 3.0e6
        # set_f_swr_min_Hz = 22.0e6
        set_f_swr_min_Hz = float(self.input_set_Hz.text())

        def min_found() -> bool:
            if f_swr_min_Hz is None:
                return False
            if f_swr_p2_64_l_Hz is None:
                return False
            if f_swr_p2_64_h_Hz is None:
                return False
            return True

        if min_found():
            distance_f = abs(set_f_swr_min_Hz - f_swr_min_Hz)
            distance_f = max(
                abs(f_swr_p2_64_l_Hz - set_f_swr_min_Hz), distance_f
            )
            distance_f = max(
                abs(f_swr_p2_64_h_Hz - set_f_swr_min_Hz), distance_f
            )

            sweep_stop_Hz = set_f_swr_min_Hz + distance_f * SWEEP_RANGE_OVERLAP
            sweep_stop_Hz = min(F_USEFUL_MAX_Hz, sweep_stop_Hz)
            sweep_start_Hz = set_f_swr_min_Hz - distance_f * SWEEP_RANGE_OVERLAP
            sweep_start_Hz = max(F_USEFUL_MIN_Hz, sweep_start_Hz)
        else:
            sweep_start_Hz = F_USEFUL_MIN_Hz
            sweep_stop_Hz = F_USEFUL_MAX_Hz


        self._setStartStopFrequencyFloat("Start", sweep_start_Hz)
        self._setStartStopFrequencyFloat("Stop", sweep_stop_Hz)
        self._setDatapointCount(201)

        logger.debug(f"{f_swr_min_Hz=} {sweep_start_Hz=} {sweep_stop_Hz=}")

        if f_swr_min_Hz is not None:
            difference_Hz = set_f_swr_min_Hz - f_swr_min_Hz
            direction_up = difference_Hz > 0
            pulse = abs(difference_Hz) < 50_000
            if pulse:
                duration_s = 0.05
                cmd = f"pulse({direction_up}, {duration_s})"
            else:
                cmd = f"run(direction_up={direction_up}, on=True)"

            util_mpremote.mp_exec(cmd=cmd)
