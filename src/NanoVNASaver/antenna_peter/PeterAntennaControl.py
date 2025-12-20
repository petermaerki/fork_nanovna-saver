import logging
import pathlib
from typing import TYPE_CHECKING

import numpy as np
import socket
from PySide6 import QtWidgets, QtCore

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
FILENAME_MICROPYTHON_INITIALIZATION = (
    DIRECTORY_OF_THIS_FILE / "micropython" / "initialization.py"
)
MICROPYTHON_MAIN = FILENAME_MICROPYTHON_INITIALIZATION.read_text()

class PeterAntennaControl(Control):
    def __init__(self, app: "vna_app"):
        super().__init__(app, "Peter Antenna control")

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.VLine)

        input_layout = QtWidgets.QFormLayout()

        self.checkbox_tune = QtWidgets.QCheckBox()
        self.checkbox_up = QtWidgets.QCheckBox()
        self.checkbox_down = QtWidgets.QCheckBox()
        self.checkbox_vna_enable = QtWidgets.QCheckBox()
        input_layout.addRow(
            QtWidgets.QLabel("VNA enable"), self.checkbox_vna_enable
        )
        input_layout.addRow(QtWidgets.QLabel("Tune"), self.checkbox_tune)
        input_layout.addRow(QtWidgets.QLabel("up"), self.checkbox_up)
        input_layout.addRow(QtWidgets.QLabel("down"), self.checkbox_down)

        self.button_set_values = QtWidgets.QPushButton("Set & Sweep")
        input_layout.addRow(
            QtWidgets.QLabel("Set Values"), self.button_set_values
        )
        self.checkbox_auto_get_f=QtWidgets.QCheckBox()
        input_layout.addRow(
            QtWidgets.QLabel("Auto get frequency"), self.checkbox_auto_get_f
        )
        self.input_set_Hz = QtWidgets.QLineEdit("7.074e6")

        # Minimal hard-coded adjustments so the input visually matches
        # the sweep inputs: fixed height, minimum width and right alignment
        self.input_set_Hz.setFixedHeight(20)
        self.input_set_Hz.setMinimumWidth(60)
        self.input_set_Hz.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
        )
        # Make the input font a bit larger for better readability
        font = self.input_set_Hz.font()
        font.setPointSize(11)
        self.input_set_Hz.setFont(font)

        # Timer for automatic frequency fetch (when enabled)
        self.auto_get_timer = QtCore.QTimer(self)
        self.auto_get_timer.setInterval(1000)  # 1 second
        self.auto_get_timer.timeout.connect(self._auto_get_frequency)
        self.checkbox_auto_get_f.checkStateChanged.connect(
            self.on_auto_get_frequency_toggle
        )
        # Enable auto-get by default at initialization
        self.checkbox_auto_get_f.setChecked(True)

        input_layout.addRow(
            QtWidgets.QLabel("Set swr min [Hz]"), self.input_set_Hz
        )

        self.layout.addRow(input_layout)

        self.button_set_values.pressed.connect(self.on_button_set_values)
        self.checkbox_tune.checkStateChanged.connect(self.on_tune)
        self.checkbox_up.checkStateChanged.connect(self.on_up)
        self.checkbox_down.checkStateChanged.connect(self.on_down)
        self.checkbox_vna_enable.checkStateChanged.connect(self.on_vna_enable)
        self.mp_device = util_mpremote.get_device()
        util_mpremote.mp_exec(device=self.mp_device, cmd=MICROPYTHON_MAIN)

    def on_tune(self):
        checked = self.checkbox_tune.isChecked()
        if checked:
            # self.on_button_set_values()
            if False:
                sweep_stop = self.app.sweep_control.inputs["Stop"]
                assert isinstance(sweep_stop, FrequencyInputWidget)
                if sweep_stop.get_freq() > F_USEFUL_MAX_Hz:
                    sweep_stop.setText(f"{F_USEFUL_MAX_Hz:0.0f}Hz")
                    sweep_start = self.app.sweep_control.inputs["Start"]
                    assert isinstance(sweep_start, FrequencyInputWidget)
                    sweep_start.setText(f"{F_USEFUL_MIN_Hz:0.0f}Hz")

            self.app.sweep_start()
        else:
            util_mpremote.mp_exec(
                device=self.mp_device, cmd="run(direction_up=True, on=False)"
            )
            sweep_start.setText(f"100kHz") # todo: disable sweep completely
            sweep_stop.setText(f"200kHz")
            self.app.sweep_start()


    def on_vna_enable(self):
        checked = self.checkbox_vna_enable.isChecked()
        util_mpremote.mp_exec(
            device=self.mp_device, cmd=f"vna_enable(enable={int(checked)})"
        )

    def on_auto_get_frequency_toggle(self):
        """Start/stop the automatic frequency polling based on checkbox state."""
        if self.checkbox_auto_get_f.isChecked():
            logger.debug("Starting auto frequency fetch timer (1s)")
            # do an immediate fetch, then rely on timer for subsequent updates
            self._auto_get_frequency()
            self.auto_get_timer.start()
        else:
            logger.debug("Stopping auto frequency fetch timer")
            self.auto_get_timer.stop()

    def _auto_get_frequency(self):
        """Fetch frequency from localhost socket and set it to the SWR input field.

        The expected protocol: connect to localhost:4532, send 'f\n', receive an
        integer frequency in Hz (as bytes). Any errors are logged and ignored.
        """
        try:
            with socket.create_connection(("localhost", 4532), timeout=1) as s:
                s.sendall(b"f\n")
                data = s.recv(1024).strip()
                if not data:
                    logger.warning("Auto-get frequency: no data received")
                    return
                try:
                    freq_hz = int(data)
                except ValueError:
                    logger.warning(
                        "Auto-get frequency: received non-integer: %r", data
                    )
                    return
                # Insert the raw Hz integer into the input field (naked number)
                QtWidgets.QLineEdit.setText(self.input_set_Hz, str(freq_hz))
                logger.debug("Auto-get frequency: set %d Hz", freq_hz)
        except Exception as e:
            logger.debug("Auto-get frequency failed: %s", e)


    def on_up(self):
        checked = self.checkbox_up.isChecked()
        if checked:
            util_mpremote.mp_exec(
                device=self.mp_device, cmd="run(direction_up=True, on=True)"
            )
        else:
            util_mpremote.mp_exec(
                device=self.mp_device, cmd="run(direction_up=True, on=False)"
            )
    def on_down(self):
        checked = self.checkbox_down.isChecked()
        if checked:
            util_mpremote.mp_exec(
                device=self.mp_device, cmd="run(direction_up=False, on=True)"
            )
        else:
            util_mpremote.mp_exec(
                device=self.mp_device, cmd="run(direction_up=False, on=False)"
            )




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
        #sweep_range_relative = (sweep_stop_Hz - sweep_start_Hz)/set_f_swr_min_Hz
        #points = int(5 * sweep_range_relative / 0.01)
        #points = min(points, 600)
        #points = max(points, 51)
       
        points = 500
        deviation_limit_puls = 5e-3
        points_pulse = 51
        if set_f_swr_min_Hz > 5E6:
            deviation_limit_puls = 1e-2
        if set_f_swr_min_Hz > 12E6:
            deviation_limit_puls = 3e-2
        if set_f_swr_min_Hz > 16E6:
            deviation_limit_puls = 5e-2

        logger.debug(f"{f_swr_min_Hz=} {sweep_start_Hz=} {sweep_stop_Hz=}")

        if f_swr_min_Hz is not None:
            if F_USEFUL_MIN_Hz < f_swr_min_Hz < F_USEFUL_MAX_Hz:
                difference_Hz = set_f_swr_min_Hz - f_swr_min_Hz
                direction_up = difference_Hz > 0
                deviation = abs(difference_Hz/set_f_swr_min_Hz)
                pulse = False
                
                if deviation < deviation_limit_puls:
                    pulse = True
                    duration_s = 1.0*deviation/deviation_limit_puls
                if pulse:
                    cmd = f"pulse({direction_up}, {duration_s})"
                    print(f'pulse: {duration_s=}')
                    points=points_pulse
                else:
                    cmd = f"run(direction_up={direction_up}, on=True)"

                util_mpremote.mp_exec(device=self.mp_device, cmd=cmd)
        else:
            cmd = f"run(direction_up=True, on=False)"
        
        self._setDatapointCount(points)