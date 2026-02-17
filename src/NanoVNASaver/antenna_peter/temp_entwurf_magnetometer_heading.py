import math
import time

from machine import I2C, Pin

SDA_PIN = "GPIO18"
SCL_PIN = "GPIO19"

power_servo_magnetometer_out_pin = Pin("GPIO7", Pin.OUT, value=0)
power_servo_magnetometer_out_pin.value(1)

# --- USER-OFFSETS (in µT) ---
# Messung: Offset auf 0, zwei extremwerte messen, Mittelwert bilden und als USER_OFFSET verwenden
USER_OFFSET_X = (41.4 + (11.39)) / 2.0
USER_OFFSET_Y = (-12.34 + (-42.7)) / 2.0
USER_OFFSET_Z = (-21.4 + (11.0)) / 2.0

sda_num = int(SDA_PIN.replace("GPIO", ""))
scl_num = int(SCL_PIN.replace("GPIO", ""))
i2c = I2C(1, sda=Pin(sda_num), scl=Pin(scl_num), freq=10000)

BMM350_I2C_ADDR = 0x14
BMM350_CHIP_ID = 0x33
BMM350_DUMMY_BYTES = 2
BMM350_OTP_DATA_LENGTH = 32

BMM350_REG_CHIP_ID = 0x00
BMM350_REG_REV_ID = 0x01
BMM350_REG_ERR_REG = 0x02
BMM350_REG_INT_CTRL = 0x2E
BMM350_REG_PMU_CMD = 0x06
BMM350_REG_INT_STATUS = 0x30
BMM350_REG_MAG_X_XLSB = 0x31
BMM350_REG_OTP_CMD_REG = 0x50
BMM350_REG_OTP_DATA_MSB_REG = 0x52
BMM350_REG_OTP_DATA_LSB_REG = 0x53
BMM350_REG_OTP_STATUS_REG = 0x55
BMM350_REG_CMD = 0x7E

BMM350_DRDY_DATA_REG_MSK = 0x04
BMM350_DRDY_DATA_REG_POS = 2

BMM350_CMD_SOFTRESET = 0xB6
BMM350_OTP_CMD_DIR_READ = 0x20
BMM350_OTP_CMD_PWR_OFF_OTP = 0x80
BMM350_OTP_WORD_ADDR_MSK = 0x1F

BMM350_OTP_STATUS_ERROR_MSK = 0xE0
BMM350_OTP_STATUS_NO_ERROR = 0x00
BMM350_OTP_STATUS_CMD_DONE = 0x01

BMM350_PMU_CMD_SUS = 0x00
BMM350_PMU_CMD_NM = 0x01
BMM350_PMU_CMD_FGR = 0x05
BMM350_PMU_CMD_BR = 0x07

BMM350_BR_DELAY = 0.014
BMM350_FGR_DELAY = 0.018
BMM350_SOFT_RESET_DELAY = 0.01

BMM350_LSB_MASK = 0x00FF
BMM350_MSB_MASK = 0xFF00

BMM350_SIGNED_8_BIT = 8
BMM350_SIGNED_12_BIT = 12
BMM350_SIGNED_16_BIT = 16
BMM350_SIGNED_21_BIT = 21
BMM350_SIGNED_24_BIT = 24

BMM350_TEMP_OFF_SENS = 0x0D
BMM350_MAG_OFFSET_X = 0x0E
BMM350_MAG_OFFSET_Y = 0x0F
BMM350_MAG_OFFSET_Z = 0x10
BMM350_MAG_SENS_X = 0x10
BMM350_MAG_SENS_Y = 0x11
BMM350_MAG_SENS_Z = 0x11
BMM350_MAG_TCO_X = 0x12
BMM350_MAG_TCO_Y = 0x13
BMM350_MAG_TCO_Z = 0x14
BMM350_MAG_TCS_X = 0x12
BMM350_MAG_TCS_Y = 0x13
BMM350_MAG_TCS_Z = 0x14
BMM350_MAG_DUT_T_0 = 0x18
BMM350_CROSS_X_Y = 0x15
BMM350_CROSS_Y_X = 0x15
BMM350_CROSS_Z_X = 0x16
BMM350_CROSS_Z_Y = 0x16

BMM350_SENS_CORR_Y = 0.01
BMM350_TCS_CORR_Z = 0.0001


class BMM350:
    def __init__(self, i2c_bus, address=BMM350_I2C_ADDR):
        self.i2c = i2c_bus
        self.address = address
        self.otp_data = [0] * BMM350_OTP_DATA_LENGTH
        self.mag_comp = {
            "dut_offset_coef": {
                "t_offs": 0.0,
                "offset_x": 0.0,
                "offset_y": 0.0,
                "offset_z": 0.0,
            },
            "dut_sensit_coef": {
                "t_sens": 0.0,
                "sens_x": 0.0,
                "sens_y": 0.0,
                "sens_z": 0.0,
            },
            "dut_tco": {"tco_x": 0.0, "tco_y": 0.0, "tco_z": 0.0},
            "dut_tcs": {"tcs_x": 0.0, "tcs_y": 0.0, "tcs_z": 0.0},
            "dut_t0": 0.0,
            "cross_axis": {
                "cross_x_y": 0.0,
                "cross_y_x": 0.0,
                "cross_z_x": 0.0,
                "cross_z_y": 0.0,
            },
        }
        self.init_sensor()

    def _write_reg(self, reg, value):
        self.i2c.writeto_mem(self.address, reg, bytes([value]))

    def _read_regs(self, reg, length):
        data = self.i2c.readfrom_mem(
            self.address, reg, length + BMM350_DUMMY_BYTES
        )
        return data[BMM350_DUMMY_BYTES:]

    def _read_u8(self, reg):
        return self._read_regs(reg, 1)[0]

    def init_sensor(self):
        try:
            self._write_reg(BMM350_REG_CMD, BMM350_CMD_SOFTRESET)
            time.sleep(BMM350_SOFT_RESET_DELAY)
            self._read_otp_all()
            self._update_mag_off_sens()
            self._write_reg(BMM350_REG_OTP_CMD_REG, BMM350_OTP_CMD_PWR_OFF_OTP)
            self._write_reg(BMM350_REG_PMU_CMD, BMM350_PMU_CMD_SUS)
            time.sleep(0.003)
            self._write_reg(BMM350_REG_PMU_CMD, BMM350_PMU_CMD_BR)
            time.sleep(BMM350_BR_DELAY)
            self._write_reg(BMM350_REG_PMU_CMD, BMM350_PMU_CMD_FGR)
            time.sleep(BMM350_FGR_DELAY)
            self._write_reg(BMM350_REG_PMU_CMD, BMM350_PMU_CMD_NM)
            time.sleep(0.02)
            self.enable_drdy_data_reg(True)
        except:
            print("Sensor-Initialisierung fehlgeschlagen!")

    def enable_drdy_data_reg(self, enable):
        reg = self._read_u8(BMM350_REG_INT_CTRL)
        if enable:
            reg |= 0x80
        else:
            reg &= 0x7F
        self._write_reg(BMM350_REG_INT_CTRL, reg)

    def read_chip_info(self):
        chip_id = self._read_u8(BMM350_REG_CHIP_ID)
        rev_id = self._read_u8(BMM350_REG_REV_ID)
        err_reg = self._read_u8(BMM350_REG_ERR_REG)
        return chip_id, rev_id, err_reg

    def data_ready(self):
        int_status = self._read_u8(BMM350_REG_INT_STATUS)
        drdy = (
            int_status & BMM350_DRDY_DATA_REG_MSK
        ) >> BMM350_DRDY_DATA_REG_POS
        return drdy == 1, int_status

    def _to_signed24(self, value):
        if value & 0x800000:
            return value - 0x1000000
        return value

    def _fix_sign(self, value, number_of_bits):
        power = 0
        if number_of_bits == BMM350_SIGNED_8_BIT:
            power = 128
        elif number_of_bits == BMM350_SIGNED_12_BIT:
            power = 2048
        elif number_of_bits == BMM350_SIGNED_16_BIT:
            power = 32768
        elif number_of_bits == BMM350_SIGNED_21_BIT:
            power = 1048576
        elif number_of_bits == BMM350_SIGNED_24_BIT:
            power = 8388608
        if value >= power:
            value = value - (power * 2)
        return value

    def _read_otp_word(self, addr):
        otp_cmd = BMM350_OTP_CMD_DIR_READ | (addr & BMM350_OTP_WORD_ADDR_MSK)
        self._write_reg(BMM350_REG_OTP_CMD_REG, otp_cmd)
        while True:
            time.sleep(0.0003)
            otp_status = self._read_u8(BMM350_REG_OTP_STATUS_REG)
            otp_err = otp_status & BMM350_OTP_STATUS_ERROR_MSK
            if otp_err != BMM350_OTP_STATUS_NO_ERROR:
                return None
            if otp_status & BMM350_OTP_STATUS_CMD_DONE:
                break
        msb = self._read_u8(BMM350_REG_OTP_DATA_MSB_REG)
        lsb = self._read_u8(BMM350_REG_OTP_DATA_LSB_REG)
        return ((msb << 8) | lsb) & 0xFFFF

    def _read_otp_all(self):
        for idx in range(BMM350_OTP_DATA_LENGTH):
            word = self._read_otp_word(idx)
            if word is None:
                break
            self.otp_data[idx] = word

    def _update_mag_off_sens(self):
        off_x_lsb_msb = self.otp_data[BMM350_MAG_OFFSET_X] & 0x0FFF
        off_y_lsb_msb = ((self.otp_data[BMM350_MAG_OFFSET_X] & 0xF000) >> 4) + (
            self.otp_data[BMM350_MAG_OFFSET_Y] & BMM350_LSB_MASK
        )
        off_z_lsb_msb = (self.otp_data[BMM350_MAG_OFFSET_Y] & 0x0F00) + (
            self.otp_data[BMM350_MAG_OFFSET_Z] & BMM350_LSB_MASK
        )
        t_off = self.otp_data[BMM350_TEMP_OFF_SENS] & BMM350_LSB_MASK

        self.mag_comp["dut_offset_coef"]["offset_x"] = self._fix_sign(
            off_x_lsb_msb, BMM350_SIGNED_12_BIT
        )
        self.mag_comp["dut_offset_coef"]["offset_y"] = self._fix_sign(
            off_y_lsb_msb, BMM350_SIGNED_12_BIT
        )
        self.mag_comp["dut_offset_coef"]["offset_z"] = self._fix_sign(
            off_z_lsb_msb, BMM350_SIGNED_12_BIT
        )
        self.mag_comp["dut_offset_coef"]["t_offs"] = (
            self._fix_sign(t_off, BMM350_SIGNED_8_BIT) / 5.0
        )

        sens_x = (self.otp_data[BMM350_MAG_SENS_X] & BMM350_MSB_MASK) >> 8
        sens_y = self.otp_data[BMM350_MAG_SENS_Y] & BMM350_LSB_MASK
        sens_z = (self.otp_data[BMM350_MAG_SENS_Z] & BMM350_MSB_MASK) >> 8
        t_sens = (self.otp_data[BMM350_TEMP_OFF_SENS] & BMM350_MSB_MASK) >> 8

        self.mag_comp["dut_sensit_coef"]["sens_x"] = (
            self._fix_sign(sens_x, BMM350_SIGNED_8_BIT) / 256.0
        )
        self.mag_comp["dut_sensit_coef"]["sens_y"] = (
            self._fix_sign(sens_y, BMM350_SIGNED_8_BIT) / 256.0
        ) + BMM350_SENS_CORR_Y
        self.mag_comp["dut_sensit_coef"]["sens_z"] = (
            self._fix_sign(sens_z, BMM350_SIGNED_8_BIT) / 256.0
        )
        self.mag_comp["dut_sensit_coef"]["t_sens"] = (
            self._fix_sign(t_sens, BMM350_SIGNED_8_BIT) / 512.0
        )

        tco_x = self.otp_data[BMM350_MAG_TCO_X] & BMM350_LSB_MASK
        tco_y = self.otp_data[BMM350_MAG_TCO_Y] & BMM350_LSB_MASK
        tco_z = self.otp_data[BMM350_MAG_TCO_Z] & BMM350_LSB_MASK

        self.mag_comp["dut_tco"]["tco_x"] = (
            self._fix_sign(tco_x, BMM350_SIGNED_8_BIT) / 32.0
        )
        self.mag_comp["dut_tco"]["tco_y"] = (
            self._fix_sign(tco_y, BMM350_SIGNED_8_BIT) / 32.0
        )
        self.mag_comp["dut_tco"]["tco_z"] = (
            self._fix_sign(tco_z, BMM350_SIGNED_8_BIT) / 32.0
        )

        tcs_x = (self.otp_data[BMM350_MAG_TCS_X] & BMM350_MSB_MASK) >> 8
        tcs_y = (self.otp_data[BMM350_MAG_TCS_Y] & BMM350_MSB_MASK) >> 8
        tcs_z = (self.otp_data[BMM350_MAG_TCS_Z] & BMM350_MSB_MASK) >> 8

        self.mag_comp["dut_tcs"]["tcs_x"] = (
            self._fix_sign(tcs_x, BMM350_SIGNED_8_BIT) / 16384.0
        )
        self.mag_comp["dut_tcs"]["tcs_y"] = (
            self._fix_sign(tcs_y, BMM350_SIGNED_8_BIT) / 16384.0
        )
        self.mag_comp["dut_tcs"]["tcs_z"] = (
            self._fix_sign(tcs_z, BMM350_SIGNED_8_BIT) / 16384.0
        ) - BMM350_TCS_CORR_Z

        self.mag_comp["dut_t0"] = (
            self._fix_sign(
                self.otp_data[BMM350_MAG_DUT_T_0], BMM350_SIGNED_16_BIT
            )
            / 512.0
        ) + 23.0

        cross_x_y = self.otp_data[BMM350_CROSS_X_Y] & BMM350_LSB_MASK
        cross_y_x = (self.otp_data[BMM350_CROSS_Y_X] & BMM350_MSB_MASK) >> 8
        cross_z_x = self.otp_data[BMM350_CROSS_Z_X] & BMM350_LSB_MASK
        cross_z_y = (self.otp_data[BMM350_CROSS_Z_Y] & BMM350_MSB_MASK) >> 8

        self.mag_comp["cross_axis"]["cross_x_y"] = (
            self._fix_sign(cross_x_y, BMM350_SIGNED_8_BIT) / 800.0
        )
        self.mag_comp["cross_axis"]["cross_y_x"] = (
            self._fix_sign(cross_y_x, BMM350_SIGNED_8_BIT) / 800.0
        )
        self.mag_comp["cross_axis"]["cross_z_x"] = (
            self._fix_sign(cross_z_x, BMM350_SIGNED_8_BIT) / 800.0
        )
        self.mag_comp["cross_axis"]["cross_z_y"] = (
            self._fix_sign(cross_z_y, BMM350_SIGNED_8_BIT) / 800.0
        )

    def _update_default_coefficients(self):
        bxy_sens = 14.55
        bz_sens = 9.0
        temp_sens = 0.00204
        ina_xy_gain_trgt = 19.46
        ina_z_gain_trgt = 31.0
        adc_gain = 1 / 1.5
        lut_gain = 0.714607238769531
        power = 1000000.0 / 1048576.0
        lsb_to_ut_degc = [0.0, 0.0, 0.0, 0.0]
        lsb_to_ut_degc[0] = power / (
            bxy_sens * ina_xy_gain_trgt * adc_gain * lut_gain
        )
        lsb_to_ut_degc[1] = power / (
            bxy_sens * ina_xy_gain_trgt * adc_gain * lut_gain
        )
        lsb_to_ut_degc[2] = power / (
            bz_sens * ina_z_gain_trgt * adc_gain * lut_gain
        )
        lsb_to_ut_degc[3] = 1 / (temp_sens * adc_gain * lut_gain * 1048576)
        return lsb_to_ut_degc

    def _read_raw_mag_temp(self):
        data = self._read_regs(BMM350_REG_MAG_X_XLSB, 12)
        raw_mag_x = data[0] | (data[1] << 8) | (data[2] << 16)
        raw_mag_y = data[3] | (data[4] << 8) | (data[5] << 16)
        raw_mag_z = data[6] | (data[7] << 8) | (data[8] << 16)
        raw_temp = data[9] | (data[10] << 8) | (data[11] << 16)
        raw_mag_x = self._fix_sign(raw_mag_x, BMM350_SIGNED_24_BIT)
        raw_mag_y = self._fix_sign(raw_mag_y, BMM350_SIGNED_24_BIT)
        raw_mag_z = self._fix_sign(raw_mag_z, BMM350_SIGNED_24_BIT)
        raw_temp = self._fix_sign(raw_temp, BMM350_SIGNED_24_BIT)
        return raw_mag_x, raw_mag_y, raw_mag_z, raw_temp

    def _get_compensated_data(self):
        raw_x, raw_y, raw_z, raw_t = self._read_raw_mag_temp()
        lsb_to_ut_degc = self._update_default_coefficients()
        out_data = [0.0, 0.0, 0.0, 0.0]
        out_data[0] = raw_x * lsb_to_ut_degc[0]
        out_data[1] = raw_y * lsb_to_ut_degc[1]
        out_data[2] = raw_z * lsb_to_ut_degc[2]
        out_data[3] = raw_t * lsb_to_ut_degc[3]

        if out_data[3] > 0.0:
            out_data[3] = out_data[3] - (1 * 25.49)
        elif out_data[3] < 0.0:
            out_data[3] = out_data[3] - (-1 * 25.49)

        out_data[3] = (
            1 + self.mag_comp["dut_sensit_coef"]["t_sens"]
        ) * out_data[3] + self.mag_comp["dut_offset_coef"]["t_offs"]

        dut_offset_coef = [
            self.mag_comp["dut_offset_coef"]["offset_x"],
            self.mag_comp["dut_offset_coef"]["offset_y"],
            self.mag_comp["dut_offset_coef"]["offset_z"],
        ]
        dut_sensit_coef = [
            self.mag_comp["dut_sensit_coef"]["sens_x"],
            self.mag_comp["dut_sensit_coef"]["sens_y"],
            self.mag_comp["dut_sensit_coef"]["sens_z"],
        ]
        dut_tco = [
            self.mag_comp["dut_tco"]["tco_x"],
            self.mag_comp["dut_tco"]["tco_y"],
            self.mag_comp["dut_tco"]["tco_z"],
        ]
        dut_tcs = [
            self.mag_comp["dut_tcs"]["tcs_x"],
            self.mag_comp["dut_tcs"]["tcs_y"],
            self.mag_comp["dut_tcs"]["tcs_z"],
        ]

        for idx in range(3):
            out_data[idx] *= 1 + dut_sensit_coef[idx]
            out_data[idx] += dut_offset_coef[idx]
            out_data[idx] += dut_tco[idx] * (
                out_data[3] - self.mag_comp["dut_t0"]
            )
            out_data[idx] /= 1 + dut_tcs[idx] * (
                out_data[3] - self.mag_comp["dut_t0"]
            )

        cross_x_y = self.mag_comp["cross_axis"]["cross_x_y"]
        cross_y_x = self.mag_comp["cross_axis"]["cross_y_x"]
        cross_z_x = self.mag_comp["cross_axis"]["cross_z_x"]
        cross_z_y = self.mag_comp["cross_axis"]["cross_z_y"]

        cr_ax_comp_x = (out_data[0] - cross_x_y * out_data[1]) / (
            1 - cross_y_x * cross_x_y
        )
        cr_ax_comp_y = (out_data[1] - cross_y_x * out_data[0]) / (
            1 - cross_y_x * cross_x_y
        )
        cr_ax_comp_z = out_data[2] + (
            out_data[0] * (cross_y_x * cross_z_y - cross_z_x)
            - out_data[1] * (cross_z_y - cross_x_y * cross_z_x)
        ) / (1 - cross_y_x * cross_x_y)

        return cr_ax_comp_x, cr_ax_comp_y, cr_ax_comp_z, out_data[3]

    def read_data(self):
        x, y, z, _temp = self._get_compensated_data()
        x -= USER_OFFSET_X
        y -= USER_OFFSET_Y
        z -= USER_OFFSET_Z

        # Berechnung Betrag |B| und Heading
        b_total = math.sqrt(x**2 + y**2 + z**2)
        heading = -math.degrees(math.atan2(y, x)) + 360.0 + 90.0
        heading = heading % 360.0

        return x, y, z, b_total, heading


devices = i2c.scan()
print("I2C scan:", [hex(addr) for addr in devices])
if BMM350_I2C_ADDR not in devices:
    print("Warnung: BMM350 nicht unter 0x14 gefunden.")

sensor = BMM350(i2c)

chip_id, rev_id, err_reg = sensor.read_chip_info()
print(
    f"BMM350 chip_id=0x{chip_id:02X} (soll 0x{BMM350_CHIP_ID:02X} sein), rev=0x{rev_id:02X}, err=0x{err_reg:02X}"
)

print(f"Monitoring BMM350 auf {SDA_PIN}/{SCL_PIN}...")
print(
    f"User-Offset (uT): X={USER_OFFSET_X:.2f} Y={USER_OFFSET_Y:.2f} Z={USER_OFFSET_Z:.2f}"
)

while True:
    try:
        drdy, int_status = sensor.data_ready()
        if not drdy:
            print(f"DRDY=0 (INT_STATUS=0x{int_status:02X})")
            time.sleep(0.2)
            continue
        x, y, z, b, h = sensor.read_data()
        print(
            f"X:{x:6.2f} µT Y:{y:6.2f} µT Z:{z:6.2f} µT | |B|:{b:6.2f} µT | Heading:{h:5.1f}° | INT_STATUS:0x{int_status:02X}"
        )
    except Exception as e:
        print(f"Fehler: {e}")

    time.sleep(01.0)
