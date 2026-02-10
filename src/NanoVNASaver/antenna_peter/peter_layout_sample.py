import sys
from typing import TypeVar

from PySide6 import QtWidgets

from NanoVNASaver.antenna_peter import peter_widgets

QWidgetT = TypeVar("QWidgetT", bound=QtWidgets.QWidget)


class LayoutSample(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Layout Sample")
        self.setCentralWidget(self._build_mainframe())
        self.resize(360, 160)

    def add_row(self, widget: QWidgetT) -> QWidgetT:
        self._layout.addWidget(widget)
        return widget

    def _build_mainframe(self) -> QtWidgets.QWidget:
        mainframe = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(mainframe)

        row1 = self.add_row(peter_widgets.LineEditWidget(label= "Label",value= 42.0, unit="V"))

        self.add_row(peter_widgets.SeparatorWidget())

        row2 = self.add_row(
            peter_widgets.PushButtonWidget(label="Samibrot",value= "5",unit= "kg")
        )

        row3 =self.add_row(peter_widgets.CheckboxWidget(label="Tune automatic"))
        row4 =self.add_row(peter_widgets.ValueWidget(label="RSSI", value="5 dbm"))

        return mainframe


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    window = LayoutSample()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
