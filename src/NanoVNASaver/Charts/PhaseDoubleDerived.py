#  NanoVNASaver - Modified version
#
#  Based on NanoVNASaver by Rune B. Broberg and NanoVNA-Saver Authors
#  Modified for magnetic loop antenna control
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
import logging
import math

import numpy as np
from PySide6 import QtGui
from PySide6.QtGui import QPainter

from ..RFTools import Datapoint
from .Chart import Chart
from .Phase import PhaseChart

logger = logging.getLogger(__name__)


class PhaseDoubleDerivedChart(PhaseChart):
    """Phase second derivative chart (d²Phase/dFreq² in °/MHz²)"""

    def __init__(self, name=""):
        super().__init__(name)
        self.derivedData = []
        self.derivedReference = []

    def copy(self):
        new_chart = super().copy()
        return new_chart

    def drawValues(self, qp: QPainter):
        if len(self.data) == 0 and len(self.reference) == 0:
            return

        # Calculate second derivative (d²Phase/dFreq²) in °/MHz²
        # First unwrap phase, then compute first derivative, then second
        if len(self.data) >= 3:
            phases = [d.phase for d in self.data]
            unwrapped = np.degrees(np.unwrap(phases))
            freqs = [float(d.freq) for d in self.data]

            # First derivative in °/Hz
            first_deriv = []
            for i in range(len(unwrapped) - 1):
                delta_phase = unwrapped[i + 1] - unwrapped[i]
                delta_freq = freqs[i + 1] - freqs[i]
                if delta_freq != 0:
                    first_deriv.append(delta_phase / delta_freq)
                else:
                    first_deriv.append(0.0)

            # Second derivative in °/Hz² then convert to °/MHz²
            self.derivedData = []
            for i in range(len(first_deriv) - 1):
                delta_deriv = first_deriv[i + 1] - first_deriv[i]
                # Use average frequency step for second derivative
                delta_freq = (
                    (freqs[i + 2] - freqs[i + 1]) + (freqs[i + 1] - freqs[i])
                ) / 2
                if delta_freq != 0:
                    # Convert to °/MHz² (multiply by 1e12)
                    second_deriv = (delta_deriv / delta_freq) * 1e12
                    self.derivedData.append(second_deriv)
                else:
                    self.derivedData.append(0.0)
        else:
            self.derivedData = []

        if len(self.reference) >= 3:
            phases_ref = [d.phase for d in self.reference]
            unwrapped_ref = np.degrees(np.unwrap(phases_ref))
            freqs_ref = [float(d.freq) for d in self.reference]

            # First derivative
            first_deriv_ref = []
            for i in range(len(unwrapped_ref) - 1):
                delta_phase = unwrapped_ref[i + 1] - unwrapped_ref[i]
                delta_freq = freqs_ref[i + 1] - freqs_ref[i]
                if delta_freq != 0:
                    first_deriv_ref.append(delta_phase / delta_freq)
                else:
                    first_deriv_ref.append(0.0)

            # Second derivative
            self.derivedReference = []
            for i in range(len(first_deriv_ref) - 1):
                delta_deriv = first_deriv_ref[i + 1] - first_deriv_ref[i]
                delta_freq = (
                    (freqs_ref[i + 2] - freqs_ref[i + 1])
                    + (freqs_ref[i + 1] - freqs_ref[i])
                ) / 2
                if delta_freq != 0:
                    second_deriv = (delta_deriv / delta_freq) * 1e12
                    self.derivedReference.append(second_deriv)
                else:
                    self.derivedReference.append(0.0)
        else:
            self.derivedReference = []

        # Determine min/max for scaling
        if self.fixedValues:
            minAngle = self.minDisplayValue
            maxAngle = self.maxDisplayValue
        elif self.derivedData and len(self.derivedData) > 0:
            minAngle = math.floor(min(self.derivedData))
            maxAngle = math.ceil(max(self.derivedData))
        elif self.derivedReference and len(self.derivedReference) > 0:
            minAngle = math.floor(min(self.derivedReference))
            maxAngle = math.ceil(max(self.derivedReference))
        else:
            minAngle = -1e-6
            maxAngle = 1e-6

        span = float(maxAngle - minAngle)
        self.minAngle = minAngle
        self.maxAngle = maxAngle
        self.span = span if span != 0 else 0.01

        tickcount = math.floor(self.dim.height / 60)

        for i in range(tickcount):
            angle = minAngle + span * i / tickcount
            y = self.topMargin + int(
                (self.maxAngle - angle) / self.span * self.dim.height
            )
            if angle not in [minAngle, maxAngle]:
                qp.setPen(Chart.color.text)
                if angle != 0:
                    # Format derivative value
                    if abs(angle) < 0.001 or abs(angle) > 1000:
                        anglestr = f"{angle:.2e}"
                    else:
                        digits = max(
                            0, min(6, math.floor(6 - math.log10(abs(angle))))
                        )
                        anglestr = f"{angle:.{digits}f}".rstrip("0").rstrip(".")
                else:
                    anglestr = "0"
                qp.drawText(3, y + 3, f"{anglestr}°/MHz²")
                qp.setPen(Chart.color.foreground)
                qp.drawLine(
                    self.leftMargin - 5, y, self.leftMargin + self.dim.width, y
                )
        qp.drawLine(
            self.leftMargin - 5,
            self.topMargin,
            self.leftMargin + self.dim.width,
            self.topMargin,
        )
        qp.setPen(Chart.color.text)
        # Format min/max with appropriate precision
        if abs(maxAngle) < 0.001 or abs(maxAngle) > 1000:
            max_str = f"{maxAngle:.2e}°/MHz²"
        else:
            max_str = f"{maxAngle:.6f}".rstrip("0").rstrip(".") + "°/MHz²"
        if abs(minAngle) < 0.001 or abs(minAngle) > 1000:
            min_str = f"{minAngle:.2e}°/MHz²"
        else:
            min_str = f"{minAngle:.6f}".rstrip("0").rstrip(".") + "°/MHz²"
        qp.drawText(3, self.topMargin + 5, max_str)
        qp.drawText(3, self.dim.height + self.topMargin, min_str)

        self._set_start_stop()

        # Draw bands if required
        if self.bands.enabled:
            self.drawBands(qp, self.fstart, self.fstop)

        self.drawFrequencyTicks(qp)

        # Draw derivative data starting from third point
        if self.derivedData and len(self.data) > 2:
            pen = QtGui.QPen(Chart.color.sweep)
            pen.setWidth(self.dim.point)
            qp.setPen(pen)
            for i in range(len(self.derivedData)):
                # Use frequency from point i+2 (third point onwards)
                x = self.getXPosition(self.data[i + 2])
                deriv = self.derivedData[i]
                y = self.topMargin + int(
                    (self.maxAngle - deriv) / self.span * self.dim.height
                )
                if i == 0:
                    prev_x, prev_y = x, y
                else:
                    qp.drawLine(prev_x, prev_y, x, y)
                    prev_x, prev_y = x, y

        if self.derivedReference and len(self.reference) > 2:
            pen = QtGui.QPen(Chart.color.reference)
            pen.setWidth(self.dim.point)
            qp.setPen(pen)
            for i in range(len(self.derivedReference)):
                x = self.getXPosition(self.reference[i + 2])
                deriv = self.derivedReference[i]
                y = self.topMargin + int(
                    (self.maxAngle - deriv) / self.span * self.dim.height
                )
                if i == 0:
                    prev_x, prev_y = x, y
                else:
                    qp.drawLine(prev_x, prev_y, x, y)
                    prev_x, prev_y = x, y

        self.drawMarkers(qp)

    def getYPosition(self, d: Datapoint) -> int:
        # Find index of this datapoint
        if d in self.data and len(self.data) > 2:
            idx = self.data.index(d)
            # First two points have no second derivative
            if idx < 2:
                return self.topMargin + self.dim.height // 2
            # Use derivative calculated from this and previous points
            deriv_idx = idx - 2
            if deriv_idx < len(self.derivedData):
                deriv = self.derivedData[deriv_idx]
                return self.topMargin + int(
                    (self.maxAngle - deriv) / self.span * self.dim.height
                )
        elif d in self.reference and len(self.reference) > 2:
            idx = self.reference.index(d)
            if idx < 2:
                return self.topMargin + self.dim.height // 2
            deriv_idx = idx - 2
            if deriv_idx < len(self.derivedReference):
                deriv = self.derivedReference[deriv_idx]
                return self.topMargin + int(
                    (self.maxAngle - deriv) / self.span * self.dim.height
                )
        return self.topMargin + self.dim.height // 2

    def valueAtPosition(self, y) -> list[float]:
        absy = y - self.topMargin
        val = -1 * ((absy / self.dim.height * self.span) - self.maxAngle)
        return [val]
