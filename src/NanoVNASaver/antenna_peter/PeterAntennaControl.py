import contextlib
import logging
import math
import pathlib
import socket
import time
import typing
from typing import TYPE_CHECKING, TypeVar

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from sts3215_ctl import util_mpremote
from sts3215_ctl.servo_ctl import Servo, ServoPortConfig
from sts3215_micropython.sts3215_portable import calculator

from ..Controls.Control import Control
from ..Controls.SweepControl import FrequencyInputWidget
from ..Hardware.VNA import VNA
from ..Marker.Widget import Marker
from ..RFTools import Datapoint
from . import peter_widgets, statemachine_tuner, util_persist

if TYPE_CHECKING:
    from ..NanoVNASaver import NanoVNASaver

logger = logging.getLogger(__name__)

QWidgetT = TypeVar("QWidgetT", bound=QtWidgets.QWidget)


# Frequency limits for magnetic loop antenna
F_USEFUL_MIN_Hz = 1.0e6
F_USEFUL_MAX_Hz = 30.0e6

DIRECTORY_OF_THIS_FILE = pathlib.Path(__file__).parent
DIRECTORY_MICROPYTHON = DIRECTORY_OF_THIS_FILE / "micropython"
assert DIRECTORY_MICROPYTHON.is_dir()
DIRECTORY_LOGS = DIRECTORY_OF_THIS_FILE / "tmp_sts3215_servo_f_logs"
DIRECTORY_LOGS.mkdir(exist_ok=True)

ENABLE_STS3215 = True
ENABLE_STS3215_SERVO_F = False


class Servos:
    def __init__(self, port_config: ServoPortConfig) -> None:
        if ENABLE_STS3215_SERVO_F:
            self.servo_ctl_f = Servo(
                port_config=port_config,
                scs_id=2,
                torque_limit=300,
                goal_speed=1000,
                acceleration=300,
                position_p_gain=10,
                position_i_gain=2,
                filename_persist=DIRECTORY_OF_THIS_FILE
                / "tmp_sts3215_servo_f.json",
            )
        self.servo_ctl_z = Servo(
            port_config=port_config,
            scs_id=3,
            torque_limit=100,
            goal_speed=1000,
            acceleration=1,
            position_p_gain=10,
            position_i_gain=2,
        )
        self.servo_ctl_h = Servo(
            port_config=port_config,
            scs_id=4,
            torque_limit=150,
            goal_speed=100,
            acceleration=1,
            position_p_gain=10,
            position_i_gain=2,
        )


def calculate_safety_distance(
    f_mhz, p_watt, q_factor, loop_diameter_m=1.0, loop_area_m2=0.78
):
    """Calculates the minimum safety distance for a Magnetic Loop antenna based on H-field limits."""
    f_hz = f_mhz * 1e6
    radius = loop_diameter_m / 2
    area = math.pi * (radius**2)
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

    r_meters_igw = ((i_loop * area) / (2 * math.pi * h_limit_igw)) ** (1 / 3)
    r_meters_omen = ((i_loop * area) / (2 * math.pi * h_limit_omen)) ** (1 / 3)

    # Calculate radiation resistance and efficiency for small loop antenna
    # R_rad = 31171 × (A/λ²)² Ω  (for circular loop)
    # R_loss = 2πfL / Q
    # η = R_rad / (R_rad + R_loss)
    # P_radiated = P_input × η
    c = 299792458  # speed of light m/s
    wavelength = c / f_hz

    # Radiation resistance (small loop formula)
    r_rad = 31171 * ((loop_area_m2 / (wavelength**2)) ** 2)

    # Loss resistance from Q factor
    omega_l = 2 * math.pi * f_hz * l_henry
    r_loss = omega_l / q_factor

    # Efficiency and radiated power
    efficiency = (r_rad / (r_rad + r_loss)) * 100.0
    p_radiated = p_watt * (r_rad / (r_rad + r_loss))

    return {
        "frequency_mhz": f_mhz,
        "power_watts": p_watt,
        "q_factor": q_factor,
        "loop_current_amps": round(i_loop, 2),
        "cap_voltage_volts": round(v_cap, 0),
        "h_limit_igw_am": round(h_limit_igw, 4),
        "h_limit_omen_am": round(h_limit_omen, 4),
        "min_distance_igw_m": round(r_meters_igw, 2),
        "min_distance_omen_m": round(r_meters_omen, 2),
        "p_radiated_watts": round(p_radiated, 2),
        "efficiency_percent": round(efficiency, 1),
    }


class PeterAntennaControl(Control):
    def add_row(self, widget: QWidgetT) -> QWidgetT:
        self._layout.addWidget(widget)
        return widget

    def add_row_old(
        self, left: QtWidgets.QWidget, right: QtWidgets.QWidget | None = None
    ) -> QtWidgets.QWidget:
        widget = peter_widgets.FormLayoutWidget(left=left, right=right)
        self._layout.addWidget(widget)
        return widget

    def __init__(self, app: "NanoVNASaver"):
        super().__init__(app, "Peter Antenna control")

        with self._servo_position_persist() as p:
            servo_position_persist = p

        self.statemachine_tuner = statemachine_tuner.StatemachineTuner()
        self.statemachine_tuner_timer = QtCore.QTimer(self)

        self.mp_device = util_mpremote.get_device()
        self.port_config = ServoPortConfig(
            device=self.mp_device,
            directory_logs=DIRECTORY_LOGS,
        )
        # This will copy the files and reset the rasperry pi pico
        self.port_config.init()
        # This will power the servos
        for file_py in ("initialization_BMM350.py", "initialization.py"):
            filename = DIRECTORY_MICROPYTHON / file_py
            python_code = filename.read_text()
            self._mp_exec(
                label_full=f"pico_initilization_{filename.stem}",
                cmd=python_code,
            )
        # time.sleep(1.0)
        self.servos: Servos | None = None

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.VLine)

        self._layout = QtWidgets.QVBoxLayout(self)

        self.checkbox_tune = self.add_row(
            peter_widgets.CheckboxWidget("Tune automatic")
        ).checkbox
        self.checkbox_vna_enable = self.add_row(
            peter_widgets.CheckboxWidget("VNA enable, TX inhibit")
        ).checkbox

        self.tx_inhibit_switch_display = self.add_row(
            peter_widgets.ValueWidget(
                label="TX inhibited by switch", value="--"
            )
        ).value

        if True:
            # OBSOLETE
            self.checkbox_up = QtWidgets.QCheckBox()
            self.checkbox_down = QtWidgets.QCheckBox()

            # Tune iteration counter (internal; display removed)
            # self._tune_iteration_obsolete = 0
            # Store calculated Q factor for safety calculations
            self._q_factor = 500.0  # default value

            # Manual F controls in one row
            manual_f_layout = QtWidgets.QHBoxLayout()
            manual_f_layout.addWidget(self.checkbox_up)
            manual_f_layout.addWidget(QtWidgets.QLabel("up"))
            manual_f_layout.addWidget(self.checkbox_down)
            manual_f_layout.addWidget(QtWidgets.QLabel("down"))
            manual_f_layout.addStretch()
            self.add_row_old(QtWidgets.QLabel("Manual F"), manual_f_layout)

            # motor status display (under the 'down' checkbox)
            self.motor_status = QtWidgets.QLabel("stop")
            # align the motor status to the right (consistent with other numeric fields)
            self.motor_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            font = self.motor_status.font()
            font.setPointSize(11)
            self.motor_status.setFont(font)
            self.add_row_old(
                QtWidgets.QLabel("Motor status"), self.motor_status
            )
            # The 'Set Values' input was intentionally disabled/commented out.
            # self.button_set_values = QtWidgets.QPushButton("Set & Sweep")
            # self.add_row_old(
            #     QtWidgets.QLabel("Set Values"), self.button_set_values
            # )

        #### NEW
        self.add_row(peter_widgets.SeparatorWidget())

        # Tune heading checkbox
        self.heading_checkbox = self.add_row(
            peter_widgets.CheckboxWidget("Tune heading checkbox")
        ).checkbox
        self.heading_checkbox.setChecked(True)
        # Tune heading target textfeld, button set
        self.heading_target = self.add_row(
            peter_widgets.PushButtonWidget(
                label="Tune heading target", f_value=0.0, unit="deg"
            )
        )
        # Tune heading current textfeld
        self.heading_current = self.add_row(
            peter_widgets.ValueWidget(label="Tune heading current", value="0")
        )
        # Tune heading servo_h textfeld, button set
        self.heading_servo = self.add_row(
            peter_widgets.PushButtonWidget(
                label="Tune heading servo_h",
                f_value=servo_position_persist.servo_h_ta,
                unit="turns",
                cb_set=self._heading_set_servo_h,
            )
        )

        self.add_row(peter_widgets.SeparatorWidget())

        self.checkbox_auto_get_f = self.add_row(
            peter_widgets.CheckboxWidget("Auto get frequency (OBSOLETE)")
        ).checkbox

        if True:
            # MOVE
            self.auto_get_timer = QtCore.QTimer(self)
            self.auto_get_timer.setInterval(2000)  # 2 seconds
            self.auto_get_timer.timeout.connect(self._auto_get_frequency)

            # self.tx_inhibit_timer = QtCore.QTimer(self)
            # self.tx_inhibit_timer.setInterval(1000)
            # self.tx_inhibit_timer.timeout.connect(
            #     self._update_tx_inhibit_switch
            # )

            self.checkbox_auto_get_f.checkStateChanged.connect(
                self.on_auto_get_frequency_toggle
            )
            # Enable auto-get by default at initialization
            self.checkbox_auto_get_f.setChecked(True)

        self.input_swr_offset_Hz = self.add_row(
            peter_widgets.DoubleSpinBoxWidget(
                label="Set offset (OBSOLETE)", value=1500, unit="Hz"
            )
        ).entry

        self.input_set_Hz = self.add_row(
            peter_widgets.DoubleSpinBoxWidget(
                label="Set swr min(OBSOLETE)", value=7.074e6, unit="Hz"
            )
        ).entry

        # Frequency enable checkbox
        self.frequency_checkbox = self.add_row(
            peter_widgets.CheckboxWidget("Tune Frequency enable")
        ).checkbox
        # Frequency Offset textfeld mit button set
        self.frequency_offset = self.add_row(
            peter_widgets.PushButtonWidget(
                label="Frequency Offset (DOPPELT)", f_value=0.0, unit="Hz"
            )
        )
        # Frequency auto get from TX checkbox
        self.frequency_auto_get = self.add_row(
            peter_widgets.CheckboxWidget("Frequency auto get from TX (DOPPELT)")
        ).checkbox
        # Frequency TX textfeld mit button set
        self.frequency_tx = self.add_row(
            peter_widgets.PushButtonWidget(
                label="Frequency TX", f_value=0.0, unit="Hz"
            )
        )
        # Frequency target textfeld
        self.frequency_target = self.add_row(
            peter_widgets.ValueWidget(label="Frequency target", value="0")
        )
        # Frequency current textfeld
        self.frequency_target = self.add_row(
            peter_widgets.ValueWidget(label="Frequency current", value="0")
        )

        # Frequency servo_f textfeld button set
        self.frequency_servo_f = self.add_row(
            peter_widgets.PushButtonWidget(
                label="Frequency servo_f",
                f_value=self._frequency_get_servo_f(),
                unit="turns",
                cb_set=self._frequency_set_servo_f,
            )
        )

        self.add_row(peter_widgets.SeparatorWidget())
        # Impedance enable checkbox
        self.impedance_checkbox = self.add_row(
            peter_widgets.CheckboxWidget("Tune Impedance enable")
        ).checkbox
        # Impedance target textfeld mit button set
        self.impedance_target = self.add_row(
            peter_widgets.PushButtonWidget(
                label="Impedance target", f_value=0.0, unit="Ohm"
            )
        )
        # Impedance current textfeld
        self.impedance_current = self.add_row(
            peter_widgets.ValueWidget(label="Impedance current", value="0")
        )
        # Impedance servo_z textfeld button set
        self.impedance_servo_z = self.add_row(
            peter_widgets.PushButtonWidget(
                label="Impedance servo_z",
                f_value=servo_position_persist.servo_z_ta,
                unit="turns",
                cb_set=self._impedance_set_servo_z,
            )
        )

        self.add_row(peter_widgets.SeparatorWidget())
        #### NEW

        self.delta_display = self.add_row(
            peter_widgets.ValueWidget(label="Δ kHz (SWR min)", value="--")
        ).value

        self.q_display = self.add_row(
            peter_widgets.ValueWidget(label="Q (SWR 2.64)", value="--")
        ).value
        self.swrmin_display = self.add_row(
            peter_widgets.ValueWidget(label="SWR min", value="--")
        ).value
        self.impedance_display = self.add_row(
            peter_widgets.ValueWidget(label="R @ SWR min", value="--")
        ).value
        self.efficiency_display = self.add_row(
            peter_widgets.ValueWidget(label="Efficiency η", value="--")
        ).value

        self.power_spin = self.add_row(
            peter_widgets.PowerspinWidget(
                label="Power 5...100",
                value=5,
                min_value=5,
                max_value=100,
                unit="W",
            )
        ).power_spin

        # Radiated power display (calculated from loop area, current, frequency)
        self.radiated_power_display = self.add_row(
            peter_widgets.ValueWidget(label="P radiated", value="--")
        ).value

        self.add_row(peter_widgets.SeparatorWidget())

        # Safety calculation fields (read-only display)
        self.cap_voltage_display = self.add_row(
            peter_widgets.ValueWidget(label="Cap Voltage", value="--")
        ).value

        self.loop_current_display = self.add_row(
            peter_widgets.ValueWidget(label="Loop Current", value="--")
        ).value

        self.h_limit_display = self.add_row(
            peter_widgets.ValueWidget(label="H_Limit (NISV/IGW)", value="--")
        ).value

        self.h_limit_omen_display = self.add_row(
            peter_widgets.ValueWidget(label="H_Limit (OMEN)", value="--")
        ).value

        self.safety_distance_display = self.add_row(
            peter_widgets.ValueWidget(label="Safety distance IGW", value="--")
        ).value

        self.safety_distance_omen_display = self.add_row(
            peter_widgets.ValueWidget(
                label="Safety distance <a href='https://github.com/petermaerki/fork_nanovna-saver/blob/antenna_tuner/src/NanoVNASaver/antenna_peter/SAFETY_INFO.md'>OMEN</a>",
                value="--",
            )
        ).value

        self.add_row(peter_widgets.SeparatorWidget())

        # (power status label removed — FT-991 cannot be queried for power)
        # connect power control immediately so changes always send to rigctld
        try:
            self.power_spin.valueChanged.connect(self.on_power_changed)
        except Exception:
            logger.exception("Failed to connect power spin signal at init")

        # Connect frequency input field to update safety calculations
        try:
            self.input_set_Hz.textChanged.connect(
                self._update_safety_calculation
            )
        except Exception:
            logger.exception("Failed to connect frequency input signal at init")

        # Perform initial safety calculation
        try:
            self._update_safety_calculation()
        except Exception:
            logger.exception("Failed to perform initial safety calculation")

        self.layout.addRow(self._layout)

        # 'Set Values' signal connection commented out because the input is disabled
        # self.button_set_values.pressed.connect(self.on_button_set_values)
        self.checkbox_tune.checkStateChanged.connect(self.on_tune)
        self.checkbox_up.checkStateChanged.connect(self.on_up)
        self.checkbox_down.checkStateChanged.connect(self.on_down)
        self.checkbox_vna_enable.checkStateChanged.connect(self.on_vna_enable)
        self._default_app_palette = QtGui.QPalette(self.app.palette())
        # self._app_bg_inhibit_active = False
        # self._update_tx_inhibit_switch()
        # self.tx_inhibit_timer.start()
        self._enable_widgets(
            state_vna_enabled=self.checkbox_vna_enable.isChecked()
        )
        self.statemachine_tuner_timer.setInterval(1000)  # 1 seconds

        def tune():
            self.statemachine_tuner.tune(self)

        self.statemachine_tuner_timer.timeout.connect(tune)
        self.statemachine_tuner_timer.start()

    def on_tune(self, checked: QtCore.Qt.CheckState) -> None:
        """
        Statemachine "Tuning".
        This is the entry action.
        """
        assert isinstance(checked, QtCore.Qt.CheckState)
        state_tuning = checked.value  #  self.checkbox_tune.isChecked()
        self.checkbox_vna_enable.setChecked(state_tuning)
        if state_tuning:
            # Auto-enable VNA if not already enabled
            # if not self.checkbox_vna_enable.isChecked():
            #     logger.debug("Tune enabled: auto-enabling VNA")
            #     self.checkbox_vna_enable.setChecked(True)

            # reset tune iteration counter on initial enable; first sweep is a dry-run
            # self._tune_iteration_obsolete = 0
            # Send current power setting to FT-991 when tuning is enabled
            # try:
            #     self.on_power_changed()
            # except Exception:
            #     logger.exception("Failed to send initial power on tune enable")
            # self.on_button_set_values()
            if False:
                sweep_stop = self.app.sweep_control.inputs["Stop"]
                assert isinstance(sweep_stop, FrequencyInputWidget)
                if sweep_stop.get_freq() > F_USEFUL_MAX_Hz:
                    sweep_stop.setText(f"{F_USEFUL_MAX_Hz:0.0f}Hz")
                    sweep_start = self.app.sweep_control.inputs["Start"]
                    assert isinstance(sweep_start, FrequencyInputWidget)
                    sweep_start.setText(f"{F_USEFUL_MIN_Hz:0.0f}Hz")

            # self._setStartStopFrequencyFloat("Start", 1e6)
            # self._setStartStopFrequencyFloat("Stop", 30e6)
            # self._setDatapointCount(1000)  # initial bei overview
            # self.app.sweep.set_logarithmic(True)

            # self.app.sweep_start()
        else:
            # self._pico_run(direction_up=True, on=False)
            # When tune is disabled, also disable VNA enable
            # if self.checkbox_vna_enable.isChecked():
            #     logger.debug("Tune disabled: auto-disabling VNA")
            #     self.checkbox_vna_enable.setChecked(False)
            # self._set_motor_status_obsolete("stop")
            # clear internal tune iteration counter when tuning disabled
            # self._tune_iteration_obsolete = 0
            def run_vna_on_frequency_which_does_not_harm():
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
                    logger.debug(
                        "Tune disabled: started harmless sweep 100kHz-200kHz (display suppressed)"
                    )
                except Exception:
                    logger.exception(
                        "Failed to set harmless sweep on tune disable"
                    )

            run_vna_on_frequency_which_does_not_harm()

            # sweep_start.setText(f"100kHz") # todo: disable sweep completely
            # sweep_stop.setText(f"200kHz")
            # self.app.sweep_start()

    def on_vna_enable(self, checked: QtCore.Qt.CheckState) -> None:
        """
        Statemachine "VNA Enable".
        This is the entry action.
        """
        assert isinstance(checked, QtCore.Qt.CheckState)
        try:
            state_vna_enabled = (
                checked.value
            )  # self.checkbox_vna_enable.isChecked()
            # The following code will ALSO power the servos
            self._mp_exec(
                label_full="pico_vna_enable",
                cmd=f"vna_enable(enable={int(state_vna_enabled)})",
            )
            if state_vna_enabled:
                if ENABLE_STS3215:
                    self.servos = Servos(port_config=self.port_config)
            else:
                self.servos = None

            self._enable_widgets(state_vna_enabled=state_vna_enabled)
            # If the user enabled VNA, also try to connect the serial port control
            # (do nothing if already connected)
            # if checked:
            #     try:
            #         if not self.app.serial_control.is_vna_connected():
            #             self.app.serial_control.connect_device()
            #     except Exception:
            #         logger.exception(
            #             "Failed to auto-connect serial port on VNA enable"
            #         )
            # else:
            #     # When VNA is disabled, also uncheck tune automatic
            #     self.checkbox_tune.setChecked(False)

            # Note: power spin is connected at init; no further action needed here
        except Exception:
            logger.exception("on_vna_enable")

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
            logger.debug(
                "Setting RF power: %s W -> %s (socket)", watts, scaled_str
            )
            # Send command over the same localhost:4532 socket used by _auto_get_frequency
            try:
                with socket.create_connection(
                    ("localhost", 4532), timeout=1
                ) as s:
                    # send rigctl-style command over socket; server accepts newline-terminated commands
                    cmd = f"L RFPOWER {scaled_str}\n"
                    s.sendall(cmd.encode("ascii"))
                    # try to read a short response to know if server accepted the command
                    try:
                        s.settimeout(0.5)
                        resp = s.recv(1024).strip()
                        if resp:
                            try:
                                resp_text = resp.decode(
                                    "utf-8", errors="replace"
                                )
                            except Exception:
                                resp_text = repr(resp)
                            logger.warning("RFPOWER response: %s", resp_text)
                        else:
                            logger.warning("RFPOWER: no response from server")
                    except socket.timeout:
                        logger.warning("RFPOWER: no response (timeout)")
                    except Exception as e:
                        logger.warning(
                            "RFPOWER: reading response failed: %s", e
                        )
            except Exception as e:
                logger.warning("Failed to send RFPOWER over socket: %s", e)
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
            self.cap_voltage_display.setText(
                f"{results['cap_voltage_volts']:.0f} V"
            )

            # Loop Current
            self.loop_current_display.setText(
                f"{results['loop_current_amps']} A"
            )

            # H-Limit IGW
            self.h_limit_display.setText(f"{results['h_limit_igw_am']:.3f} A/m")

            # H-Limit OMEN
            self.h_limit_omen_display.setText(
                f"{results['h_limit_omen_am']:.3f} A/m"
            )

            # Safety Distance IGW
            self.safety_distance_display.setText(
                f"{results['min_distance_igw_m']} m"
            )

            # Safety Distance OMEN
            self.safety_distance_omen_display.setText(
                f"{results['min_distance_omen_m']} m"
            )

            # Radiated Power
            self.radiated_power_display.setText(
                f"{results['p_radiated_watts']:.2f} W"
            )

            # Efficiency
            self.efficiency_display.setText(
                f"{results['efficiency_percent']:.1f} %"
            )

            logger.debug(
                "Safety calc: f=%s MHz, P=%s W, Q=%s, I=%s A, H_IGW=%s A/m, dist_IGW=%s m, H_OMEN=%s A/m, dist_OMEN=%s m",
                f_mhz,
                watts,
                q_factor,
                results["loop_current_amps"],
                results["h_limit_igw_am"],
                results["min_distance_igw_m"],
                results["h_limit_omen_am"],
                results["min_distance_omen_m"],
            )
        except Exception:
            logger.exception("Failed to update safety calculation")
            self.cap_voltage_display.setText("--")
            self.loop_current_display.setText("--")
            self.h_limit_display.setText("--")
            self.h_limit_omen_display.setText("--")
            self.safety_distance_display.setText("--")
            self.safety_distance_omen_display.setText("--")
            self.radiated_power_display.setText("--")
            self.efficiency_display.setText("--")

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
                if hasattr(self, "input_set_Hz"):
                    self.input_set_Hz.setValue(freq_hz_with_offset)
                logger.debug(
                    "Auto-get frequency: set %d Hz (received %d Hz + offset %d Hz)",
                    freq_hz_with_offset,
                    freq_hz,
                    offset_hz,
                )
        except Exception as e:
            logger.warning("Auto-get frequency failed: %s", e)

    # def _update_tx_inhibit_switch_obsolete(self):
    #     try:
    #         stdout = self._mp_exec(
    #             label_full="pico_get_tx_inhibit_switch",
    #             cmd="get_tx_inhibit_switch()",
    #         )
    #         tx_inhibit_switch = calculator.parse_value_int(
    #             stdout=stdout,
    #             label="tx_inhibit_switch",
    #         )

    #         self.tx_inhibit_switch_display.setText(
    #             "YES" if tx_inhibit_switch == 1 else "NO"
    #         )
    #         self._set_app_background(inhibited=(tx_inhibit_switch == 1))
    #     except Exception as e:
    #         logger.debug("TX inhibit switch read failed: %s", e)
    #         self.tx_inhibit_switch_display.setText("--")
    #         self._set_app_background(inhibited=False)
    #         raise

    # def _set_app_background(self, inhibited: bool) -> None:
    #     if inhibited == self._app_bg_inhibit_active:
    #         return
    #     if inhibited:
    #         palette = QtGui.QPalette(self._default_app_palette)
    #         palette.setColor(
    #             QtGui.QPalette.ColorRole.Window, QtGui.QColor("#CCFFCC")
    #         )
    #         self.app.setAutoFillBackground(True)
    #         self.app.setPalette(palette)
    #         self._app_bg_inhibit_active = True
    #     else:
    #         self.app.setPalette(self._default_app_palette)
    #         self._app_bg_inhibit_active = False

    def on_up(self):
        checked = self.checkbox_up.isChecked()
        if checked:
            self._pico_run(direction_up=True, on=True)
            self._set_motor_status_obsolete("motor run f up")
        else:
            self._pico_run(direction_up=True, on=False)
            self._set_motor_status_obsolete("stop")

    def on_down(self):
        checked = self.checkbox_down.isChecked()
        if checked:
            self._pico_run(direction_up=False, on=True)
            self._set_motor_status_obsolete("motor run f down")
        else:
            self._pico_run(direction_up=False, on=False)
            self._set_motor_status_obsolete("stop")

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
        # self._setStartStartFrequency("Start", "2MHz")
        # self._setStartStopFrequency("Stop", "28MHz")
        # self._setMakerFrequency(0, "1MHz")
        # self._setMakerFrequency(-1, "30MHz")
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
            if (
                f_swr_p2_64_l_Hz is None
                and f_swr_min_Hz is None
                and f_swr_p2_64_h_Hz is None
            ):
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
                logger.exception(
                    "Failed to update delta display after sweep finish"
                )
            try:
                self._update_q_display()
            except Exception:
                logger.exception(
                    "Failed to update Q display after sweep finish"
                )
            try:
                self._update_swrmin_display()
            except Exception:
                logger.exception(
                    "Failed to update SWR min display after sweep finish"
                )
            try:
                self._update_impedance_display()
            except Exception:
                logger.exception(
                    "Failed to update impedance display after sweep finish"
                )
            # Update safety calculation when Q is recalculated
            try:
                self._update_safety_calculation()
            except Exception:
                logger.exception(
                    "Failed to update safety calculation after sweep finish"
                )
            # increment tune iteration counter if tuning is still enabled
            try:
                if self.checkbox_tune.isChecked():
                    self._tune_iteration_obsolete += 1
            except Exception:
                logger.exception("Failed to increment tune iteration counter")
        except Exception:
            logger.exception("Critical error in sweepFinished_peter_antenna")
            # Ensure motor is stopped on any error
            try:
                self._pico_run(direction_up=True, on=False)
                self._set_motor_status_obsolete("stop (error)")
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
            return None, None, None, float("inf")

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
                            (freqs[i + 2] - freqs[i + 1])
                            + (freqs[i + 1] - freqs[i])
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
                                    max_val,
                                    mean_val,
                                    f_swr_min_Hz,
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

    def _update_impedance_display(self):
        """Compute and display the antenna impedance from the Smith chart circle.

        The three marker points form a circle in the Smith chart.
        Check if the center of the Smith chart (50 Ω, Gamma=0) is inside the circle:
        - If inside: overcoupled → R = 50 Ω × SWR_min
        - If outside: undercoupled → R = 50 Ω / SWR_min
        """
        try:
            markers = self.app.markers
            if len(markers) < 3:
                self.impedance_display.setText("--")
                return

            # Get all three marker frequencies
            f1 = markers[0].frequencyInput.get_freq()  # SWR 2.64 low
            f2 = markers[1].frequencyInput.get_freq()  # SWR min
            f3 = markers[2].frequencyInput.get_freq()  # SWR 2.64 high

            if f1 is None or f2 is None or f3 is None:
                self.impedance_display.setText("--")
                return

            # Get S11 data
            with self.app.dataLock:
                s11: list[Datapoint] = self.app.data.s11[:]
                if not s11:
                    self.impedance_display.setText("--")
                    return
                # Also get SWR at marker 2 (SWR min)
                swr_array = np.asarray([d.vswr for d in s11])

            swr_min = float(np.min(swr_array))

            # Find closest datapoints for all three markers
            def find_closest(freq_target):
                min_diff = float("inf")
                closest = None
                for dp in s11:
                    diff = abs(dp.freq - freq_target)
                    if diff < min_diff:
                        min_diff = diff
                        closest = dp
                return closest

            dp1 = find_closest(f1)
            dp2 = find_closest(f2)
            dp3 = find_closest(f3)

            if dp1 is None or dp2 is None or dp3 is None:
                self.impedance_display.setText("--")
                return

            # Get S11 (Gamma) for all three points
            g1 = complex(dp1.re, dp1.im)
            g2 = complex(dp2.re, dp2.im)
            g3 = complex(dp3.re, dp3.im)

            # Calculate circle center using perpendicular bisectors
            mid12 = (g1 + g2) / 2
            mid23 = (g2 + g3) / 2

            d12 = g2 - g1
            d23 = g3 - g2

            # Perpendicular vectors (rotate by 90°)
            perp12 = complex(-d12.imag, d12.real)
            perp23 = complex(-d23.imag, d23.real)

            diff = mid23 - mid12
            det = perp12.real * perp23.imag - perp12.imag * perp23.real

            if abs(det) < 1e-10:
                # Points are collinear
                self.impedance_display.setText("--")
                return

            t = (diff.real * perp23.imag - diff.imag * perp23.real) / det
            circle_center = mid12 + t * perp12

            # Calculate radius
            radius = abs(g1 - circle_center)

            # Check if Smith chart center (Gamma=0, representing 50 Ω) is inside circle
            distance_to_center = abs(circle_center)  # distance from Gamma=0

            if distance_to_center < radius:
                # Center is inside circle → overcoupled
                r_antenna = 50.0 * swr_min
            else:
                # Center is outside circle → undercoupled
                r_antenna = 50.0 / swr_min

            self.impedance_display.setText(f"{r_antenna:.0f} Ω")

        except Exception:
            logger.exception("Failed to update impedance display")
            self.impedance_display.setText("--")

    def _set_motor_status_obsolete(self, status: str):
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
        if (
            f_swr_min_Hz is None
            and f_swr_p2_64_l_Hz is None
            and f_swr_p2_64_h_Hz is None
        ):
            logger.warning(
                "find_sweep_start_stop: No valid frequency data, using full range"
            )
            self._setStartStopFrequencyFloat("Start", F_USEFUL_MIN_Hz)
            self._setStartStopFrequencyFloat("Stop", F_USEFUL_MAX_Hz)
            self._setDatapointCount(500)
            self._set_motor_status_obsolete("stop (no data)")
            return

        try:
            set_f_swr_min_Hz = float(self.input_set_Hz.text())
        except (ValueError, AttributeError) as e:
            logger.warning(
                "find_sweep_start_stop: Invalid set frequency: %s", e
            )
            set_f_swr_min_Hz = 7.074e6  # default fallback

        # Check if we have at least SWR min frequency
        if f_swr_min_Hz is not None:
            # Check if 2.64 markers are missing or too far from SWR min (>500 kHz)
            use_fixed_zoom = False
            if f_swr_p2_64_l_Hz is None or f_swr_p2_64_h_Hz is None:
                use_fixed_zoom = True
                logger.debug("2.64 markers missing, using ±1 MHz zoom")
            elif (
                abs(f_swr_p2_64_l_Hz - f_swr_min_Hz) > 500e3
                or abs(f_swr_p2_64_h_Hz - f_swr_min_Hz) > 500e3
            ):
                use_fixed_zoom = True
                logger.debug(
                    "2.64 markers >500 kHz from SWR min, using ±1 MHz zoom"
                )

            if use_fixed_zoom:
                # Use fixed ±1 MHz zoom around set frequency
                distance_f = 1e6
            else:
                # Use 2.64 markers for zoom calculation
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

            logger.debug(
                "Zoom calc: f_swr_min=%s Hz, set_f=%s Hz, distance_f=%s Hz, "
                "sweep: %s - %s Hz",
                f_swr_min_Hz,
                set_f_swr_min_Hz,
                distance_f,
                sweep_start_Hz,
                sweep_stop_Hz,
            )
        else:
            # No SWR min found at all, use full range
            logger.debug("No SWR min found, using full range")
            sweep_start_Hz = F_USEFUL_MIN_Hz
            sweep_stop_Hz = F_USEFUL_MAX_Hz

        self._setStartStopFrequencyFloat("Start", sweep_start_Hz)
        self._setStartStopFrequencyFloat("Stop", sweep_stop_Hz)
        # sweep_range_relative = (sweep_stop_Hz - sweep_start_Hz)/set_f_swr_min_Hz
        # points = int(5 * sweep_range_relative / 0.01)
        # points = min(points, 600)
        # points = max(points, 51)

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

        BAND_160M_80M_HZ = (BAND_160M_HZ + BAND_80M_HZ) / 2
        BAND_80M_60M_HZ = (BAND_80M_HZ + BAND_60M_HZ) / 2
        BAND_60M_40M_HZ = (BAND_60M_HZ + BAND_40M_HZ) / 2
        BAND_40M_30M_HZ = (BAND_40M_HZ + BAND_30M_HZ) / 2
        BAND_30M_20M_HZ = (BAND_30M_HZ + BAND_20M_HZ) / 2
        BAND_20M_17M_HZ = (BAND_20M_HZ + BAND_17M_HZ) / 2
        BAND_17M_15M_HZ = (BAND_17M_HZ + BAND_15M_HZ) / 2
        BAND_15M_12M_HZ = (BAND_15M_HZ + BAND_12M_HZ) / 2
        BAND_12M_10M_HZ = (BAND_12M_HZ + BAND_10M_HZ) / 2

        points = 500
        deviation_limit_puls = 1e-2  # kleiner = agressiver
        points_pulse = 101
        if set_f_swr_min_Hz > BAND_160M_80M_HZ:
            deviation_limit_puls = 0.2e-2
        if set_f_swr_min_Hz > BAND_80M_60M_HZ:
            deviation_limit_puls = 0.3e-2
        if set_f_swr_min_Hz > BAND_60M_40M_HZ:
            deviation_limit_puls = 0.5e-2  # 20260109 ok
        if set_f_swr_min_Hz > BAND_40M_30M_HZ:
            deviation_limit_puls = 0.8e-2  # 20260109 ok
        if set_f_swr_min_Hz > BAND_30M_20M_HZ:
            deviation_limit_puls = 2e-2  # 20260109 ok
        if set_f_swr_min_Hz > BAND_20M_17M_HZ:
            deviation_limit_puls = 4e-2  # 20260109 ok
        if set_f_swr_min_Hz > BAND_17M_15M_HZ:
            deviation_limit_puls = 3e-2  # 20260109 ok
        if set_f_swr_min_Hz > BAND_15M_12M_HZ:
            deviation_limit_puls = 1.5e-2  # 20260109 ok
        if set_f_swr_min_Hz > BAND_12M_10M_HZ:
            deviation_limit_puls = 1.2e-2  # 20260109 ok

        logger.debug(f"{f_swr_min_Hz=} {sweep_start_Hz=} {sweep_stop_Hz=}")

        # Motor control condition:
        # - f_swr_min_Hz must exist AND
        # - either deviation > 1 MHz OR both 2.64 markers exist (good SWR)
        should_stop = False
        if f_swr_min_Hz is not None and (
            abs(f_swr_min_Hz - set_f_swr_min_Hz) > 1e6 or swr_min < 2.0
        ):
            if F_USEFUL_MIN_Hz < f_swr_min_Hz < F_USEFUL_MAX_Hz:
                difference_Hz = set_f_swr_min_Hz - f_swr_min_Hz
                direction_up = difference_Hz > 0
                deviation = abs(difference_Hz / set_f_swr_min_Hz)

                # Check if we're close enough to stop (smaller than pulse threshold)
                if deviation < deviation_limit_puls * 3:
                    # Small deviation: use pulse
                    pulse = True
                    duration_s = 1.0 * deviation / deviation_limit_puls
                    cmd = f"pulse({direction_up}, {duration_s})"
                    dir_str = "up" if direction_up else "down"
                    dur_str = f"{duration_s:.2f}".rstrip("0").rstrip(".")
                    if getattr(self, "_tune_iteration", 0) == 0:
                        self._set_motor_status_obsolete(
                            f"pulse {dir_str} {dur_str}s (preview)"
                        )
                        print(f"pulse: {duration_s=} (preview)")
                    else:
                        self._set_motor_status_obsolete(
                            f"pulse {dir_str} {dur_str}s"
                        )
                        self._mp_exec(label_full="pico_pulse", cmd=cmd)
                        points = points_pulse
                else:
                    # Large deviation: continuous run
                    dir_str = "up" if direction_up else "down"
                    if getattr(self, "_tune_iteration", 0) == 0:
                        self._set_motor_status_obsolete(
                            f"motor run {dir_str} (preview)"
                        )
                    else:
                        self._set_motor_status_obsolete(f"motor run {dir_str}")
                        self._pico_run(direction_up=direction_up, on=True)
            else:
                should_stop = True
        else:
            should_stop = True

        # Always send explicit stop command when needed
        if should_stop:
            if getattr(self, "_tune_iteration", 0) > 0:
                self._pico_run(direction_up=True, on=False)
            if not hasattr(self, "_motor_status_already_set"):
                self._set_motor_status_obsolete("stop")

        # Safety check: ensure points is defined
        if "points" not in locals():
            points = 500
            logger.warning("points variable not set, using default: %d", points)

        try:
            self._setDatapointCount(points)
        except Exception:
            logger.exception("Failed to set datapoint count")

    def _frequency_set_servo_f(self, target_ta: float) -> float:
        if self.servos is None:
            return target_ta
        if ENABLE_STS3215_SERVO_F:
            return target_ta
        require_homeing = False
        try:
            _target_ta = min(
                statemachine_tuner.FREQUENCY_TARGET_TA_MAX,
                max(statemachine_tuner.FREQUENCY_TARGET_TA_MIN, target_ta),
            )
            self.servos.servo_ctl_f.move_ta(target_ta=_target_ta)
        except calculator.ExceptionRequireHoming as e:
            logger.warning(e)
            require_homeing = True
        if require_homeing:
            self.servos.servo_ctl_f.homing()
            self.servos.servo_ctl_f.move_ta(target_ta=_target_ta)

        return _target_ta

    def _heading_set_servo_h(self, target_ta: float) -> float:
        if self.servos is None:
            return target_ta
        _target_ta = min(
            statemachine_tuner.HEADING_TARGET_TA_MAX,
            max(statemachine_tuner.HEADING_TARGET_TA_MIN, target_ta),
        )
        ewp = int(-_target_ta * 4096) + 2048
        self.servos.servo_ctl_h.move_ewp(ewp=ewp)

        with self._servo_position_persist() as p:
            p.servo_h_ta = _target_ta

        return _target_ta

    def _impedance_set_servo_z(self, target_ta: float) -> float:
        if self.servos is None:
            return target_ta
        _target_ta = min(
            statemachine_tuner.IMPEDANCE_TARGET_TA_MAX,
            max(statemachine_tuner.IMPEDANCE_ARGET_TA_MIN, target_ta),
        )
        ewp = int(_target_ta * 4096) + 2048
        self.servos.servo_ctl_z.move_ewp(ewp=ewp)

        with self._servo_position_persist() as p:
            p.servo_z_ta = _target_ta

        return _target_ta

    def _frequency_get_servo_f(self) -> float:
        try:
            if self.servos is None:
                return 42.0
            if ENABLE_STS3215_SERVO_F:
                return
            return self.servos.servo_ctl_f.get_persist().present_ta
        except calculator.ExceptionRequireHoming:
            return 0.1

    def _mp_exec(self, label_full: str, cmd: str) -> str:
        assert isinstance(label_full, str)
        assert isinstance(cmd, str)

        process = util_mpremote.mp_exec(
            device=self.mp_device,
            cmd=cmd,
            logfilename=ServoPortConfig.get_logfilename(
                directory_logs=DIRECTORY_LOGS,
                label_full=label_full,
            ),
        )
        _msg = calculator.parse_value_str(
            stdout=process.stdout,
            label="exec: OK",
        )
        return process.stdout

    def _pico_run(self, direction_up: bool, on: bool) -> None:
        assert isinstance(direction_up, bool)
        assert isinstance(on, bool)
        self._mp_exec(
            label_full="pico_run",
            cmd=f"run(direction_up={direction_up}, on={on})",
        )

    def _enable_widgets(self, state_vna_enabled: bool) -> None:
        # state_vna_enabled = self.checkbox_vna_enable.isChecked()
        self.heading_servo.setEnabled(state_vna_enabled)
        self.frequency_servo_f.setEnabled(state_vna_enabled)
        self.impedance_servo_z.setEnabled(state_vna_enabled)

    @contextlib.contextmanager
    def _servo_position_persist(
        self,
    ) -> typing.Generator[util_persist.ServoPositionPersistent, None, None]:
        """Context manager for loading and saving servo position persistently."""
        filename = DIRECTORY_OF_THIS_FILE / "tmp_sts3215_servo_z_h.json"
        persist = util_persist.ServoPositionPersistent.get_persist(
            filename=filename
        )
        try:
            yield persist
        finally:
            util_persist.ServoPositionPersistent.save(
                filename=filename,
                persist=persist,
            )
