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
            QtWidgets.QLabel("VNA enable, TX inhibit"), self.checkbox_vna_enable
        )
        input_layout.addRow(QtWidgets.QLabel("Tune automatic"), self.checkbox_tune)
        # Tune iteration counter (internal; display removed)
        self._tune_iteration = 0
        input_layout.addRow(QtWidgets.QLabel("manual f up"), self.checkbox_up)
        input_layout.addRow(QtWidgets.QLabel("manual f down"), self.checkbox_down)

        # motor status display (under the 'down' checkbox)
        self.motor_status = QtWidgets.QLabel("stop")
        # align the motor status to the right (consistent with other numeric fields)
        self.motor_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        input_layout.addRow(QtWidgets.QLabel("Motor status"), self.motor_status)
        # The 'Set Values' input was intentionally disabled/commented out.
        # self.button_set_values = QtWidgets.QPushButton("Set & Sweep")
        # input_layout.addRow(
        #     QtWidgets.QLabel("Set Values"), self.button_set_values
        # )
        self.checkbox_auto_get_f=QtWidgets.QCheckBox()
        input_layout.addRow(
            QtWidgets.QLabel("Auto get frequency"), self.checkbox_auto_get_f
        )
        self.input_set_Hz = QtWidgets.QLineEdit("7.074e6")




        self.input_set_Hz.setFixedHeight(20)
        self.input_set_Hz.setMinimumWidth(60)
        self.input_set_Hz.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
        )
        font = self.input_set_Hz.font()
        font.setPointSize(11)
        self.input_set_Hz.setFont(font)

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

        # delta frequency display (shows deviation of SWR min to set SWR min in kHz)
        # placed before Q display for easier reading of frequency deviation
        self.delta_display = QtWidgets.QLabel("--")
        self.delta_display.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        input_layout.addRow(QtWidgets.QLabel("Δ kHz (SWR min)"), self.delta_display)

        # Q display label (shows Q = marker2 / (marker3 - marker1))
        self.q_display = QtWidgets.QLabel("--")
        # display Q aligned to the right to match numeric input styling
        self.q_display.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        input_layout.addRow(QtWidgets.QLabel("Q (SWR 2.64)"), self.q_display)

        # SWR min display (shows minimum SWR found in the sweep, e.g., 1.21)
        self.swrmin_display = QtWidgets.QLabel("--")
        self.swrmin_display.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        input_layout.addRow(QtWidgets.QLabel("SWR min"), self.swrmin_display)

        # Power input: allow user to enter transmit power in Watts (5..100)
        self.power_spin = QtWidgets.QSpinBox()
        self.power_spin.setRange(5, 100)
        self.power_spin.setValue(5)
        self.power_spin.setFixedHeight(20)
        self.power_spin.setMinimumWidth(60)
        self.power_spin.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        font = self.power_spin.font()
        font.setPointSize(11)
        self.power_spin.setFont(font)
        input_layout.addRow(QtWidgets.QLabel("Power W"), self.power_spin)

        # (power status label removed — FT-991 cannot be queried for power)
        # connect power control immediately so changes always send to rigctld
        try:
            self.power_spin.valueChanged.connect(self.on_power_changed)
        except Exception:
            logger.exception("Failed to connect power spin signal at init")

        self.layout.addRow(input_layout)

        # 'Set Values' signal connection commented out because the input is disabled
        # self.button_set_values.pressed.connect(self.on_button_set_values)
        self.checkbox_tune.checkStateChanged.connect(self.on_tune)
        self.checkbox_up.checkStateChanged.connect(self.on_up)
        self.checkbox_down.checkStateChanged.connect(self.on_down)
        self.checkbox_vna_enable.checkStateChanged.connect(self.on_vna_enable)
        self.mp_device = util_mpremote.get_device()
        util_mpremote.mp_exec(device=self.mp_device, cmd=MICROPYTHON_MAIN)

    def on_tune(self):
        checked = self.checkbox_tune.isChecked()
        if checked:
            # reset tune iteration counter on initial enable; first sweep is a dry-run
            self._tune_iteration = 0
            # self.on_button_set_values()
            if False:
                sweep_stop = self.app.sweep_control.inputs["Stop"]
                assert isinstance(sweep_stop, FrequencyInputWidget)
                if sweep_stop.get_freq() > F_USEFUL_MAX_Hz:
                    sweep_stop.setText(f"{F_USEFUL_MAX_Hz:0.0f}Hz")
                    sweep_start = self.app.sweep_control.inputs["Start"]
                    assert isinstance(sweep_start, FrequencyInputWidget)
                    sweep_start.setText(f"{F_USEFUL_MIN_Hz:0.0f}Hz")

            self._setStartStopFrequencyFloat("Start", 1e6)
            self._setStartStopFrequencyFloat("Stop", 30e6)
            self._setDatapointCount(1000)
            self.app.sweep.set_logarithmic(True)

            self.app.sweep_start()
        else:
            util_mpremote.mp_exec(
                device=self.mp_device, cmd="run(direction_up=True, on=False)"
            )
            self._set_motor_status("stop")
            # clear internal tune iteration counter when tuning disabled
            self._tune_iteration = 0
            # set a harmless sweep range so the VNA does not disturb (100kHz .. 200kHz)
            try:
                # Restore a harmless sweep on low frequencies and start it so the
                # VNA runs there (this keeps the device quiet on other bands).
                # Update the UI fields so behavior is visible and consistent.
                self._setStartStopFrequencyFloat("Start", 100e3)
                self._setStartStopFrequencyFloat("Stop", 200e3)
                # use a small number of points for quick harmless sweep
                self._setDatapointCount(201)
                self.app.sweep.set_logarithmic(False)
                # mark/apply suppression of display updates while this
                # harmless sweep runs so the visible graph is not overwritten
                self.app._suppress_display_updates = True
                self.app._harmless_sweep_active = True
                # start the harmless sweep so the VNA actually runs at low freq
                self.app.sweep_start()
                logger.debug("Tune disabled: started harmless sweep 100kHz-200kHz (display suppressed)")
            except Exception:
                logger.exception("Failed to set harmless sweep on tune disable")
            #sweep_start.setText(f"100kHz") # todo: disable sweep completely
            #sweep_stop.setText(f"200kHz")
            #self.app.sweep_start()


    def on_vna_enable(self):
        checked = self.checkbox_vna_enable.isChecked()
        util_mpremote.mp_exec(
            device=self.mp_device, cmd=f"vna_enable(enable={int(checked)})"
        )
        # If the user enabled VNA, also try to connect the serial port control
        # (do nothing if already connected)
        if checked:
            try:
                if not self.app.serial_control.is_vna_connected():
                    self.app.serial_control.connect_device()
            except Exception:
                logger.exception("Failed to auto-connect serial port on VNA enable")

        # Note: power spin is connected at init; no further action needed here

    def on_power_changed(self):
        """Handle changes to the Power W spinbox.

        Convert from 5..100 W to 0.05..1.0 scale (value/100) and send via
        rigctl: `rigctl -m 2 -r localhost:4532 L RFPOWER <scaled>`.
        """
        try:
            watts = int(self.power_spin.value())
            # enforce allowed range 5..100 (defensive clamp)
            if watts < 5:
                watts = 5
            elif watts > 100:
                watts = 100
            # map 5..100 -> 0.05..1.0
            scaled = watts / 100.0
            scaled_str = f"{scaled:.2f}".rstrip("0").rstrip(".")
            logger.debug("Setting RF power: %s W -> %s (socket)", watts, scaled_str)
            # Send command over the same localhost:4532 socket used by _auto_get_frequency
            try:
                with socket.create_connection(("localhost", 4532), timeout=1) as s:
                    # send rigctl-style command over socket; server accepts newline-terminated commands
                    cmd = f"L RFPOWER {scaled_str}\n"
                    s.sendall(cmd.encode("ascii"))
                    # try to read a short response to know if server accepted the command
                    try:
                        s.settimeout(0.5)
                        resp = s.recv(1024).strip()
                        if resp:
                            try:
                                resp_text = resp.decode("utf-8", errors="replace")
                            except Exception:
                                resp_text = repr(resp)
                            logger.debug("RFPOWER response: %s", resp_text)
                        else:
                            logger.debug("RFPOWER: no response from server")
                    except socket.timeout:
                        logger.debug("RFPOWER: no response (timeout)")
                    except Exception as e:
                        logger.debug("RFPOWER: reading response failed: %s", e)
            except Exception as e:
                logger.debug("Failed to send RFPOWER over socket: %s", e)
                try:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "RF power send failed",
                        f"Failed to send RFPOWER command to localhost:4532:\n{e}",
                    )
                except Exception:
                    logger.exception("Failed to show RFPOWER failure message box")
        except Exception:
            logger.exception("Failed to prepare RFPOWER command")

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
            self._set_motor_status("motor run f up")
        else:
            util_mpremote.mp_exec(
                device=self.mp_device, cmd="run(direction_up=True, on=False)"
            )
            self._set_motor_status("stop")
    def on_down(self):
        checked = self.checkbox_down.isChecked()
        if checked:
            util_mpremote.mp_exec(
                device=self.mp_device, cmd="run(direction_up=False, on=True)"
            )
            self._set_motor_status("motor run f down")
        else:
            util_mpremote.mp_exec(
                device=self.mp_device, cmd="run(direction_up=False, on=False)"
            )
            self._set_motor_status("stop")





    def _setStartStopFrequencyFloat(self, tag: str, freq_Hz: float):
        self._setStartStopFrequency(tag, f"{freq_Hz:0.0f} Hz")

    def _setStartStopFrequency(self, tag: str, text: str):
        input = self.app.sweep_control.inputs[tag]
        assert isinstance(input, FrequencyInputWidget)
        # Log incoming requested update and existing content
        try:
            logger.debug(
                "_setStartStopFrequency request: tag=%s text=%s (before=%s)",
                tag,
                text,
                input.text(),
            )
        except Exception:
            logger.exception("Failed to log before-set state for sweep input")

        # Update the visible input field
        input.setText(text)

        # Log the field after setText to verify the widget contains the
        # expected value (diagnostic for why the hardware may not receive it)
        try:
            logger.debug(
                "_setStartStopFrequency after setText: tag=%s content=%s",
                tag,
                input.text(),
            )
        except Exception:
            logger.exception("Failed to log after-set state for sweep input")
        # Make sure the sweep control reacts to the change so the
        # internal Sweep object is updated immediately (otherwise the
        # VNA will keep using the old sweep range).
        try:
            input.textEdited.emit(input.text())
        except Exception:
            logger.exception("Failed to emit textEdited for sweep input")
        try:
            self.app.sweep_control.update_sweep()
        except Exception:
            logger.exception("Failed to update sweep after changing Start/Stop")
        else:
            # Log the active sweep range for diagnostics
            try:
                logger.debug(
                    "Set sweep Start/Stop -> %s - %s",
                    self.app.sweep.start,
                    self.app.sweep.end,
                )
            except Exception:
                # Best-effort, do not crash on logging
                logger.exception("Failed to log new sweep range")

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
        #self._setStartStartFrequency("Start", "2MHz")
        #self._setStartStopFrequency("Stop", "28MHz")
        #self._setMakerFrequency(0, "1MHz")
        #self._setMakerFrequency(-1, "30MHz")
        self._setStartStopFrequencyFloat("Start", 1e6)
        self._setStartStopFrequencyFloat("Stop", 30e6)
        self._setDatapointCount(1000)
        self.app.sweep.set_logarithmic(True)
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
            # Update ppm and Q displays only after sweep finish / after find_min_swr()
            try:
                self._update_delta_display()
            except Exception:
                logger.exception("Failed to update delta display after sweep finish")
            try:
                self._update_q_display()
            except Exception:
                logger.exception("Failed to update Q display after sweep finish")
            try:
                self._update_swrmin_display()
            except Exception:
                logger.exception("Failed to update SWR min display after sweep finish")
            # increment tune iteration counter if tuning is still enabled
            try:
                if self.checkbox_tune.isChecked():
                    self._tune_iteration += 1
            except Exception:
                logger.exception("Failed to increment tune iteration counter")
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

        if swr_min < 4.0:
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

    def _update_q_display(self):
        """Compute Q = marker2 / (marker3 - marker1) and update label.

        If markers are missing or the denominator is non-positive, show `--`.
        """
        try:
            markers = self.app.markers
            if len(markers) < 3:
                self.q_display.setText("--")
                return
            m1 = markers[0]
            m2 = markers[1]
            m3 = markers[2]
            # Use frequencyInput.get_freq() to parse the displayed frequency
            f1 = m1.frequencyInput.get_freq()
            f2 = m2.frequencyInput.get_freq()
            f3 = m3.frequencyInput.get_freq()
            denom = float(f3 - f1)
            if denom <= 0:
                self.q_display.setText("--")
                return
            q = float(f2) / denom
            # show numeric value only, no decimal places
            self.q_display.setText(f"{q:.0f}")
        except Exception:
            logger.exception("Failed to update Q display")
            self.q_display.setText("--")

    def _update_delta_display(self):
        """Compute deviation of SWR min to set SWR min in kHz and update label.

        The display shows (f_swr_min - set_f) / 1e3 as an integer kHz value with
        unit 'kHz'. If markers or set frequency are missing/invalid, show `--`.
        """
        try:
            markers = self.app.markers
            if len(markers) < 2:
                self.delta_display.setText("--")
                return
            m2 = markers[1]
            f_min = m2.frequencyInput.get_freq()
            try:
                set_f = float(self.input_set_Hz.text())
            except Exception:
                self.delta_display.setText("--")
                return
            if set_f == 0 or f_min is None:
                self.delta_display.setText("--")
                return
            delta = f_min - set_f
            # determine sign based on comparison before rounding
            sign = "-" if delta < 0 else "+"
            delta_khz_abs = abs(delta) / 1e3
            # show numeric value with three decimal places, include explicit sign and unit
            self.delta_display.setText(f"{sign}{delta_khz_abs:.3f} kHz")
        except Exception:
            logger.exception("Failed to update delta display")
            self.delta_display.setText("--")

    def _update_swrmin_display(self):
        """Compute the minimum SWR from the latest sweep and update label.

        The display shows the numeric SWR value with two decimal places (e.g., 1.21).
        If sweep data is missing or invalid, show `--`.
        """
        try:
            with self.app.dataLock:
                s11: list[Datapoint]
                s11 = self.app.data.s11[:]
                if not s11:
                    self.swrmin_display.setText("--")
                    return
                swr = np.asarray([d.vswr for d in s11])
            swr_min = float(np.min(swr))
            self.swrmin_display.setText(f"{swr_min:.2f}")
        except Exception:
            logger.exception("Failed to update SWR min display")
            self.swrmin_display.setText("--")

    def _set_motor_status(self, status: str):
        """Set the motor status label safely."""
        try:
            self.motor_status.setText(status)
        except Exception:
            logger.exception("Failed to set motor status")

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
        points_pulse = 101
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
                    # show pulse status (pulse up/down 0.3s)
                    dir_str = "up" if direction_up else "down"
                    dur_str = f"{duration_s:.2f}".rstrip("0").rstrip(".")
                    # first iteration is a dry-run: do not actuate motor and do not
                    # change sweep points; only set points_pulse when actually
                    # actuating the motor (iteration > 0).
                    if getattr(self, "_tune_iteration", 0) == 0:
                        self._set_motor_status(f"pulse {dir_str} {dur_str}s (preview)")
                        print(f'pulse: {duration_s=} (preview)')
                    else:
                        self._set_motor_status(f"pulse {dir_str} {dur_str}s")
                        util_mpremote.mp_exec(device=self.mp_device, cmd=cmd)
                        points = points_pulse
                else:
                    cmd = f"run(direction_up={direction_up}, on=True)"
                    dir_str = "up" if direction_up else "down"
                    if getattr(self, "_tune_iteration", 0) == 0:
                        # dry-run on first iteration: do not actuate motor
                        self._set_motor_status(f"motor run {dir_str} (preview)")
                    else:
                        self._set_motor_status(f"motor run {dir_str}")
                        util_mpremote.mp_exec(device=self.mp_device, cmd=cmd)
        else:
            cmd = f"run(direction_up=True, on=False)"
            # no best freq -> ensure motor stopped
            self._set_motor_status("stop")
        
        self._setDatapointCount(points)