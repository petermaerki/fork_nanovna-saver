import logging
import pathlib
from typing import TYPE_CHECKING
import math

import numpy as np
import socket
from PySide6 import QtWidgets, QtCore, QtGui

from ..Controls.Control import Control
from ..Controls.SweepControl import FrequencyInputWidget
from ..Hardware.VNA import VNA
from ..Marker.Widget import Marker
from ..RFTools import Datapoint
from . import util_mpremote
 

if TYPE_CHECKING:
    from ..NanoVNASaver.NanoVNASaver import NanoVNASaver as vna_app

logger = logging.getLogger(__name__)


def calculate_safety_distance(f_mhz, p_watt, q_factor, loop_diameter_m=1.0):
    """Calculates the minimum safety distance for a Magnetic Loop antenna based on H-field limits."""
    f_hz = f_mhz * 1e6
    radius = loop_diameter_m / 2
    area = math.pi * (radius ** 2)
    l_henry = 1.55e-6
    i_loop = math.sqrt((p_watt * q_factor) / (2 * math.pi * f_hz * l_henry))
    
    # Capacitor voltage at resonance: V_c = I_loop * X_L (X_L = X_C at resonance)
    x_l = 2 * math.pi * f_hz * l_henry
    v_cap = i_loop * x_l
    
    # Immissionsgrenzwert IGW (public exposure limit)
    if f_mhz < 1.0:
        h_limit_igw = 1.6
    elif 1.0 <= f_mhz <= 30.0:
        h_limit_igw = 0.73 / f_mhz
    else:
        h_limit_igw = 0.16
    
    # Anlagengrenzwert OMEN (installation limit) - 5x stricter than IGW
    h_limit_omen = h_limit_igw / 5.0
    
    r_meters_igw = ((i_loop * area) / (2 * math.pi * h_limit_igw))**(1/3)
    r_meters_omen = ((i_loop * area) / (2 * math.pi * h_limit_omen))**(1/3)
    
    return {
        "frequency_mhz": f_mhz, 
        "power_watts": p_watt, 
        "q_factor": q_factor,
        "loop_current_amps": round(i_loop, 2), 
        "cap_voltage_volts": round(v_cap, 0),
        "h_limit_igw_am": round(h_limit_igw, 4),
        "h_limit_omen_am": round(h_limit_omen, 4),
        "min_distance_igw_m": round(r_meters_igw, 2),
        "min_distance_omen_m": round(r_meters_omen, 2)
    }


# Frequency limits for magnetic loop antenna
F_USEFUL_MIN_Hz = 1.0e6
F_USEFUL_MAX_Hz = 30.0e6

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
        
        # Create label for tune checkbox with yellow highlight
        self.label_tune = QtWidgets.QLabel("Tune automatic")
        self.label_tune.setAutoFillBackground(True)
        palette = self.label_tune.palette()
        palette.setColor(self.label_tune.backgroundRole(), QtGui.QColor("#FFFF99"))
        self.label_tune.setPalette(palette)
        
        input_layout.addRow(self.label_tune, self.checkbox_tune)
        input_layout.addRow(QtWidgets.QLabel("VNA enable, TX inhibit"), self.checkbox_vna_enable)
        # Tune iteration counter (internal; display removed)
        self._tune_iteration = 0
        # Store calculated Q factor for safety calculations
        self._q_factor = 500.0  # default value
        
        # Manual F controls in one row
        manual_f_layout = QtWidgets.QHBoxLayout()
        manual_f_layout.addWidget(self.checkbox_up)
        manual_f_layout.addWidget(QtWidgets.QLabel("up"))
        manual_f_layout.addWidget(self.checkbox_down)
        manual_f_layout.addWidget(QtWidgets.QLabel("down"))
        manual_f_layout.addStretch()
        input_layout.addRow(QtWidgets.QLabel("Manual F"), manual_f_layout)

        # motor status display (under the 'down' checkbox)
        self.motor_status = QtWidgets.QLabel("stop")
        # align the motor status to the right (consistent with other numeric fields)
        self.motor_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        font = self.motor_status.font()
        font.setPointSize(11)
        self.motor_status.setFont(font)
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
        self.auto_get_timer.setInterval(2000)  # 2 seconds
        self.auto_get_timer.timeout.connect(self._auto_get_frequency)
        self.checkbox_auto_get_f.checkStateChanged.connect(
            self.on_auto_get_frequency_toggle
        )
        # Enable auto-get by default at initialization
        self.checkbox_auto_get_f.setChecked(True)

        # SWR offset input field
        self.input_swr_offset_Hz = QtWidgets.QLineEdit("1500")
        self.input_swr_offset_Hz.setFixedHeight(20)
        self.input_swr_offset_Hz.setMinimumWidth(60)
        self.input_swr_offset_Hz.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        font = self.input_swr_offset_Hz.font()
        font.setPointSize(11)
        self.input_swr_offset_Hz.setFont(font)
        input_layout.addRow(
            QtWidgets.QLabel("Set offset [Hz]"), self.input_swr_offset_Hz
        )

        input_layout.addRow(
            QtWidgets.QLabel("Set swr min [Hz]"), self.input_set_Hz
        )

        # delta frequency display (shows deviation of SWR min to set SWR min in kHz)
        # placed before Q display for easier reading of frequency deviation
        self.delta_display = QtWidgets.QLabel("--")
        self.delta_display.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        font = self.delta_display.font()
        font.setPointSize(11)
        self.delta_display.setFont(font)
        input_layout.addRow(QtWidgets.QLabel("Δ kHz (SWR min)"), self.delta_display)

        # Q display label (shows Q = marker2 / (marker3 - marker1))
        self.q_display = QtWidgets.QLabel("--")
        # display Q aligned to the right to match numeric input styling
        self.q_display.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        font = self.q_display.font()
        font.setPointSize(11)
        self.q_display.setFont(font)
        input_layout.addRow(QtWidgets.QLabel("Q (SWR 2.64)"), self.q_display)

        # SWR min display (shows minimum SWR found in the sweep, e.g., 1.21)
        self.swrmin_display = QtWidgets.QLabel("--")
        self.swrmin_display.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        font = self.swrmin_display.font()
        font.setPointSize(11)
        self.swrmin_display.setFont(font)
        input_layout.addRow(QtWidgets.QLabel("SWR min"), self.swrmin_display)

        # Power input: allow user to enter transmit power in Watts (5..100)
        self.power_spin = QtWidgets.QSpinBox()
        self.power_spin.setRange(5, 100)
        self.power_spin.setValue(5)
        self.power_spin.setFixedHeight(20)
        self.power_spin.setMinimumWidth(60)
        self.power_spin.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.power_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        font = self.power_spin.font()
        font.setPointSize(11)
        self.power_spin.setFont(font)
        input_layout.addRow(QtWidgets.QLabel("Power W 5...100"), self.power_spin)

        # Safety calculation fields (read-only display)
        self.cap_voltage_display = QtWidgets.QLabel("--")
        self.cap_voltage_display.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        font = self.cap_voltage_display.font()
        font.setPointSize(11)
        self.cap_voltage_display.setFont(font)
        input_layout.addRow(QtWidgets.QLabel("Cap Voltage"), self.cap_voltage_display)

        self.loop_current_display = QtWidgets.QLabel("--")
        self.loop_current_display.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        font = self.loop_current_display.font()
        font.setPointSize(11)
        self.loop_current_display.setFont(font)
        input_layout.addRow(QtWidgets.QLabel("Loop Current"), self.loop_current_display)

        self.h_limit_display = QtWidgets.QLabel("--")
        self.h_limit_display.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        font = self.h_limit_display.font()
        font.setPointSize(11)
        self.h_limit_display.setFont(font)
        input_layout.addRow(QtWidgets.QLabel("H_Limit (NISV/IGW)"), self.h_limit_display)

        self.h_limit_omen_display = QtWidgets.QLabel("--")
        self.h_limit_omen_display.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        font = self.h_limit_omen_display.font()
        font.setPointSize(11)
        self.h_limit_omen_display.setFont(font)
        input_layout.addRow(QtWidgets.QLabel("H_Limit (OMEN)"), self.h_limit_omen_display)

        self.safety_distance_display = QtWidgets.QLabel("--")
        self.safety_distance_display.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        font = self.safety_distance_display.font()
        font.setPointSize(11)
        self.safety_distance_display.setFont(font)
        
        # Create complete row with label, info button, and display value
        safety_row_layout = QtWidgets.QHBoxLayout()
        safety_row_layout.addWidget(QtWidgets.QLabel("Safety distance IGW"))
        self.safety_info_button = QtWidgets.QPushButton("INFO")
        self.safety_info_button.setMaximumWidth(50)
        self.safety_info_button.setToolTip("Show technical background")
        self.safety_info_button.clicked.connect(self.show_safety_info)
        safety_row_layout.addWidget(self.safety_info_button)
        safety_row_layout.addStretch()
        safety_row_layout.addWidget(self.safety_distance_display)
        
        input_layout.addRow(safety_row_layout)

        self.safety_distance_omen_display = QtWidgets.QLabel("--")
        self.safety_distance_omen_display.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        font = self.safety_distance_omen_display.font()
        font.setPointSize(11)
        self.safety_distance_omen_display.setFont(font)
        input_layout.addRow(QtWidgets.QLabel("Safety distance OMEN"), self.safety_distance_omen_display)

        # (power status label removed — FT-991 cannot be queried for power)
        # connect power control immediately so changes always send to rigctld
        try:
            self.power_spin.valueChanged.connect(self.on_power_changed)
        except Exception:
            logger.exception("Failed to connect power spin signal at init")
        
        # Connect frequency input field to update safety calculations
        try:
            self.input_set_Hz.textChanged.connect(self._update_safety_calculation)
        except Exception:
            logger.exception("Failed to connect frequency input signal at init")
        
        # Perform initial safety calculation
        try:
            self._update_safety_calculation()
        except Exception:
            logger.exception("Failed to perform initial safety calculation")

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
            # Auto-enable VNA if not already enabled
            if not self.checkbox_vna_enable.isChecked():
                logger.debug("Tune enabled: auto-enabling VNA")
                self.checkbox_vna_enable.setChecked(True)
            
            # reset tune iteration counter on initial enable; first sweep is a dry-run
            self._tune_iteration = 0
            # Send current power setting to FT-991 when tuning is enabled
            try:
                self.on_power_changed()
            except Exception:
                logger.exception("Failed to send initial power on tune enable")
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
            self._setDatapointCount(1000) # initial bei overview
            self.app.sweep.set_logarithmic(True)

            self.app.sweep_start()
        else:
            util_mpremote.mp_exec(
                device=self.mp_device, cmd="run(direction_up=True, on=False)"
            )
            # When tune is disabled, also disable VNA enable
            if self.checkbox_vna_enable.isChecked():
                logger.debug("Tune disabled: auto-disabling VNA")
                self.checkbox_vna_enable.setChecked(False)
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
        else:
            # When VNA is disabled, also uncheck tune automatic
            self.checkbox_tune.setChecked(False)

        # Note: power spin is connected at init; no further action needed here

    def on_power_changed(self):
        """Handle changes to the Power W spinbox.

        Convert from 5..100 W to 0.05..1.0 scale (value/100) and send via
        rigctl: `rigctl -m 2 -r localhost:4532 L RFPOWER <scaled>`.
        Also update safety calculation displays.
        """
        # Always update safety calculations first, regardless of any errors
        self._update_safety_calculation()
        
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
        except Exception:
            logger.exception("Failed to prepare RFPOWER command")

    def _update_safety_calculation(self):
        """Update safety calculation fields based on current settings."""
        try:
            # Get values from UI; use reasonable defaults if missing
            try:
                set_f_hz = float(self.input_set_Hz.text())
                f_mhz = set_f_hz / 1e6
            except Exception:
                f_mhz = 14.150  # default 40m band
            
            watts = int(self.power_spin.value())
            
            # Use stored Q factor from Q display (updated after sweep)
            q_factor = self._q_factor
            
            # Calculate safety parameters
            results = calculate_safety_distance(f_mhz, watts, q_factor)
            
            # Update display fields with values from loop calculation
            # Cap Voltage from loop (not feedline)
            self.cap_voltage_display.setText(f"{results['cap_voltage_volts']:.0f} V")
            
            # Loop Current
            self.loop_current_display.setText(f"{results['loop_current_amps']} A")
            
            # H-Limit IGW
            self.h_limit_display.setText(f"{results['h_limit_igw_am']:.3f} A/m")
            
            # H-Limit OMEN
            self.h_limit_omen_display.setText(f"{results['h_limit_omen_am']:.3f} A/m")
            
            # Safety Distance IGW
            self.safety_distance_display.setText(f"{results['min_distance_igw_m']} m")
            
            # Safety Distance OMEN
            self.safety_distance_omen_display.setText(f"{results['min_distance_omen_m']} m")
            
            logger.debug(
                "Safety calc: f=%s MHz, P=%s W, Q=%s, I=%s A, H_IGW=%s A/m, dist_IGW=%s m, H_OMEN=%s A/m, dist_OMEN=%s m",
                f_mhz, watts, q_factor, results['loop_current_amps'],
                results['h_limit_igw_am'], results['min_distance_igw_m'],
                results['h_limit_omen_am'], results['min_distance_omen_m']
            )
        except Exception:
            logger.exception("Failed to update safety calculation")
            self.cap_voltage_display.setText("--")
            self.loop_current_display.setText("--")
            self.h_limit_display.setText("--")
            self.h_limit_omen_display.setText("--")
            self.safety_distance_display.setText("--")
            self.safety_distance_omen_display.setText("--")

    def show_safety_info(self):
        """Show technical background information about safety calculations."""
        info_text = """Technical Background & Safety Compliance

Electromagnetic Field Dynamics (Near-Field)
This application calculates the physical parameters of a high-Q resonant loop antenna. Unlike conventional antennas, a Magnetic Loop operates primarily by generating an intense Magnetic Near-Field (H-Field).

Due to the extremely high resonance quality (Q-factor), the circulating currents within the main inductor (the copper braid) can reach values significantly higher than the feedline current. This leads to:
• High Magnetic Flux Density: Concentrated in the immediate vicinity of the loop.
• Inductive Voltage Peaks: At the tuning capacitor, voltages reach levels that require specific dielectric strength (kV-range).

Computational Methodology
The calculation of the safety distance is based on the Inverse-Cube Law for magnetic dipoles in the near-field (1/r³).

Geometry Factor: The copper braid is modeled using an equivalent conductor radius to account for skin effect and reduced RF resistance.

Inductance & Reactance: These values are derived from the physical diameter and conductor surface area to determine the precise circulating current at a given power level.

Legal Standards (Switzerland)
The safety distances provided are calculated in accordance with the Swiss Ordinance on Protection against Non-Ionizing Radiation (NISV / ONIR).

Immissionsgrenzwerte (IGW): The primary safety boundary is based on the exposure limits for the general public, designed to prevent thermal and non-thermal biological effects.

Frequency Dependence: In the High Frequency (HF) range, the permissible magnetic field strength (H) is frequency-dependent (0.73 / f). The safety distance is dynamically adjusted as you tune your transceiver.

Precautionary Principle: Following Swiss regulatory logic, a safety margin (k-factor) is applied to account for environmental reflections and local field enhancements."""
        
        QtWidgets.QMessageBox.information(
            self,
            "Safety Distance - Technical Background",
            info_text,
            QtWidgets.QMessageBox.StandardButton.Ok
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
                # Apply SWR offset to received frequency
                try:
                    offset_hz = int(self.input_swr_offset_Hz.text())
                except (ValueError, AttributeError):
                    offset_hz = 0
                freq_hz_with_offset = freq_hz + offset_hz
                # Insert the offset-adjusted Hz integer into the input field (naked number)
                QtWidgets.QLineEdit.setText(self.input_set_Hz, str(freq_hz_with_offset))
                logger.debug("Auto-get frequency: set %d Hz (received %d Hz + offset %d Hz)", freq_hz_with_offset, freq_hz, offset_hz)
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
            f_swr_p2_64_l_Hz, f_swr_min_Hz, f_swr_p2_64_h_Hz, swr_min = (
                self.find_min_swr()
            )
            if f_swr_p2_64_l_Hz is None and f_swr_min_Hz is None and f_swr_p2_64_h_Hz is None:
                logger.warning("sweepFinished: No valid frequencies found")
                # Still call find_sweep_start_stop to handle the case properly
            self.find_sweep_start_stop(
                f_swr_p2_64_l_Hz,
                f_swr_min_Hz,
                f_swr_p2_64_h_Hz,
                swr_min,
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
            # Update safety calculation when Q is recalculated
            try:
                self._update_safety_calculation()
            except Exception:
                logger.exception("Failed to update safety calculation after sweep finish")
            # increment tune iteration counter if tuning is still enabled
            try:
                if self.checkbox_tune.isChecked():
                    self._tune_iteration += 1
            except Exception:
                logger.exception("Failed to increment tune iteration counter")
        except Exception:
            logger.exception("Critical error in sweepFinished_peter_antenna")
            # Ensure motor is stopped on any error
            try:
                util_mpremote.mp_exec(device=self.mp_device, cmd="run(direction_up=True, on=False)")
                self._set_motor_status("stop (error)")
            except Exception:
                logger.exception("Failed to stop motor after error")

    def find_min_swr(self):
        with self.app.dataLock:
            s11: list[Datapoint]
            s11 = self.app.data.s11[:]

            swr = np.asarray([d.vswr for d in s11])
            freq_Hz = np.asarray([float(d.freq) for d in s11])

        # Safety check: return early if no data available
        if len(swr) == 0 or len(freq_Hz) == 0:
            logger.warning("find_min_swr: No data available")
            return None, None, None, float('inf')

        idx_min = np.argmin(swr)
        swr_min = swr[idx_min]

        f_swr_min_Hz = None
        f_swr_p2_64_l_Hz = None
        f_swr_p2_64_h_Hz = None

        if swr_min < 2.0:
            f_swr_min_Hz = freq_Hz[idx_min]

        else:
            # S11 betrag phase doppelt abgeleitet: falls ein peak grösser als
            # 5 mal der mittelwert ist, so ist f_swr_min_Hz an der stelle vom
            # peak. sonst bleibt f_swr_min_Hz = none
            try:
                # Calculate phase double derivative absolute values
                if len(s11) >= 3:
                    phases = [d.phase for d in s11]
                    unwrapped = np.degrees(np.unwrap(phases))
                    freqs = [float(d.freq) for d in s11]

                    # First derivative
                    first_deriv = []
                    for i in range(len(unwrapped) - 1):
                        delta_phase = unwrapped[i + 1] - unwrapped[i]
                        delta_freq = freqs[i + 1] - freqs[i]
                        if delta_freq != 0:
                            first_deriv.append(delta_phase / delta_freq)
                        else:
                            first_deriv.append(0.0)

                    # Second derivative absolute values
                    second_deriv_abs = []
                    for i in range(len(first_deriv) - 1):
                        delta_deriv = first_deriv[i + 1] - first_deriv[i]
                        delta_freq = (
                            (freqs[i + 2] - freqs[i + 1]) +
                            (freqs[i + 1] - freqs[i])
                        ) / 2
                        if delta_freq != 0:
                            # Absolute value in °/MHz²
                            deriv = abs((delta_deriv / delta_freq) * 1e12)
                            second_deriv_abs.append(deriv)
                        else:
                            second_deriv_abs.append(0.0)

                    if second_deriv_abs:
                        mean_val = np.mean(second_deriv_abs)
                        max_val = np.max(second_deriv_abs)
                        
                        # Check if peak is > 5x mean
                        if max_val > 5 * mean_val:
                            # Find index of peak (add 2 for offset)
                            peak_idx = np.argmax(second_deriv_abs) + 2
                            if peak_idx < len(freq_Hz):
                                f_swr_min_Hz = freq_Hz[peak_idx]
                                logger.debug(
                                    "Phase deriv peak detection: peak=%s, "
                                    "mean=%s, freq=%s Hz",
                                    max_val, mean_val, f_swr_min_Hz
                                )
            except Exception:
                logger.exception("Failed to analyze phase double derivative")


        if f_swr_min_Hz is not None:
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

        return f_swr_p2_64_l_Hz, f_swr_min_Hz, f_swr_p2_64_h_Hz, swr_min

    def _update_q_display(self):
        """Compute Q = marker2 / (marker3 - marker1) and update label.

        If markers are missing or the denominator is non-positive, show `--`.
        """
        try:
            markers = self.app.markers
            if len(markers) < 3:
                self.q_display.setText("--")
                self._q_factor = 500.0  # reset to default
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
                self._q_factor = 500.0  # reset to default
                return
            q = float(f2) / denom
            # Store Q for use in safety calculations
            self._q_factor = q
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
        swr_min: float,
    ):
        SWEEP_RANGE_OVERLAP = 1.3  # range biger than plus minus 2.64 band
        assert SWEEP_RANGE_OVERLAP > 1.1

        # Safety check: if no valid data from find_min_swr, use full range
        if f_swr_min_Hz is None and f_swr_p2_64_l_Hz is None and f_swr_p2_64_h_Hz is None:
            logger.warning("find_sweep_start_stop: No valid frequency data, using full range")
            self._setStartStopFrequencyFloat("Start", F_USEFUL_MIN_Hz)
            self._setStartStopFrequencyFloat("Stop", F_USEFUL_MAX_Hz)
            self._setDatapointCount(500)
            self._set_motor_status("stop (no data)")
            return

        try:
            set_f_swr_min_Hz = float(self.input_set_Hz.text())
        except (ValueError, AttributeError) as e:
            logger.warning("find_sweep_start_stop: Invalid set frequency: %s", e)
            set_f_swr_min_Hz = 7.074e6  # default fallback

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
       
        BAND_160M_HZ = 1905000
        BAND_80M_HZ = 3650000
        BAND_60M_HZ = 5358000
        BAND_40M_HZ = 7100000
        BAND_30M_HZ = 10125000
        BAND_20M_HZ = 14175000
        BAND_17M_HZ = 18118000
        BAND_15M_HZ = 21225000
        BAND_12M_HZ = 24940000
        BAND_10M_HZ = 28850000

        BAND_160M_80M_HZ = (BAND_160M_HZ + BAND_80M_HZ)/2
        BAND_80M_60M_HZ = (BAND_80M_HZ + BAND_60M_HZ)/2
        BAND_60M_40M_HZ = (BAND_60M_HZ + BAND_40M_HZ)/2
        BAND_40M_30M_HZ = (BAND_40M_HZ + BAND_30M_HZ)/2
        BAND_30M_20M_HZ = (BAND_30M_HZ + BAND_20M_HZ)/2
        BAND_20M_17M_HZ = (BAND_20M_HZ + BAND_17M_HZ)/2
        BAND_17M_15M_HZ = (BAND_17M_HZ + BAND_15M_HZ)/2
        BAND_15M_12M_HZ = (BAND_15M_HZ + BAND_12M_HZ)/2
        BAND_12M_10M_HZ = (BAND_12M_HZ + BAND_10M_HZ)/2



        points = 500
        deviation_limit_puls = 1e-2 # kleiner = agressiver
        points_pulse = 101
        if set_f_swr_min_Hz > BAND_160M_80M_HZ:
            pass
        if set_f_swr_min_Hz > BAND_80M_60M_HZ:
            deviation_limit_puls = 0.3e-2 
        if set_f_swr_min_Hz > BAND_60M_40M_HZ:
            deviation_limit_puls = 0.5e-2 # 20260109 ok
        if set_f_swr_min_Hz > BAND_40M_30M_HZ:
            deviation_limit_puls = 0.8e-2 # 20260109 ok
        if set_f_swr_min_Hz > BAND_30M_20M_HZ:
            deviation_limit_puls = 2e-2 # 20260109 ok
        if set_f_swr_min_Hz > BAND_20M_17M_HZ:
            deviation_limit_puls = 4e-2 # 20260109 ok
        if set_f_swr_min_Hz > BAND_17M_15M_HZ:
            deviation_limit_puls = 3e-2 # 20260109 ok
        if set_f_swr_min_Hz > BAND_15M_12M_HZ:
            deviation_limit_puls = 1.5e-2 # 20260109 ok
        if set_f_swr_min_Hz > BAND_12M_10M_HZ:
            deviation_limit_puls = 1.2e-2 # 20260109 ok

        logger.debug(f"{f_swr_min_Hz=} {sweep_start_Hz=} {sweep_stop_Hz=}")

        # Motor control condition:
        # - f_swr_min_Hz must exist AND
        # - either deviation > 1 MHz OR both 2.64 markers exist (good SWR)
        should_stop = False
        if (f_swr_min_Hz is not None and
            (abs(f_swr_min_Hz - set_f_swr_min_Hz) > 1e6 or
             swr_min < 2.0)):
            if F_USEFUL_MIN_Hz < f_swr_min_Hz < F_USEFUL_MAX_Hz:
                difference_Hz = set_f_swr_min_Hz - f_swr_min_Hz
                direction_up = difference_Hz > 0
                deviation = abs(difference_Hz/set_f_swr_min_Hz)
                
                # Check if we're close enough to stop (smaller than pulse threshold)
                if deviation < deviation_limit_puls * 3:
                    # Small deviation: use pulse
                    pulse = True
                    duration_s = 1.0*deviation/deviation_limit_puls
                    cmd = f"pulse({direction_up}, {duration_s})"
                    dir_str = "up" if direction_up else "down"
                    dur_str = f"{duration_s:.2f}".rstrip("0").rstrip(".")
                    if getattr(self, "_tune_iteration", 0) == 0:
                        self._set_motor_status(f"pulse {dir_str} {dur_str}s (preview)")
                        print(f'pulse: {duration_s=} (preview)')
                    else:
                        self._set_motor_status(f"pulse {dir_str} {dur_str}s")
                        util_mpremote.mp_exec(device=self.mp_device, cmd=cmd)
                        points = points_pulse
                else:
                    # Large deviation: continuous run
                    cmd = f"run(direction_up={direction_up}, on=True)"
                    dir_str = "up" if direction_up else "down"
                    if getattr(self, "_tune_iteration", 0) == 0:
                        self._set_motor_status(f"motor run {dir_str} (preview)")
                    else:
                        self._set_motor_status(f"motor run {dir_str}")
                        util_mpremote.mp_exec(device=self.mp_device, cmd=cmd)
            else:
                should_stop = True
        else:
            should_stop = True
        
        # Always send explicit stop command when needed
        if should_stop:
            if getattr(self, "_tune_iteration", 0) > 0:
                util_mpremote.mp_exec(device=self.mp_device, cmd="run(direction_up=True, on=False)")
            if not hasattr(self, '_motor_status_already_set'):
                self._set_motor_status("stop")
        
        # Safety check: ensure points is defined
        if 'points' not in locals():
            points = 500
            logger.warning("points variable not set, using default: %d", points)
        
        try:
            self._setDatapointCount(points)
        except Exception:
            logger.exception("Failed to set datapoint count")