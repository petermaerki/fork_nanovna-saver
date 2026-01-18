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


class PhaseDerivedChart(PhaseChart):
    """Phase derivative chart (dPhase/dFreq in °/MHz)"""

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

        # Calculate phase derivative (dPhase/dFreq) in °/MHz
        # First unwrap phase to remove artificial 180° jumps
        if len(self.data) >= 2:
            phases = [d.phase for d in self.data]
            # Unwrap phase to get continuous values
            unwrapped = np.degrees(np.unwrap(phases))
            freqs = [float(d.freq) for d in self.data]
            self.derivedData = []

            for i in range(len(unwrapped) - 1):
                delta_phase = unwrapped[i + 1] - unwrapped[i]
                delta_freq = freqs[i + 1] - freqs[i]
                if delta_freq != 0:
                    # Convert to °/MHz (multiply by 1000000)
                    derivative = (delta_phase / delta_freq) * 1000000
                    self.derivedData.append(derivative)
                else:
                    self.derivedData.append(0.0)
        else:
            self.derivedData = []

        if len(self.reference) >= 2:
            phases_ref = [d.phase for d in self.reference]
            # Unwrap phase to get continuous values
            unwrapped_ref = np.degrees(np.unwrap(phases_ref))
            freqs_ref = [float(d.freq) for d in self.reference]
            self.derivedReference = []

            for i in range(len(unwrapped_ref) - 1):
                delta_phase = unwrapped_ref[i + 1] - unwrapped_ref[i]
                delta_freq = freqs_ref[i + 1] - freqs_ref[i]
                if delta_freq != 0:
                    # Convert to °/MHz (multiply by 1000000)
                    derivative = (delta_phase / delta_freq) * 1000000
                    self.derivedReference.append(derivative)
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
                    # Format derivative value with scientific notation if needed
                    if abs(angle) < 0.001 or abs(angle) > 1000:
                        anglestr = f"{angle:.2e}"
                    else:
                        digits = max(0, min(6, math.floor(6 - math.log10(abs(angle)))))
                        anglestr = f"{angle:.{digits}f}".rstrip('0').rstrip('.')
                else:
                    anglestr = "0"
                qp.drawText(3, y + 3, f"{anglestr}°/MHz")
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
            max_str = f"{maxAngle:.2e}°/MHz"
        else:
            max_str = f"{maxAngle:.6f}".rstrip('0').rstrip('.') + "°/MHz"
        if abs(minAngle) < 0.001 or abs(minAngle) > 1000:
            min_str = f"{minAngle:.2e}°/MHz"
        else:
            min_str = f"{minAngle:.6f}".rstrip('0').rstrip('.') + "°/MHz"
        qp.drawText(3, self.topMargin + 5, max_str)
        qp.drawText(3, self.dim.height + self.topMargin, min_str)

        self._set_start_stop()

        # Draw bands if required
        if self.bands.enabled:
            self.drawBands(qp, self.fstart, self.fstop)

        self.drawFrequencyTicks(qp)

        # Draw derivative data starting from second point
        if self.derivedData and len(self.data) > 1:
            pen = QtGui.QPen(Chart.color.sweep)
            pen.setWidth(self.dim.point)
            qp.setPen(pen)
            for i in range(len(self.derivedData)):
                # Use frequency from point i+1 (second point onwards)
                x = self.getXPosition(self.data[i + 1])
                deriv = self.derivedData[i]
                y = self.topMargin + int(
                    (self.maxAngle - deriv) / self.span * self.dim.height
                )
                if i == 0:
                    prev_x, prev_y = x, y
                else:
                    qp.drawLine(prev_x, prev_y, x, y)
                    prev_x, prev_y = x, y

        if self.derivedReference and len(self.reference) > 1:
            pen = QtGui.QPen(Chart.color.reference)
            pen.setWidth(self.dim.point)
            qp.setPen(pen)
            for i in range(len(self.derivedReference)):
                x = self.getXPosition(self.reference[i + 1])
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
        if d in self.data and len(self.data) > 1:
            idx = self.data.index(d)
            # First point has no derivative (need two points)
            if idx == 0:
                return self.topMargin + self.dim.height // 2
            # Use derivative calculated from this and previous point
            deriv_idx = idx - 1
            if deriv_idx < len(self.derivedData):
                deriv = self.derivedData[deriv_idx]
                return self.topMargin + int(
                    (self.maxAngle - deriv) / self.span * self.dim.height
                )
        elif d in self.reference and len(self.reference) > 1:
            idx = self.reference.index(d)
            if idx == 0:
                return self.topMargin + self.dim.height // 2
            deriv_idx = idx - 1
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
