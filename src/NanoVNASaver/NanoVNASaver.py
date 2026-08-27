#  NanoVNASaver
#
#  A python program to view and export Touchstone data from a NanoVNA
#  Copyright (C) 2019, 2020  Rune B. Broberg
#  Copyright (C) 2020,2021 NanoVNA-Saver Authors
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
import contextlib
import logging
import threading
from time import localtime, strftime

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QWidget

from .About import VERSION
from .Calibration import Calibration
from .Charts import (
    CapacitanceChart,
    CombinedLogMagChart,
    GroupDelayChart,
    InductanceChart,
    LogMagChart,
    MagnitudeChart,
    MagnitudeZChart,
    MagnitudeZSeriesChart,
    MagnitudeZShuntChart,
    PermeabilityChart,
    PhaseChart,
    PolarChart,
    QualityFactorChart,
    RealImaginaryMuChart,
    RealImaginaryZChart,
    RealImaginaryZSeriesChart,
    RealImaginaryZShuntChart,
    SmithChart,
    SParameterChart,
    TDRChart,
    VSWRChart,
)
from .Charts.Chart import Chart
from .Controls.MarkerControl import MarkerControl
from .Controls.SerialControl import SerialControl
from .Controls.SweepControl import SweepControl
from .Defaults import APP_SETTINGS, AppSettings, get_app_config
from .Formatting import format_frequency, format_gain, format_vswr
from .Hardware.Hardware import Interface
from .Hardware.VNA import VNA
from .Marker.Delta import DeltaMarker
from .Marker.Widget import Marker
from .RFTools import corr_att_data
from .Settings.Bands import BandsModel
from .Settings.Sweep import Sweep
from .SweepWorker import SweepWorker
from .Touchstone import Touchstone
from .Windows import (
    AboutWindow,
    AnalysisWindow,
    CalibrationWindow,
    DeviceSettingsWindow,
    DisplaySettingsWindow,
    FilesWindow,
    SweepSettingsWindow,
    TDRWindow,
)
from .Windows.ui import get_window_icon

logger = logging.getLogger(__name__)

WORKING_KILL_TIME_MS = 10 * 1000


class Communicate(QObject):
    data_available = QtCore.Signal()


class NanoVNASaver(QWidget):
    version = VERSION
    scale_factor = 1.0

    def __init__(self) -> None:
        super().__init__()
        self.communicate = Communicate()
        self.s21att = 0.0
        self.setWindowIcon(get_window_icon())
        # TODO APP_SETTINGS should be used instead app.setting\
        self.settings: AppSettings = APP_SETTINGS
        app_config = self.settings.restore_config()
        self.threadpool = QtCore.QThreadPool()
        self.sweep = Sweep()
        self.worker = SweepWorker(self)

        self.worker.signals.updated.connect(self.dataUpdated)
        self.worker.signals.finished.connect(self.sweepFinished)
        self.worker.signals.sweep_error.connect(self.showSweepError)

        self.markers: list[Marker] = []
        self.marker_ref = False

        self.marker_column = QtWidgets.QVBoxLayout()
        self.marker_frame = QtWidgets.QFrame()
        self.marker_column.setContentsMargins(0, 0, 0, 0)
        self.marker_frame.setLayout(self.marker_column)

        self.interface = Interface("serial", "None")
        self.vna: VNA = VNA(self.interface)

        self.calibration: Calibration = Calibration()
        self.sweep_control = SweepControl(self)
        self.marker_control = MarkerControl(self)
        self.serial_control = SerialControl(self)
        self.serial_control.connected.connect(
            self.sweep_control.update_sweep_btn
        )

        self.bands: BandsModel = BandsModel()

        self.dataLock = threading.Lock()
        self.data: Touchstone = Touchstone()
        self.ref_data: Touchstone = Touchstone()

        self.sweepSource = ""
        self.referenceSource = ""
        self._snap_marker1_to_min_swr = False

        logger.debug("Building user interface")

        self.baseTitle = f"NanoVNA Saver {NanoVNASaver.version}"
        self.updateTitle()
        layout = QtWidgets.QBoxLayout(
            QtWidgets.QBoxLayout.Direction.LeftToRight
        )

        scrollarea = QtWidgets.QScrollArea()
        outer = QtWidgets.QVBoxLayout()
        outer.addWidget(scrollarea)
        self.setLayout(outer)
        scrollarea.setWidgetResizable(True)
        self.resize(app_config.gui.window_width, app_config.gui.window_height)
        scrollarea.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.MinimumExpanding,
            QtWidgets.QSizePolicy.Policy.MinimumExpanding,
        )
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.MinimumExpanding,
            QtWidgets.QSizePolicy.Policy.MinimumExpanding,
        )
        widget = QWidget()
        widget.setLayout(layout)
        scrollarea.setWidget(widget)

        self.charts = {
            "s11": {
                "capacitance": CapacitanceChart("S11 Serial C"),
                "group_delay": GroupDelayChart("S11 Group Delay"),
                "inductance": InductanceChart("S11 Serial L"),
                "log_mag": LogMagChart("S11 Return Loss"),
                "magnitude": MagnitudeChart("|S11|"),
                "magnitude_z": MagnitudeZChart("S11 |Z|"),
                "permeability": PermeabilityChart(
                    "S11 R/\N{GREEK SMALL LETTER OMEGA} &"
                    " X/\N{GREEK SMALL LETTER OMEGA}"
                ),
                "phase": PhaseChart("S11 Phase"),
                "q_factor": QualityFactorChart("S11 Quality Factor"),
                "real_imag": RealImaginaryZChart("S11 R+jX"),
                "real_imag_mu": RealImaginaryMuChart(
                    "S11 \N{GREEK SMALL LETTER MU}"
                ),
                "smith": SmithChart("S11 Smith Chart"),
                "s_parameter": SParameterChart("S11 Real/Imaginary"),
                "vswr": VSWRChart("S11 VSWR"),
                "sa_dbm": LogMagChart("Signal Analyser dBm"),
            },
            "s21": {
                "group_delay": GroupDelayChart(
                    "S21 Group Delay", reflective=False
                ),
                "log_mag": LogMagChart("S21 Gain"),
                "magnitude": MagnitudeChart("|S21|"),
                "magnitude_z_shunt": MagnitudeZShuntChart("S21 |Z| shunt"),
                "magnitude_z_series": MagnitudeZSeriesChart("S21 |Z| series"),
                "real_imag_shunt": RealImaginaryZShuntChart("S21 R+jX shunt"),
                "real_imag_series": RealImaginaryZSeriesChart(
                    "S21 R+jX series"
                ),
                "phase": PhaseChart("S21 Phase"),
                "polar": PolarChart("S21 Polar Plot"),
                "s_parameter": SParameterChart("S21 Real/Imaginary"),
            },
            "combined": {
                "log_mag": CombinedLogMagChart("S11 & S21 LogMag"),
            },
        }
        self.tdr_chart: TDRChart = TDRChart("TDR")
        self.tdr_mainwindow_chart = TDRChart("TDR")

        # List of all the S11 charts, for selecting
        self.s11charts = list(self.charts["s11"].values())

        # List of all the S21 charts, for selecting
        self.s21charts = list(self.charts["s21"].values())

        # List of all charts that use both S11 and S21
        self.combinedCharts = list(self.charts["combined"].values())

        # List of all charts that can be selected for display
        self.selectable_charts = (
            self.s11charts
            + self.s21charts
            + self.combinedCharts
            + [
                self.tdr_mainwindow_chart,
            ]
        )

        # List of all charts that subscribe to updates (including duplicates!)
        self.subscribing_charts = []
        self.subscribing_charts.extend(self.selectable_charts)
        self.subscribing_charts.append(self.tdr_chart)

        for c in self.subscribing_charts:
            c.popout_requested.connect(self.popoutChart)

        self.charts_layout = QtWidgets.QGridLayout()

        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Q"), self, self.close)

        ###############################################################
        #  Create main layout
        ###############################################################

        left_column = QtWidgets.QVBoxLayout()
        right_column = QtWidgets.QVBoxLayout()
        right_column.addLayout(self.charts_layout)
        self.marker_frame.setHidden(app_config.gui.markers_hidden)
        chart_widget = QWidget()
        chart_widget.setLayout(right_column)
        self.splitter = QtWidgets.QSplitter()
        self.splitter.addWidget(self.marker_frame)
        self.splitter.addWidget(chart_widget)

        self.splitter.restoreState(app_config.gui.splitter_sizes)

        layout.addLayout(left_column)
        layout.addWidget(self.splitter, 2)

        ###############################################################
        #  Windows
        ###############################################################

        self.windows: dict[str, QtWidgets.QDialog] = {
            "about": AboutWindow(self),
            "analysis": AnalysisWindow(self),
            "calibration": CalibrationWindow(self),
            "device_settings": DeviceSettingsWindow(self),
            "file": FilesWindow(self),
            "sweep_settings": SweepSettingsWindow(self),
            "setup": DisplaySettingsWindow(self),
            "tdr": TDRWindow(self),
        }

        ###############################################################
        #  Sweep control
        ###############################################################

        left_column.addWidget(self.sweep_control)

        # ###############################################################
        #  Marker control
        ###############################################################

        left_column.addWidget(self.marker_control)

        for c in self.subscribing_charts:
            c.setMarkers(self.markers)
            c.setBands(self.bands)

        self.marker_data_layout = QtWidgets.QVBoxLayout()
        self.marker_data_layout.setContentsMargins(0, 0, 0, 0)

        for m in self.markers:
            self.marker_data_layout.addWidget(m.get_data_layout())

        scroll2 = QtWidgets.QScrollArea()
        scroll2.setWidgetResizable(True)
        scroll2.setVisible(True)

        widget2 = QWidget()
        widget2.setLayout(self.marker_data_layout)
        scroll2.setWidget(widget2)
        self.marker_column.addWidget(scroll2)

        # init delta marker (but assume only one marker exists)
        self.delta_marker = DeltaMarker("Delta Marker 2 - Marker 1")
        self.delta_marker_layout = self.delta_marker.get_data_layout()
        self.delta_marker_layout.hide()
        self.marker_column.addWidget(self.delta_marker_layout)

        ###############################################################
        #  Statistics/analysis
        ###############################################################

        s11_control_box = QtWidgets.QGroupBox()
        s11_control_box.setTitle("S11")
        s11_control_layout = QtWidgets.QFormLayout()
        s11_control_layout.setVerticalSpacing(0)
        s11_control_box.setLayout(s11_control_layout)

        self.s11_min_swr_label = QtWidgets.QLabel()
        s11_control_layout.addRow("Min VSWR:", self.s11_min_swr_label)
        self.s11_min_rl_label = QtWidgets.QLabel()
        s11_control_layout.addRow("Return loss:", self.s11_min_rl_label)

        self.marker_column.addWidget(s11_control_box)

        s21_control_box = QtWidgets.QGroupBox()
        s21_control_box.setTitle("S21")
        s21_control_layout = QtWidgets.QFormLayout()
        s21_control_layout.setVerticalSpacing(0)
        s21_control_box.setLayout(s21_control_layout)

        self.s21_min_gain_label = QtWidgets.QLabel()
        s21_control_layout.addRow("Min gain:", self.s21_min_gain_label)

        self.s21_max_gain_label = QtWidgets.QLabel()
        s21_control_layout.addRow("Max gain:", self.s21_max_gain_label)

        self.marker_column.addWidget(s21_control_box)

        # self.marker_column.addStretch(1)

        btn_show_analysis = QtWidgets.QPushButton("Analysis ...")
        btn_show_analysis.setMinimumHeight(20)
        btn_show_analysis.clicked.connect(
            lambda: self.display_window("analysis")
        )
        self.marker_column.addWidget(btn_show_analysis)

        quick_box = QtWidgets.QGroupBox("Peter controls magnetic loop antenna")
        quick_box.setStyleSheet(
            "QGroupBox { border: 2px solid #f0c000;"
            " border-radius: 4px; margin-top: 6px; }"
            " QGroupBox::title { color: #f0c000; }"
        )
        quick_layout = QtWidgets.QVBoxLayout()
        quick_box.setLayout(quick_layout)

        overview_segments_layout = QtWidgets.QHBoxLayout()
        overview_segments_layout.addWidget(
            QtWidgets.QLabel("Overview segments:")
        )
        self.inp_overview_segments = QtWidgets.QLineEdit("200")
        self.inp_overview_segments.setFixedWidth(50)
        overview_segments_layout.addWidget(self.inp_overview_segments)
        overview_segments_layout.addStretch()
        quick_layout.addLayout(overview_segments_layout)

        btn_sweep_1_30 = QtWidgets.QPushButton("Sweep 0.5 – 30 MHz")
        btn_sweep_1_30.setMinimumHeight(20)
        btn_sweep_1_30.clicked.connect(self.sweep_0p5_30_mhz)
        quick_layout.addWidget(btn_sweep_1_30)

        antenna_name_layout = QtWidgets.QHBoxLayout()
        antenna_name_layout.addWidget(QtWidgets.QLabel("Name:"))
        self.inp_antenna_name = QtWidgets.QLineEdit("antenna_xy")
        antenna_name_layout.addWidget(self.inp_antenna_name)
        quick_layout.addLayout(antenna_name_layout)

        self.btn_save_s1p = QtWidgets.QPushButton("save ...")
        self.btn_save_s1p.setMinimumHeight(20)
        self.btn_save_s1p.clicked.connect(self.save_s1p_quick)
        quick_layout.addWidget(self.btn_save_s1p)

        swr_info_box = QtWidgets.QGroupBox()
        swr_info_layout = QtWidgets.QFormLayout()
        swr_info_layout.setVerticalSpacing(0)
        swr_info_box.setLayout(swr_info_layout)

        self.chk_continuous = QtWidgets.QCheckBox(
            "sweep continuous for manual tuning"
        )
        self.chk_continuous.setChecked(False)

        def _on_continuous_toggled(checked: bool):
            if checked:
                self.sweep_control.set_start(500_000)
                self.sweep_control.set_end(30_000_000)
                self.sweep_control.set_segments(5)
                self.sweep.set_logarithmic(True)
                self.sweep_start()

        self.chk_continuous.toggled.connect(_on_continuous_toggled)
        swr_info_layout.addRow(self.chk_continuous)

        self.quick_swr_min_label = QtWidgets.QLabel()
        swr_info_layout.addRow("SWR min", self.quick_swr_min_label)
        self.quick_swr_freq_label = QtWidgets.QLabel()
        swr_info_layout.addRow("SWR min f MHz", self.quick_swr_freq_label)
        left_column.addWidget(swr_info_box)

        left_column.addWidget(quick_box)

        zoom_range_layout = QtWidgets.QHBoxLayout()
        zoom_range_layout.addWidget(QtWidgets.QLabel("Zoom range +/- Hz:"))
        self.inp_zoom_range = QtWidgets.QLineEdit("1000000")
        self.inp_zoom_range.setFixedWidth(80)
        zoom_range_layout.addWidget(self.inp_zoom_range)
        zoom_range_layout.addStretch()
        left_column.addLayout(zoom_range_layout)

        zoom_segments_layout = QtWidgets.QHBoxLayout()
        zoom_segments_layout.addWidget(QtWidgets.QLabel("Zoom segments:"))
        self.inp_zoom_segments = QtWidgets.QLineEdit("50")
        self.inp_zoom_segments.setFixedWidth(50)
        zoom_segments_layout.addWidget(self.inp_zoom_segments)
        zoom_segments_layout.addStretch()
        left_column.addLayout(zoom_segments_layout)

        btn_zoom = QtWidgets.QPushButton("Optional: Sweep Zoom to min SWR")
        btn_zoom.setMinimumHeight(20)
        btn_zoom.clicked.connect(self.sweep_zoom_swr)
        left_column.addWidget(btn_zoom)

        ###############################################################
        # TDR
        ###############################################################

        self.tdr_chart.tdrWindow = self.windows["tdr"]
        self.tdr_mainwindow_chart.tdrWindow = self.windows["tdr"]
        self.windows["tdr"].updated.connect(self.tdr_chart.update)
        self.windows["tdr"].updated.connect(self.tdr_mainwindow_chart.update)

        tdr_control_box = QtWidgets.QGroupBox()
        tdr_control_box.setTitle("TDR")
        tdr_control_layout = QtWidgets.QFormLayout()
        tdr_control_box.setLayout(tdr_control_layout)

        self.tdr_result_label = QtWidgets.QLabel()
        self.tdr_result_label.setMinimumHeight(20)
        tdr_control_layout.addRow(
            "Estimated cable length:", self.tdr_result_label
        )

        self.tdr_button = QtWidgets.QPushButton("Time Domain Reflectometry ...")
        self.tdr_button.setMinimumHeight(20)
        self.tdr_button.clicked.connect(lambda: self.display_window("tdr"))

        tdr_control_layout.addRow(self.tdr_button)

        left_column.addWidget(tdr_control_box)

        ###############################################################
        #  Spacer
        ###############################################################

        left_column.addSpacerItem(
            QtWidgets.QSpacerItem(
                1,
                1,
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
        )

        ###############################################################
        #  Reference control
        ###############################################################

        reference_control_box = QtWidgets.QGroupBox()
        reference_control_box.setTitle("Reference sweep")
        reference_control_layout = QtWidgets.QFormLayout(reference_control_box)

        btn_set_reference = QtWidgets.QPushButton("Set current as reference")
        btn_set_reference.setMinimumHeight(20)
        btn_set_reference.clicked.connect(self.setReference)
        self.btnResetReference = QtWidgets.QPushButton("Reset reference")
        self.btnResetReference.setMinimumHeight(20)
        self.btnResetReference.clicked.connect(self.resetReference)
        self.btnResetReference.setDisabled(True)

        reference_control_layout.addRow(btn_set_reference)
        reference_control_layout.addRow(self.btnResetReference)

        left_column.addWidget(reference_control_box)

        ###############################################################
        #  Serial control
        ###############################################################

        left_column.addWidget(self.serial_control)

        ###############################################################
        #  Calibration
        ###############################################################

        btnOpenCalibrationWindow = QtWidgets.QPushButton("Calibration ...")
        btnOpenCalibrationWindow.setMinimumHeight(20)
        self.calibrationWindow = CalibrationWindow(self)
        btnOpenCalibrationWindow.clicked.connect(
            lambda: self.display_window("calibration")
        )

        ###############################################################
        #  Display setup
        ###############################################################

        btn_display_setup = QtWidgets.QPushButton("Display setup ...")
        btn_display_setup.setMinimumHeight(20)
        btn_display_setup.clicked.connect(lambda: self.display_window("setup"))

        btn_about = QtWidgets.QPushButton("About ...")
        btn_about.setMinimumHeight(20)

        btn_about.clicked.connect(lambda: self.display_window("about"))

        btn_open_file_window = QtWidgets.QPushButton("Files ...")
        btn_open_file_window.setMinimumHeight(20)

        btn_open_file_window.clicked.connect(
            lambda: self.display_window("file")
        )

        button_grid = QtWidgets.QGridLayout()
        button_grid.addWidget(btn_open_file_window, 0, 0)
        button_grid.addWidget(btnOpenCalibrationWindow, 0, 1)
        button_grid.addWidget(btn_display_setup, 1, 0)
        button_grid.addWidget(btn_about, 1, 1)
        left_column.addLayout(button_grid)

        self.auto_connect()

        logger.debug("Finished building interface")

    def sweep_0p5_30_mhz(self):
        self._snap_marker1_to_min_swr = True
        self.sweep.set_logarithmic(True)
        self.sweep_control.set_start(500_000)
        self.sweep_control.set_end(30_000_000)
        try:
            segments = int(self.inp_overview_segments.text())
        except ValueError:
            segments = 200
        self.sweep_control.set_segments(segments)
        self.sweep_start()

    def save_s1p_quick(self):
        if not self.data.s11:
            return
        min_vswr = min(self.data.s11, key=lambda d: d.vswr)
        freq_mhz = f"{min_vswr.freq / 1e6:.1f}"
        ts = strftime("%Y%m%d_%H%M", localtime())
        name = self.inp_antenna_name.text().strip() or "antenna"
        filename = f"{ts}_{name}_{freq_mhz}MHz.s1p"
        t = Touchstone(filename)
        t.sdata[0] = self.data.s11[:]
        try:
            t.save(1)
            logger.info("Saved %s", filename)
            QtWidgets.QMessageBox.information(self, "Saved", filename)
        except IOError as e:
            logger.exception("Error saving %s: %s", filename, e)

    def sweep_zoom_swr(self):
        self._snap_marker1_to_min_swr = True
        self.sweep.set_logarithmic(False)
        try:
            half = int(self.inp_zoom_range.text())
        except ValueError:
            half = 1_000_000
        try:
            segments = int(self.inp_zoom_segments.text())
        except ValueError:
            segments = 5
        if not self.data.s11:
            return
        center = min(self.data.s11, key=lambda d: d.vswr).freq
        start = max(100_000, center - half)
        self.sweep_control.set_start(start)
        self.sweep_control.set_end(start + 2 * half)
        self.sweep_control.set_segments(segments)
        self.sweep_start()

    def auto_connect(
        self,
    ):  # connect if there is exactly one detected serial device
        if self.serial_control.inp_port.count() == 1:
            self.serial_control.connect_device()

    def _sweep_control(self, start: bool = True) -> None:
        self.sweep_control.progress_bar.setValue(0 if start else 100)
        self.sweep_control.btn_start.setDisabled(start)
        self.sweep_control.btn_stop.setDisabled(not start)
        self.sweep_control.toggle_settings(start)

    def sweep_start(self):
        # Run the device data update
        if not self.vna.connected():
            return
        self._sweep_control(start=True)

        for m in self.markers:
            m.resetLabels()
        self.s11_min_rl_label.setText("")
        self.s11_min_swr_label.setText("")
        self.quick_swr_min_label.setText("")
        self.quick_swr_freq_label.setText("")
        self.s21_min_gain_label.setText("")
        self.s21_max_gain_label.setText("")
        self.tdr_result_label.setText("")

        logger.debug("Starting worker thread")
        self.worker.start()
        # TODO: Rewrite to make worker a qrunnable with worker signals
        # https://www.pythonguis.com/tutorials/multithreading-pyqt6-applications-qthreadpool/
        # self.threadpool.start(self.worker)

    def saveData(self, data, data21, source=None):
        with self.dataLock:
            self.data.s11 = data
            self.data.s21 = data21
            if self.s21att > 0:
                self.data.s21 = corr_att_data(self.data.s21, self.s21att)
        if source is not None:
            self.sweepSource = source
        else:
            time = strftime("%Y-%m-%d %H:%M:%S", localtime())
            name = self.sweep.properties.name or "nanovna"
            self.sweepSource = f"{name}_{time}"

    def markerUpdated(self, marker: Marker):
        with self.dataLock:
            marker.findLocation(self.data.s11)
            marker.resetLabels()
            marker.updateLabels(self.data.s11, self.data.s21)
            for c in self.subscribing_charts:
                c.update()
        if not self.delta_marker_layout.isHidden():
            m1 = self.markers[0]
            m2 = None
            if self.marker_ref:
                if self.ref_data:
                    m2 = Marker("Reference")
                    m2.location = self.markers[0].location
                    m2.resetLabels()
                    m2.updateLabels(self.ref_data.s11, self.ref_data.s21)
                else:
                    logger.warning("No reference data for marker")

            elif Marker.count() >= 2:
                m2 = self.markers[1]

            if m2 is None:
                logger.error("No data for delta, missing marker or reference")
            else:
                self.delta_marker.set_markers(m1, m2)
                self.delta_marker.resetLabels()
                with contextlib.suppress(IndexError):
                    self.delta_marker.updateLabels()

    def dataUpdated(self):
        with self.dataLock:
            s11 = self.data.s11[:]
            s21 = self.data.s21[:]

        for m in self.markers:
            m.resetLabels()
            m.updateLabels(s11, s21)

        for c in self.s11charts:
            c.setData(s11)

        for c in self.s21charts:
            c.setData(s21)

        for c in self.combinedCharts:
            c.setCombinedData(s11, s21)

        self.sweep_control.progress_bar.setValue(int(self.worker.percentage))
        self.windows["tdr"].updateTDR()

        if s11:
            min_vswr = min(s11, key=lambda data: data.vswr)
            self.s11_min_swr_label.setText(
                f"{format_vswr(min_vswr.vswr)} @"
                f" {format_frequency(min_vswr.freq)}"
            )
            self.s11_min_rl_label.setText(format_gain(min_vswr.gain))
            freq_mhz = f"{min_vswr.freq / 1e6:.1f}"
            ts = strftime("%Y%m%d_%H%M", localtime())
            name = self.inp_antenna_name.text().strip() or "antenna"
            self.btn_save_s1p.setText(f"save {ts}_{name}_{freq_mhz}MHz.s1p")
            self.quick_swr_min_label.setText(format_vswr(min_vswr.vswr))
            self.quick_swr_freq_label.setText(f"{min_vswr.freq / 1e6:.6f}")
            if self._snap_marker1_to_min_swr and self.markers:
                self._snap_marker1_to_min_swr = False
                self.markers[0].setFrequency(str(min_vswr.freq))
        else:
            self.s11_min_swr_label.setText("")
            self.s11_min_rl_label.setText("")
            self.quick_swr_min_label.setText("")
            self.quick_swr_freq_label.setText("")

        if s21:
            min_gain = min(s21, key=lambda data: data.gain)
            max_gain = max(s21, key=lambda data: data.gain)
            self.s21_min_gain_label.setText(
                f"{format_gain(min_gain.gain)}"
                f" @ {format_frequency(min_gain.freq)}"
            )
            self.s21_max_gain_label.setText(
                f"{format_gain(max_gain.gain)}"
                f" @ {format_frequency(max_gain.freq)}"
            )
        else:
            self.s21_min_gain_label.setText("")
            self.s21_max_gain_label.setText("")

        self.updateTitle()
        self.communicate.data_available.emit()

    def sweepFinished(self):
        self._sweep_control(start=False)

        for marker in self.markers:
            marker.frequencyInput.textEdited.emit(marker.frequencyInput.text())

        if self.chk_continuous.isChecked():
            self.sweep_start()

    def setReference(self, s11=None, s21=None, source=None):
        if not s11:
            with self.dataLock:
                s11 = self.data.s11[:]
                s21 = self.data.s21[:]

        self.ref_data.s11 = s11
        for c in self.s11charts:
            c.setReference(s11)

        self.ref_data.s21 = s21
        for c in self.s21charts:
            c.setReference(s21)

        for c in self.combinedCharts:
            c.setCombinedReference(s11, s21)

        self.btnResetReference.setDisabled(False)

        self.referenceSource = source or self.sweepSource
        self.updateTitle()

    def updateTitle(self):
        insert = "("
        if self.sweepSource != "":
            insert += (
                f"Sweep: {self.sweepSource} @ {len(self.data.s11)} points"
                f"{', ' if self.referenceSource else ''}"
            )
        if self.referenceSource != "":
            insert += (
                f"Reference: {self.referenceSource} @"
                f" {len(self.ref_data.s11)} points"
            )
        insert += ")"
        title = f"{self.baseTitle} {insert or ''}"
        self.setWindowTitle(title)

    def resetReference(self):
        self.ref_data = Touchstone()
        self.referenceSource = ""
        self.updateTitle()
        for c in self.subscribing_charts:
            c.resetReference()
        self.btnResetReference.setDisabled(True)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(1100, 950)

    def display_window(self, name):
        self.windows[name].show()
        QtWidgets.QApplication.setActiveWindow(self.windows[name])

    def showError(self, text):
        QtWidgets.QMessageBox.warning(self, "Error", text)

    def showSweepError(self):
        self.showError(self.worker.error_message)
        with contextlib.suppress(IOError):
            self.vna.flushSerialBuffers()  # Remove any left-over data
            self.vna.reconnect()  # try reconnection
        self.sweepFinished()

    def popoutChart(self, chart: Chart):
        logger.debug("Requested popout for chart: %s", chart.name)
        new_chart = self.copyChart(chart)
        new_chart.isPopout = True
        new_chart.show()
        new_chart.setWindowTitle(new_chart.name)
        new_chart.setWindowIcon(get_window_icon())

    def copyChart(self, chart: Chart):
        new_chart = chart.copy()
        self.subscribing_charts.append(new_chart)
        if chart in self.s11charts:
            self.s11charts.append(new_chart)
        if chart in self.s21charts:
            self.s21charts.append(new_chart)
        if chart in self.combinedCharts:
            self.combinedCharts.append(new_chart)
        new_chart.popout_requested.connect(self.popoutChart)
        return new_chart

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        self.worker.quit()
        self.worker.wait(WORKING_KILL_TIME_MS)
        for marker in self.markers:
            marker.update_settings()
        self.settings.sync()
        self.bands.saveSettings()
        self.threadpool.waitForDone(2500)

        app_config = get_app_config()
        app_config.chart.marker_count = Marker.count()
        app_config.gui.window_width = self.width()
        app_config.gui.window_height = self.height()
        app_config.gui.splitter_sizes = self.splitter.saveState()

        self.sweep_control.store_settings()

        self.settings.store_config()

        # Dosconnect connected devices and release serial port
        self.serial_control.disconnect_device()

        a0.accept()

    def changeFont(self, font: QtGui.QFont) -> None:
        qf_new = QtGui.QFontMetricsF(font)
        normal_font = QtGui.QFont(font)
        normal_font.setPointSize(8)
        qf_normal = QtGui.QFontMetricsF(normal_font)
        # Characters we would normally display
        standard_string = "0.123456789 0.123456789 MHz \N{OHM SIGN}"
        new_width = qf_new.horizontalAdvance(standard_string)
        old_width = qf_normal.horizontalAdvance(standard_string)
        self.scale_factor = new_width / old_width
        logger.debug(
            "New font width: %f, normal font: %f, factor: %f",
            new_width,
            old_width,
            self.scale_factor,
        )
        # TODO: Update all the fixed widths to account for the scaling
        for m in self.markers:
            m.get_data_layout().setFont(font)
            m.setScale(self.scale_factor)

    def update_sweep_title(self):
        for c in self.subscribing_charts:
            c.setSweepTitle(self.sweep.properties.name)
