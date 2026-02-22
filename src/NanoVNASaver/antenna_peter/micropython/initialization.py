import time

from machine import I2C, Pin

pin_led = Pin("LED", Pin.OUT, value=0)
TX_GND_input_pin = Pin("GPIO21", Pin.IN)
K1_UHF_out_pin = Pin("GPIO12", Pin.OUT, value=0)
K2_ATTENUATION_out_pin = Pin("GPIO11", Pin.OUT, value=0)
K3_VNA_out_pin = Pin("GPIO10", Pin.OUT, value=0)
K4_50_OHM_out_pin = Pin("GPIO9", Pin.OUT, value=0)
K5_FREQ_UP_center_minus_out_pin = Pin("GPIO8", Pin.OUT, value=0)
led_enable_pin_out = Pin("GPIO6", Pin.OUT, value=1)
TX_INH_out_pin = Pin("GPIO15", Pin.OUT, value=0)
TX_INH_switch_input_pin = Pin("GPIO14", Pin.IN)

power_servo_magnetometer_out_pin = Pin("GPIO7", Pin.OUT, value=0)


i2c = I2C(1, sda=Pin("GPIO18"), scl=Pin("GPIO19"), freq=10000)
bmm350 = BMM350(i2c)  # noqa: F821


OK_STRING = "BEGIN[[exec: OK=]]END"

# K2_ATTENUATION_out_pin.value(1)
# K3_VNA_out_pin.value(1)


"""

falls attenuation (ckeckbox) sendeleistung reduzieren beim senden
if not TX_GND_input_pin: # radio moechte senden

    K2_ATTENUATION_out_pin.value(True)
    time.sleep(0.01)
    TX_INH_out_pin.value(False) # TX sperre aufheben


"""

# def pulse(direction_up:bool, duration_s: float) -> None:
#     K5_FREQ_UP_center_minus_out_pin.value(direction_up)
#     led_enable_pin_out.value(1)
#     time.sleep(duration_s)
#     led_enable_pin_out.value(0)
#     print(OK_STRING)

# def run(direction_up: bool, on: bool) -> None:
#     K5_FREQ_UP_center_minus_out_pin.value(direction_up)
#     led_enable_pin_out.value(on)
#     print(OK_STRING)


def get_tx_aktiv() -> int:
    return not TX_GND_input_pin.value()


def get_tx_inhibit_switch() -> bool:
    print(f"BEGIN[[tx_inhibit_switch={TX_INH_switch_input_pin.value()}]]END")
    print(OK_STRING)


def set_tx_sperren(sperren: bool) -> None:
    TX_INH_out_pin(sperren)


def vna_enable(enable: bool) -> None:
    if enable:
        set_tx_sperren(sperren=True)
        time.sleep(0.3)
        K2_ATTENUATION_out_pin.value(True)
        K3_VNA_out_pin.value(True)
        power_servo_magnetometer_out_pin.value(True)
        time.sleep(1.5)  # 0.8s is ok
        bmm350.init_sensor()
        chip_id, rev_id, err_reg = bmm350.read_chip_info()
        print(
            f"BMM350 chip_id=0x{chip_id:02X}, rev=0x{rev_id:02X}, err=0x{err_reg:02X}"
        )
    else:
        power_servo_magnetometer_out_pin.value(False)
        K2_ATTENUATION_out_pin.value(False)
        K3_VNA_out_pin.value(False)
        time.sleep(0.01)
        set_tx_sperren(sperren=False)

    print(OK_STRING)


def reference_50_ohm(enable: bool):
    K4_50_OHM_out_pin.value(enable)
    K3_VNA_out_pin.value(not enable)


def get_bmm(sample_count: int = 2):
    start_ms = time.ticks_ms()
    x, y, z, b, h = bmm350.read_data(sample_count=sample_count)
    duration_ms = time.ticks_diff(time.ticks_ms(), start_ms)
    print(
        f"X:{x:6.2f} µT Y:{y:6.2f} µT Z:{z:6.2f} µT | |B|:{b:6.2f} µT | Heading:{h:5.1f}° | sample_count={sample_count} {duration_ms}ms"
    )
    print(f"BEGIN[[heading_deg={h:5.1f}]]END")
    print(OK_STRING)


class Minmax:
    def __init__(self, do_min: bool):
        self.value = 1e12 if do_min else -1e12
        self.f = min if do_min else max

    def push(self, value: float):
        self.value = self.f(self.value, value)

    def print(self) -> str:
        return f"{self.value:>8.1f}"


class XY:
    def __init__(self, label):
        self.label = label
        self.min = Minmax(do_min=True)
        self.max = Minmax(do_min=False)

    def push(self, value: float):
        self.min.push(value)
        self.max.push(value)

    def print(self) -> str:
        return self.min.print() + "," + self.max.print()


list_xy = (XY("x"), XY("y"), XY("z"))


def calibrate_bmm(sample_count=10):
    global USER_OFFSET_X  # noqa: PLW0603
    global USER_OFFSET_Y  # noqa: PLW0603
    global USER_OFFSET_Z  # noqa: PLW0603
    USER_OFFSET_X = 0.0
    USER_OFFSET_Y = 0.0
    USER_OFFSET_Z = 0.0

    if list_xy[0].min.value > 1e10:
        # Only the first time
        power_servo_magnetometer_out_pin.value(True)
        time.sleep(1.5)  # 0.8s is ok
        bmm350.init_sensor()

    x, y, z, _b, _h = bmm350.read_data(sample_count=sample_count)
    for xy, value in zip(list_xy, (x, y, z)):  # noqa: B905
        xy.push(value)
    value_str = "   /".join([xy.print() for xy in list_xy])
    print(value_str)

    print(f"BEGIN[[xyz_min_max_str={value_str}]]END")
    print(OK_STRING)


print("BEGIN[[exec: OK=]]END")
