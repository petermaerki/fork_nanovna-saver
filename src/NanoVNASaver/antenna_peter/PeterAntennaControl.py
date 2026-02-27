import contextlib
import logging
import pathlib
import socket
import typing
from typing import TYPE_CHECKING, TypeVar

from PySide6 import QtCore, QtGui, QtWidgets
from sts3215_ctl import util_mpremote
from sts3215_ctl.servo_ctl import Servo, ServoPortConfig, ServoPersistent
from sts3215_micropython.sts3215_portable import calculator

from ..Controls.Control import Control
from . import peter_widgets, statemachine_tuner, util_persist, util_vna_sweep
from .util_calculate_safety import calculate_safety_distance

if TYPE_CHECKING:
    from ..NanoVNASaver import NanoVNASaver

logger = logging.getLogger(__name__)

QWidgetT = TypeVar("QWidgetT", bound=QtWidgets.QWidget)

RIGCTL_HOSTNAME = "localhost"
RIGCTL_HOSTNAME = "yoga-260"
RIGCTL_PORT = 4532

DIRECTORY_OF_THIS_FILE = pathlib.Path(__file__).parent
DIRECTORY_MICROPYTHON = DIRECTORY_OF_THIS_FILE / "micropython"
assert DIRECTORY_MICROPYTHON.is_dir()
DIRECTORY_LOGS = DIRECTORY_OF_THIS_FILE / "tmp_sts3215_servo_f_logs"
DIRECTORY_LOGS.mkdir(exist_ok=True)
FILENAME_PERSIST_SERVO_F = DIRECTORY_OF_THIS_FILE / "tmp_sts3215_servo_f.json"

ENABLE_STS3215 = True
ENABLE_STS3215_SERVO_F = True
DEBUG_FORCE_BAND_SWITCH = False
DEBUG_BMM350_CALIBRATION = False


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
                filename_persist=FILENAME_PERSIST_SERVO_F,
            )
        self.servo_ctl_z = Servo(
            port_config=port_config,
            scs_id=3,
            torque_limit=150,
            goal_speed=1000,
            acceleration=10,
            position_p_gain=10,
            position_i_gain=2,
        )
        self.servo_ctl_h = Servo(
            port_config=port_config,
            scs_id=4,
            torque_limit=100,
            goal_speed=100,
            acceleration=1,
            position_p_gain=2,
            position_i_gain=0,
        )


class PeterAntennaControl(Control):
    def _start_heading_udp_listener(self):
        import threading
        import socket
        def udp_loop():
            UDP_IP = "127.0.0.1"
            UDP_PORT = 12000
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind((UDP_IP, UDP_PORT))
            while True:
                data = sock.recvfrom(4096)[0]
                decoded_data = data.decode('utf-8', errors='ignore')
                print(f"[UDP] Received: {decoded_data}")
                import re
                match = re.search(r"<AZIMUTH>([0-9.]+)</AZIMUTH>", decoded_data)
                if match:
                    azimuth_val = match.group(1)
                    print(f"[UDP] Parsed azimuth: {azimuth_val}")
                    try:
                        self.heading_target.set_value(float(azimuth_val))
                    except Exception as e:
                        print(f"[UDP] Error updating heading_target: {e}")
        threading.Thread(target=udp_loop, daemon=True).start()
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
        self._layout = QtWidgets.QVBoxLayout()
        self._start_heading_udp_listener()

        self.filename_servo_position_persist = (
            DIRECTORY_OF_THIS_FILE / "tmp_sts3215_servo_z_h.json"
        )

        with self._servo_position_persist() as p:
            if DEBUG_FORCE_BAND_SWITCH:
                p.freq_antenna_hz = 10e6
            servo_position_persist = p

        self.vna = util_vna_sweep.VnaSweeper(ctl=self, sweep=self.app.sweep)
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

        if DEBUG_BMM350_CALIBRATION:
            while True:
                stdout = self._mp_exec(
                    label_full="calibrate_bmm",
                    cmd="calibrate_bmm(sample_count=30)",
                )
                xyz_min_max_str = calculator.parse_value_str(
                    stdout=stdout,
                    label="xyz_min_max_str",
                )
                print(xyz_min_max_str)

        # time.sleep(1.0)
        self.servos: Servos | None = None

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.VLine)

        self.checkbox_tune = self.add_row(
            peter_widgets.CheckboxWidget("Tune automatic")
        ).checkbox
        self.checkbox_vna_enable = self.add_row(
            peter_widgets.CheckboxWidget("VNA enable, TX inhibit")
        ).checkbox

        self.add_row(peter_widgets.SeparatorWidget())

        self.heading_checkbox = self.add_row(
            peter_widgets.CheckboxWidget("Tune heading enable")
        ).checkbox
        self.heading_checkbox.setChecked(False)
        self.heading_target = self.add_row(
            peter_widgets.PushButtonWidget(
                label="Tune heading target", f_value=0.0, unit="deg"
            )
        )
        self.heading_current = self.add_row(
            peter_widgets.ValueWidget(
                label="Tune heading current",
                unit="deg",
                fmt="0.1f",
            )
        )
        self.heading_servo = self.add_row(
            peter_widgets.PushButtonWidget(
                label="Tune heading servo_h",
                f_value=servo_position_persist.servo_h_ta,
                unit="turns",
                cb_set=self._heading_set_servo_h,
            )
        )

        self.add_row(peter_widgets.SeparatorWidget())

        self.frequency_tune_enable = self.add_row(
            peter_widgets.CheckboxWidget("Tune Frequency enable")
        ).checkbox
        self.frequency_tune_enable.setChecked(True)
        self.frequency_offset = self.add_row(
            peter_widgets.PushButtonWidget(
                label="Frequency Offset", f_value=1500.0, unit="Hz"
            )
        )
        self.frequency_auto_get = self.add_row(
            peter_widgets.CheckboxWidget("Frequency auto get from TX")
        ).checkbox
        self.frequency_auto_get.setChecked(True)

        self.frequency_tx = self.add_row(
            peter_widgets.PushButtonWidget(
                label="Frequency TX",
                f_value=42.0,
                unit="Hz",
            )
        )
        self.frequency_target = self.add_row(
            peter_widgets.ValueWidget(
                label="Frequency target", unit="Hz", fmt="0.0f"
            )
        )
        self.frequency_current = self.add_row(
            peter_widgets.ValueWidget(
                label="Frequency current", unit="Hz", fmt="0.0f"
            )
        )

        self.frequency_servo_f = self.add_row(
            peter_widgets.PushButtonWidget(
                label="Frequency servo_f",
                f_value=self._frequency_get_servo_f(),
                unit="turns",
                cb_set=self._frequency_set_servo_f,
            )
        )

        self.add_row(peter_widgets.SeparatorWidget())
        self.impedance_tune_enable = self.add_row(
            peter_widgets.CheckboxWidget("Tune Impedance enable")
        ).checkbox
        self.impedance_tune_enable.setChecked(True)
        self.impedance_target = self.add_row(
            peter_widgets.PushButtonWidget(
                label="Impedance target", f_value=50.0, unit="Ohm"
            )
        )
        self.impedance_current = self.add_row(
            peter_widgets.ValueWidget(label="Impedance current", unit="Ohm")
        )
        self.impedance_servo_z = self.add_row(
            peter_widgets.PushButtonWidget(
                label="Impedance servo_z",
                f_value=servo_position_persist.servo_z_ta,
                unit="turns",
                cb_set=self._impedance_set_servo_z,
            )
        )

        self.add_row(peter_widgets.SeparatorWidget())

        # New: single display for all safety info
        self.power_spin = self.add_row(
            peter_widgets.PowerspinWidget(
                label="Power transmitter 5...100",
                value=100,
                min_value=5,
                max_value=100,
                unit="W",
            )
        ).power_spin

        self.add_row(peter_widgets.SeparatorWidget())

        def safety_html_widget() -> QtWidgets.QTextBrowser:
            widget = QtWidgets.QTextBrowser()
            # Hide scrollbars
            widget.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            widget.setHorizontalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            # Remove margins and set minimal padding
            widget.setContentsMargins(0, 0, 0, 0)
            widget.setStyleSheet(
                "QTextBrowser { padding: 0; margin: 0; border: none; }"
            )
            # Make the widget expand vertically to fit all lines
            widget.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
            widget.setFixedHeight(200)
            # Enable external link clicks (default for QTextBrowser)
            widget.setOpenExternalLinks(True)
            widget.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextBrowserInteraction
                | QtCore.Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
            return widget

        self.safety_info_html = self.add_row(safety_html_widget())

        # (power status label removed — FT-991 cannot be queried for power)
        # connect power control immediately so changes always send to rigctld
        try:
            self.power_spin.valueChanged.connect(self.on_power_changed)
        except Exception:
            logger.exception("Failed to connect power spin signal at init")

        self.layout.addRow(self._layout)

        # 'Set Values' signal connection commented out because the input is disabled
        # self.button_set_values.pressed.connect(self.on_button_set_values)
        self.checkbox_tune.checkStateChanged.connect(self.on_tune)
        # self.checkbox_up.checkStateChanged.connect(self.on_up)
        # self.checkbox_down.checkStateChanged.connect(self.on_down)
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

        self.rigctl_read_tx_timer = QtCore.QTimer(self)
        self.rigctl_read_tx_timer.setInterval(2000)
        self.rigctl_read_tx_timer.timeout.connect(
            self._rigctl_read_tx_frequency
        )
        self.rigctl_read_tx_timer.start()

    def on_tune(self, checked: QtCore.Qt.CheckState) -> None:
        """
        Statemachine "Tuning".
        This is the entry action.
        """
        assert isinstance(checked, QtCore.Qt.CheckState)
        state_tuning = checked.value  #  self.checkbox_tune.isChecked()
        self.checkbox_vna_enable.setChecked(state_tuning)
        if self.checkbox_tune.isChecked():
            self.statemachine_tuner.reset_iterations(ctl=self)



    def on_vna_enable(self, checked: QtCore.Qt.CheckState) -> None:
        """
        Statemachine "VNA Enable".
        This is the entry action.
        """
        assert isinstance(checked, QtCore.Qt.CheckState)
        try:
            state_vna_enabled = checked == QtCore.Qt.CheckState.Checked
            # The following code will ALSO power the servos
            self._mp_exec(
                label_full="pico_vna_enable",
                cmd=f"vna_enable(enable={int(state_vna_enabled)})",
            )
            if state_vna_enabled:
                if ENABLE_STS3215:
                    self.servos = Servos(port_config=self.port_config)
                # Setze VSWR-Marker bei Aktivierung des VNA
                try:
                    self.vna._set_marker(0, 2.64)
                except Exception as e:
                    logger.warning(f"VSWR Marker konnte nicht gesetzt werden: {e}")
            else:
                self.servos = None
                self.vna.run_vna_on_frequency_which_does_not_harm()

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
                    (RIGCTL_HOSTNAME, RIGCTL_PORT), timeout=1
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

    def _update_safety_calculation(self, freq_hz: float):
        """Update safety calculation display with a formatted string."""
        try:
            set_f_hz = freq_hz
            f_mhz = set_f_hz / 1e6
            watts = int(self.power_spin.value())
            info = calculate_safety_distance(
                f_mhz=f_mhz,
                p_watt=watts,
                antenna_q_factor=self.vna.antenna_q,
                swr_min=self.vna.swr_min,
                antenna_bandwith_3db_Hz=self.vna.antenna_bandwith_3db_Hz,
            )
            self.safety_info_html.setHtml(info)
        except Exception:
            logger.exception("Failed to update safety calculation")
            self.safety_info_html.setHtml("--")

    # def on_auto_get_frequency_toggle(self):
    #     """Start/stop the automatic frequency polling based on checkbox state."""
    #     if self.frequency_auto_get.isChecked():
    #         logger.debug("Starting auto frequency fetch timer (1s)")
    #         # do an immediate fetch, then rely on timer for subsequent updates
    #         self._auto_get_frequency()
    #         self.auto_get_timer.start()
    #     else:
    #         logger.debug("Stopping auto frequency fetch timer")
    #         self.auto_get_timer.stop()

    def _get_frequency_from_tx(self) -> int:
        try:
            with socket.create_connection(
                (RIGCTL_HOSTNAME, RIGCTL_PORT), timeout=1
            ) as s:
                s.sendall(b"f\n")
                data = s.recv(1024).strip()
                if not data:
                    logger.warning("Auto-get frequency: no data received")
                    return 42
                try:
                    return int(data)
                except ValueError:
                    logger.warning(
                        "Auto-get frequency: received non-integer: %r", data
                    )
                    return 42
        except Exception:
            logger.exception("Auto-get frequency failed")
            return 42

    def _rigctl_read_tx_frequency(self):
        """Fetch frequency from localhost socket and set it to the SWR input field.

        The expected protocol: connect to localhost:4532, send 'f\n', receive an
        integer frequency in Hz (as bytes). Any errors are logged and ignored.
        """
        if self.frequency_auto_get.isChecked():
            freq_hz = float(self._get_frequency_from_tx())
            self.frequency_tx.set_value(freq_hz)
        else:
            freq_hz = self.frequency_tx.f_value
        offset_hz = self.frequency_offset.f_value
        freq_hz_with_offset = freq_hz + offset_hz

        self.frequency_target.set_value(freq_hz_with_offset)

        self._update_safety_calculation(freq_hz=freq_hz)

    def _frequency_set_servo_f(self, target_ta: float) -> float:
        if self.servos is None:
            return target_ta
        if not ENABLE_STS3215_SERVO_F:
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
            max(statemachine_tuner.IMPEDANCE_TARGET_TA_MIN, target_ta),
        )
        ewp = int(_target_ta * 4096) + 2048
        self.servos.servo_ctl_z.move_ewp(ewp=ewp)

        with self._servo_position_persist() as p:
            p.servo_z_ta = _target_ta

        return _target_ta

    def _frequency_get_servo_f(self) -> float:
        if not ENABLE_STS3215_SERVO_F:
            return 4.2
        try:
            persist = ServoPersistent.get_persist(
                filename=FILENAME_PERSIST_SERVO_F
            )
            return persist.present_ta
        except calculator.ExceptionRequireHoming:
            return 4.3

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

    def _enable_widgets(self, state_vna_enabled: bool) -> None:
        # state_vna_enabled = self.checkbox_vna_enable.isChecked()
        self.heading_servo.setEnabled(state_vna_enabled)
        self.frequency_servo_f.setEnabled(state_vna_enabled)
        self.impedance_servo_z.setEnabled(state_vna_enabled)

    @property
    def _position_persist(self) -> util_persist.ServoPositionPersistent:
        return util_persist.ServoPositionPersistent.get_persist(
            filename=self.filename_servo_position_persist
        )

    @contextlib.contextmanager
    def _servo_position_persist(
        self,
    ) -> typing.Generator[util_persist.ServoPositionPersistent, None, None]:
        """Context manager for loading and saving servo position persistently."""
        persist = self._position_persist
        try:
            yield persist
        finally:
            util_persist.ServoPositionPersistent.save(
                filename=self.filename_servo_position_persist,
                persist=persist,
            )
