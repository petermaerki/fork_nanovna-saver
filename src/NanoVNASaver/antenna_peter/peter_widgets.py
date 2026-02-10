import logging
from typing import TypeVar

from PySide6 import QtCore, QtWidgets

logger = logging.getLogger(__name__)

QWidgetLeftT = TypeVar("QWidgetLeftT", bound=QtWidgets.QWidget)
QWidgetRightT = TypeVar("QWidgetRightT", bound=QtWidgets.QWidget)

SPACING = 4
CONTENTS_MARGINS = QtCore.QMargins(0, 0, 0, 0)

class FormLayoutWidget[QWidgetLeftT, QWidgetRightT](QtWidgets.QWidget):
    def __init__(
        self,
        left: QWidgetLeftT,
        right: QWidgetRightT | None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(CONTENTS_MARGINS)
        layout.setSpacing(SPACING)

        if isinstance(left, QtWidgets.QWidget):
            layout.addWidget(left)
            self.right_widget = left
        else:
            if isinstance(left, QtWidgets.QHBoxLayout):
                self.right_widget = QtWidgets.QWidget()
                self.right_widget.setLayout(left)
                layout.addWidget(self.right_widget)
            else:
                logger.warning(f"Not a widget left: {left}")

        if isinstance(right, QtWidgets.QWidget):
            layout.addWidget(right)
            self.right_widet = right
        else:
            if isinstance(right, QtWidgets.QHBoxLayout):
                self.right_widget = QtWidgets.QWidget()
                self.right_widget.setLayout(right)
                layout.addWidget(self.right_widget)
            else:
                logger.warning(f"Not a widget right: {right}")


class SeparatorWidget(QtWidgets.QFrame):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)


class LineEditWidget(QtWidgets.QWidget):
    def __init__(
        self,
        label: str,
        value: float,
        unit: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(CONTENTS_MARGINS)
        layout.setSpacing(SPACING)

        self.label = QtWidgets.QLabel(label)
        self.entry = QtWidgets.QDoubleSpinBox()
        self.entry.setDecimals(3)
        self.entry.setRange(-1e9, 1e9)
        self.entry.setFixedHeight(20)
        self.entry.setValue(value)
        self.unit = QtWidgets.QLabel(unit)

        self.entry.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.entry.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        layout.addWidget(self.label)
        layout.addWidget(self.entry, 1)
        layout.addWidget(self.unit)


class PowerspinWidget(QtWidgets.QWidget):
    def __init__(
        self,
        label: str,
        value: int,
        min_value: int,
        max_value: int,
        unit: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(CONTENTS_MARGINS)
        layout.setSpacing(SPACING)

        self.label = QtWidgets.QLabel(label)

        self.power_spin = QtWidgets.QSpinBox()
        self.power_spin.setRange(min_value, max_value)
        self.power_spin.setValue(value)
        self.power_spin.setFixedHeight(20)
        self.power_spin.setMinimumWidth(60)
        self.power_spin.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.power_spin.setButtonSymbols(
            QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
        )

        self.unit = QtWidgets.QLabel(unit)

        self.power_spin.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.power_spin.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        layout.addWidget(self.label)
        layout.addWidget(self.power_spin, 1)
        layout.addWidget(self.unit)


class ValueWidget(QtWidgets.QWidget):
    def __init__(
        self,
        label: str,
        value: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(CONTENTS_MARGINS)
        layout.setSpacing(SPACING)

        self.label = QtWidgets.QLabel(label)
        self.value = QtWidgets.QLabel(value)

        self.value.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        layout.addWidget(self.label,1)
        layout.addWidget(self.value)


class CheckboxWidget(QtWidgets.QWidget):
    def __init__(
        self,
        label: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(CONTENTS_MARGINS)
        layout.setSpacing(SPACING)

        self.label = QtWidgets.QLabel(label)
        self.checkbox = QtWidgets.QCheckBox()

        layout.addWidget(self.label, 1)
        layout.addWidget(self.checkbox)



class PushButtonWidget(QtWidgets.QWidget):
    def __init__(
        self,
        label: str,
        value: str,
        unit: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(CONTENTS_MARGINS)
        layout.setSpacing(SPACING)

        self.label = QtWidgets.QLabel(label)
        self.value = QtWidgets.QLabel(value)
        self.unit = QtWidgets.QLabel(unit)
        self.button = QtWidgets.QPushButton("set")

        self.value.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        self.button.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.button.setFixedWidth(40)
        self.button.setFixedHeight(20)
        self.button.clicked.connect(self._open_value_dialog)
        layout.addWidget(self.label)
        layout.addWidget(self.value, 10)
        layout.addWidget(self.unit)
        layout.addWidget(self.button)

    def _open_value_dialog(self) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Set Value")
        dialog.setModal(True)

        layout = QtWidgets.QVBoxLayout(dialog)

        actual_layout = QtWidgets.QHBoxLayout()
        actual_layout.addWidget(QtWidgets.QLabel("actual value"))
        actual_layout.addWidget(QtWidgets.QLabel(self.value.text()))
        layout.addLayout(actual_layout)

        new_layout = QtWidgets.QHBoxLayout()
        new_layout.addWidget(QtWidgets.QLabel("new value"))
        new_value = QtWidgets.QDoubleSpinBox()
        new_value.setDecimals(3)
        new_value.setRange(-1e9, 1e9)
        new_value.setValue(self._parse_value(self.value.text()))
        new_layout.addWidget(new_value)
        layout.addLayout(new_layout)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.value.setText(f"{new_value.value():.3f}")

    @staticmethod
    def _parse_value(text: str) -> float:
        try:
            return float(text)
        except ValueError:
            return 0.0


