import logging
import typing
import enum
import numpy as np
from ..Marker.Widget import Marker

from ..RFTools import Datapoint

from ..Controls.SweepControl import FrequencyInputWidget
from ..Hardware.VNA import VNA

if typing.TYPE_CHECKING:
    from ..NanoVNASaver import NanoVNASaver
    from .PeterAntennaControl import PeterAntennaControl
    from ..Settings.Sweep import Sweep

logger = logging.getLogger(__name__)

# Frequency limits for magnetic loop antenna
F_USEFUL_MIN_Hz_obsolete = 1.0e6
F_USEFUL_MAX_Hz_obsolete = 30.0e6


class StatemachineVna(enum.IntEnum):
    RESULTS_READY = 1
    RESULTS_OUTDATED = 2
    VNA_IS_SWEEPING = 3


class StatemachineZoom(enum.IntEnum):
    OVERVIEW = 1
    ZOOMED = 2


class VnaSweeper:
    def __init__(self, ctl: PeterAntennaControl, sweep: Sweep):
        self.ctl = ctl
        self.stateVNA = StatemachineVna.RESULTS_OUTDATED
        self.stateZOOM = StatemachineZoom.OVERVIEW
        self.ctl_sweep = sweep
        self.app = self.ctl.app
        # self.vna_is_sweeping___obsolete = False
        self.lower_freq_Hz: float
        self.upper_freq_Hz: float
        self.swr_min: float = 42.0
        # self.reset_range(freq_Hz=7e6)

    def reset_range(self, freq_Hz: float) -> None:
        BAND_TEIL = 0.05
        """Damit mit allen Toleranzen die Resonanz sicher abgebildet wird"""
        self.lower_freq_Hz = freq_Hz * (1.0 - BAND_TEIL)
        self.upper_freq_Hz = freq_Hz * (1.0 + BAND_TEIL)
        self._setDatapointPoints(points_per_segment=100)
        self._setSegments(segments=10)
        self.state = StatemachineVna.RESULTS_OUTDATED
        self.state = StatemachineZoom.OVERVIEW

    def sweep(self) -> bool:
        """Falls Messwerte READY: True, sonst False"""
        if self.stateVNA is StatemachineVna.VNA_IS_SWEEPING:
            return False
        if self.stateVNA is StatemachineVna.RESULTS_READY:
            return True
        assert self.stateVNA is StatemachineVna.RESULTS_OUTDATED
        self._setStartStopFrequencyFloat("Start", self.lower_freq_Hz)
        self._setStartStopFrequencyFloat("Stop", self.upper_freq_Hz)

        self.ctl_sweep.set_logarithmic(False)
        self.app.sweep_start()
        self.stateVNA = StatemachineVna.VNA_IS_SWEEPING
        return False

    def _setStartStopFrequencyFloat(self, tag: str, freq_Hz: float):
        self._setStartStopFrequency(tag, f"{freq_Hz:0.0f} Hz")

    def _setStartStopFrequency(self, tag: str, text: str):
        input = self.app.sweep_control.inputs[tag]
        input.setText(text)
        input.textEdited.emit(input.text())
        self.app.sweep_control.update_sweep()

    def _setDatapointPoints(self, points_per_segment: int):
        # See: src/NanoVNASaver/Windows/DeviceSettings.py, def updateNrDatapoints()
        vna = self.app.vna
        assert isinstance(vna, VNA)
        vna.datapoints = points_per_segment
        logger.debug(f"DP: {vna.datapoints}")
        self.app.sweep.set_points(vna.datapoints)
        self.app.sweep_control.update_step_size()

    def _setSegments(self, segments: int):
        assert 0 < segments < 100
        # Total Punkte = DatapointSegemns x DatapointCount
        self.app.sweep_control.set_segments(count=segments)

    def sweepFinished_peter_antenna(self):
        self.stateVNA = StatemachineVna.RESULTS_READY
        self.ctl.impedance_current.set_value(self.impedance)
        if not self._find_min_swr():
            self.stateVNA = StatemachineVna.RESULTS_OUTDATED
            return
        if not self._zoom():
            self.stateVNA = StatemachineVna.RESULTS_OUTDATED
            return

        #self.ctl.impedance_current.set_value(self.impedance)

        # try:
        #     f_swr_p2_64_l_Hz, f_swr_min_Hz, f_swr_p2_64_h_Hz, swr_min = (
        #         self.find_min_swr()
        #     )
        #     if (
        #         f_swr_p2_64_l_Hz is None
        #         and f_swr_min_Hz is None
        #         and f_swr_p2_64_h_Hz is None
        #     ):
        #         logger.warning("sweepFinished: No valid frequencies found")
        #         # Still call find_sweep_start_stop to handle the case properly
        #     self.find_sweep_start_stop(
        #         f_swr_p2_64_l_Hz,
        #         f_swr_min_Hz,
        #         f_swr_p2_64_h_Hz,
        #         swr_min,
        #     )
        #     self.f_swr_p2_64_l_Hz = f_swr_p2_64_l_Hz
        #     self.f_swr_min_Hz = f_swr_min_Hz
        #     self.f_swr_p2_64_h_Hz = f_swr_p2_64_h_Hz
        #     self.swr_min = swr_min
        # Update ppm and Q displays only after sweep finish / after find_min_swr()
        # try:
        #     self._update_delta_display()
        # except Exception:
        #     logger.exception(
        #         "Failed to update delta display after sweep finish"
        #     )
        # try:
        #     self._update_q_display()
        # except Exception:
        #     logger.exception(
        #         "Failed to update Q display after sweep finish"
        #     )
        # try:
        #     self._update_swrmin_display()
        # except Exception:
        #     logger.exception(
        #         "Failed to update SWR min display after sweep finish"
        #     )
        # try:
        #     self._update_impedance_display()
        # except Exception:
        #     logger.exception(
        #         "Failed to update impedance display after sweep finish"
        #     )
        # increment tune iteration counter if tuning is still enabled
        # try:
        #     if self.checkbox_tune.isChecked():
        #         self._tune_iteration_obsolete += 1
        # except Exception:
        #     logger.exception("Failed to increment tune iteration counter")
        # except Exception:
        #     logger.exception("Critical error in sweepFinished_peter_antenna")
        # Ensure motor is stopped on any error
        # try:
        #     self._pico_run(direction_up=True, on=False)
        #     self._set_motor_status_obsolete("stop (error)")
        # except Exception:
        #     logger.exception("Failed to stop motor after error")

    def _find_min_swr(self) -> bool:
        """Returns True if swr und 2.64 freqeuencies are found"""
        with self.app.dataLock:
            s11: list[Datapoint]
            s11 = self.app.data.s11[:]

            swr = np.asarray([d.vswr for d in s11])
            freq_Hz = np.asarray([float(d.freq) for d in s11])

            if len(swr) == 0 or len(freq_Hz) == 0:
                logger.warning("find_min_swr: No data available")
                return False

            idx_min = np.argmin(swr)
            swr_min = swr[idx_min]

            swr_min_limit = 2.0
            if swr_min > swr_min_limit:
                logger.warning(
                    f"{swr_min=} is not below {swr_min_limit=}: adjust servo_z manually to get a lower swr"
                )
                return False
            f_swr_min_Hz = freq_Hz[idx_min]

            TARGET_SWR_2_64 = 2.64

            left_idx = np.where(swr[:idx_min] >= TARGET_SWR_2_64)[0]
            right_idx = np.where(swr[idx_min:] >= TARGET_SWR_2_64)[0]

            f_swr_p2_64_l_Hz = freq_Hz[left_idx[-1]] if len(left_idx) else None
            f_swr_p2_64_h_Hz = (
                freq_Hz[idx_min + right_idx[0]] if len(right_idx) else None
            )

        if f_swr_p2_64_l_Hz is not None and f_swr_p2_64_h_Hz is not None:
            self.f_swr_p2_64_l_Hz = f_swr_p2_64_l_Hz
            self.f_swr_min_Hz = f_swr_min_Hz
            self.f_swr_p2_64_h_Hz = f_swr_p2_64_h_Hz
            self.swr_min = swr_min
            return True
        return False

    def _zoom(self) -> bool:
        SWEEP_RANGE_OVERLAP = 1.3  # range biger than plus minus 2.64 band
        assert SWEEP_RANGE_OVERLAP > 1.1
        target_hz = self.ctl.frequency_target.f_value
        distance_f = abs(target_hz - self.f_swr_min_Hz)
        distance_f = max(abs(self.f_swr_p2_64_l_Hz - target_hz), distance_f)
        distance_f = max(abs(self.f_swr_p2_64_h_Hz - target_hz), distance_f)
        upper_freq_Hz = target_hz + distance_f * SWEEP_RANGE_OVERLAP
        upper_freq_Hz = min(F_USEFUL_MAX_Hz_obsolete, upper_freq_Hz)
        lower_freq_Hz = target_hz - distance_f * SWEEP_RANGE_OVERLAP
        lower_freq_Hz = max(F_USEFUL_MIN_Hz_obsolete, lower_freq_Hz)

        self.lower_freq_Hz = lower_freq_Hz
        self.upper_freq_Hz = upper_freq_Hz
        POINTS_IN_BANDWITH = 50
        frequency_per_point = abs(self.f_swr_p2_64_h_Hz - self.f_swr_p2_64_l_Hz)/POINTS_IN_BANDWITH
        points_total =  (upper_freq_Hz-lower_freq_Hz)/frequency_per_point
        POINTS_PER_SEGMENT_TARGET = 100
        segments = max(int(points_total/POINTS_PER_SEGMENT_TARGET+0.5),1)
        points_per_segment = int(points_total/segments)
        self._setDatapointPoints(points_per_segment=points_per_segment)
        self._setSegments(segments=segments)
        if self.stateZOOM is StatemachineZoom.OVERVIEW:
            self.stateZOOM = StatemachineZoom.ZOOMED
            '''Nochmals sweepen damit die Aufloesung sicher gut genug ist'''
            return False
        return True

    # ...existing code...

    def find_min_swr_obsolete_old(self):
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

        self._set_marker(0, f_swr_p2_64_l_Hz)
        self._set_marker(1, f_swr_min_Hz)
        self._set_marker(2, f_swr_p2_64_h_Hz)

        return f_swr_p2_64_l_Hz, f_swr_min_Hz, f_swr_p2_64_h_Hz, swr_min
        self.state = StatemachineVna.RESULTS_OUTDATED

    @property
    def f_swr_p2_64_l_Hz(self) -> int:
        return self.app.markers[0].frequencyInput.get_freq()

    @f_swr_p2_64_l_Hz.setter
    def f_swr_p2_64_l_Hz(self, freq_Hz: int) -> None:
        self._set_marker(0, freq_Hz=freq_Hz)

    @property
    def f_swr_min_Hz(self) -> int:
        return self.app.markers[1].frequencyInput.get_freq()

    @f_swr_min_Hz.setter
    def f_swr_min_Hz(self, freq_Hz: int) -> None:
        self._set_marker(1, freq_Hz=freq_Hz)
        self.ctl.frequency_current.set_value(float(freq_Hz))

    @property
    def f_swr_p2_64_h_Hz(self) -> int:
        return self.app.markers[2].frequencyInput.get_freq()

    @f_swr_p2_64_h_Hz.setter
    def f_swr_p2_64_h_Hz(self, freq_Hz: int) -> None:
        self._set_marker(2, freq_Hz=freq_Hz)

    def _set_marker(self, index: int, freq_Hz: int | float):
        assert isinstance(freq_Hz, int | float)
        self.app.markers[index].setFrequency(f"{freq_Hz:0.0f} Hz")

    @property
    def antenna_bandwith_3db_Hz(self) -> int:
        bandwith_hz = self.f_swr_p2_64_h_Hz - self.f_swr_p2_64_l_Hz
        assert bandwith_hz >= 0
        return bandwith_hz

    @property
    def antenna_q(self) -> int:
        try:
            antenna_q = self.f_swr_min_Hz / self.antenna_bandwith_3db_Hz
        except ZeroDivisionError:
            return 42
        return antenna_q

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

    # def _update_delta_display(self):
    #     """Compute deviation of SWR min to set SWR min in kHz and update label.

    #     The display shows (f_swr_min - set_f) / 1e3 as an integer kHz value with
    #     unit 'kHz'. If markers or set frequency are missing/invalid, show `--`.
    #     """
    #     try:
    #         markers = self.app.markers
    #         if len(markers) < 2:
    #             self.delta_display.setText("--")
    #             return
    #         m2 = markers[1]
    #         f_min = m2.frequencyInput.get_freq()
    #         try:
    #             set_f = float(self.input_set_Hz.text())
    #         except Exception:
    #             self.delta_display.setText("--")
    #             return
    #         if set_f == 0 or f_min is None:
    #             self.delta_display.setText("--")
    #             return
    #         delta = f_min - set_f
    #         # determine sign based on comparison before rounding
    #         sign = "-" if delta < 0 else "+"
    #         delta_khz_abs = abs(delta) / 1e3
    #         # show numeric value with three decimal places, include explicit sign and unit
    #         self.delta_display.setText(f"{sign}{delta_khz_abs:.3f} kHz")
    #     except Exception:
    #         logger.exception("Failed to update delta display")
    #         self.delta_display.setText("--")

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
                    self.swr_min = 42
                    return
                swr = np.asarray([d.vswr for d in s11])
            self.swr_min = float(np.min(swr))
        except Exception:
            logger.exception("Failed to update SWR min display")
            self.swr_min = 42

    @property
    def impedance(self) -> float:
        """Compute and display the antenna impedance from the Smith chart circle.

        The three marker points form a circle in the Smith chart.
        Check if the center of the Smith chart (50 Ω, Gamma=0) is inside the circle:
        - If inside: overcoupled → R = 50 Ω x SWR_min
        - If outside: undercoupled → R = 50 Ω / SWR_min
        """
        try:
            with self.app.dataLock:
                s11: list[Datapoint]
                s11 = self.app.data.s11[:]

                swr = np.asarray([d.vswr for d in s11])
                freq_Hz = np.asarray([float(d.freq) for d in s11])

                if len(swr) == 0 or len(freq_Hz) == 0:
                    logger.warning("find_min_swr: No data available")
                    return False

            idx_min = np.argmin(swr)
            swr_min = swr[idx_min]
            f_swr_min_Hz = freq_Hz[idx_min]


            # Find closest datapoints for all three markers
            # def find_closest(freq_target):
            #     min_diff = float("inf")
            #     closest = None
            #     for dp in s11:
            #         diff = abs(dp.freq - freq_target)
            #         if diff < min_diff:
            #             min_diff = diff
            #             closest = dp
            #     return closest

            # dp1 = find_closest(self.f_swr_p2_64_l_Hz)
            # dp2 = find_closest(self.f_swr_min_Hz)
            # dp3 = find_closest(self.f_swr_p2_64_h_Hz)

            punkte_versatz = 10
            dp1=s11[idx_min-punkte_versatz]
            dp2=s11[idx_min]
            dp3=s11[idx_min+punkte_versatz]

            logger.debug(f'impedanze calculation {dp1=} {dp2=} {dp3=}')


            assert dp1 is not None and dp2 is not None and dp3 is not None

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

            assert abs(det) >= 1e-10

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

            return r_antenna

        except Exception as e:
            logger.exception(f"Failed to update impedance display: {e}")
            return 0.0

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
        # if (
        #     f_swr_min_Hz is None
        #     and f_swr_p2_64_l_Hz is None
        #     and f_swr_p2_64_h_Hz is None
        # ):
        #     logger.warning(
        #         "find_sweep_start_stop: No valid frequency data, using full range"
        #     )
        #     self._setStartStopFrequencyFloat("Start", F_USEFUL_MIN_Hz_obsolete)
        #     self._setStartStopFrequencyFloat("Stop", F_USEFUL_MAX_Hz_obsolete)
        #     self._setDatapointCount(500)
        #     # self._set_motor_status_obsolete("stop (no data)")
        #     return

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
            sweep_stop_Hz = min(F_USEFUL_MAX_Hz_obsolete, sweep_stop_Hz)
            sweep_start_Hz = set_f_swr_min_Hz - distance_f * SWEEP_RANGE_OVERLAP
            sweep_start_Hz = max(F_USEFUL_MIN_Hz_obsolete, sweep_start_Hz)

            logger.debug(
                "Zoom calc: f_swr_min=%s Hz, set_f=%s Hz, distance_f=%s Hz, "
                "sweep: %s - %s Hz",
                f_swr_min_Hz,
                set_f_swr_min_Hz,
                distance_f,
                sweep_start_Hz,
                sweep_stop_Hz,
            )
        # else:
        #     # No SWR min found at all, use full range
        #     logger.debug("No SWR min found, using full range")
        #     sweep_start_Hz = F_USEFUL_MIN_Hz_obsolete
        #     sweep_stop_Hz = F_USEFUL_MAX_Hz_obsolete

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
            if (
                F_USEFUL_MIN_Hz_obsolete
                < f_swr_min_Hz
                < F_USEFUL_MAX_Hz_obsolete
            ):
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
                    # if getattr(self, "_tune_iteration", 0) == 0:
                    #     self._set_motor_status_obsolete(
                    #         f"pulse {dir_str} {dur_str}s (preview)"
                    #     )
                    #     print(f"pulse: {duration_s=} (preview)")
                    # else:
                    #     self._set_motor_status_obsolete(
                    #         f"pulse {dir_str} {dur_str}s"
                    #     )
                    #     self._mp_exec(label_full="pico_pulse", cmd=cmd)
                    #     points = points_pulse
                    pass
                else:
                    # Large deviation: continuous run
                    # dir_str = "up" if direction_up else "down"
                    # if getattr(self, "_tune_iteration", 0) == 0:
                    #     self._set_motor_status_obsolete(
                    #         f"motor run {dir_str} (preview)"
                    #     )
                    # else:
                    #     self._set_motor_status_obsolete(f"motor run {dir_str}")
                    #     self._pico_run(direction_up=direction_up, on=True)
                    pass
            else:
                should_stop = True
        else:
            should_stop = True

        # Always send explicit stop command when needed
        # if should_stop:
        #     if getattr(self, "_tune_iteration", 0) > 0:
        #         self._pico_run(direction_up=True, on=False)
        #     if not hasattr(self, "_motor_status_already_set"):
        #         self._set_motor_status_obsolete("stop")

        # Safety check: ensure points is defined
        if "points" not in locals():
            points = 500
            logger.warning("points variable not set, using default: %d", points)

        try:
            self._setDatapointPoints(points)
        except Exception:
            logger.exception("Failed to set datapoint count")

    def run_vna_on_frequency_which_does_not_harm(self) -> None:
        return
        # set a harmless sweep range so the VNA does not disturb (100kHz .. 200kHz)
        try:
            # Restore a harmless sweep on low frequencies and start it so the
            # VNA runs there (this keeps the device quiet on other bands).
            # Update the UI fields so behavior is visible and consistent.
            self._setStartStopFrequencyFloat("Start", 100e3)
            self._setStartStopFrequencyFloat("Stop", 200e3)
            # use a small number of points for quick harmless sweep
            self._setDatapointPoints(201)
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
            logger.exception("Failed to set harmless sweep on tune disable")
