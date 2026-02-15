from machine import Pin, Timer
import time

# pin_led = Pin("LED", Pin.OUT, value=0)
# TX_GND_input_pin = Pin("GPIO21", Pin.IN)
# K1_UHF_out_pin = Pin("GPIO12", Pin.OUT, value=0)
# K2_ATTENUATION_out_pin = Pin("GPIO11", Pin.OUT, value=0)
# K3_VNA_out_pin = Pin("GPIO10", Pin.OUT, value=0)
# K4_50_OHM_out_pin = Pin("GPIO9", Pin.OUT, value=0)
# K5_FREQ_UP_center_minus_out_pin = Pin("GPIO8", Pin.OUT, value=0)
# motor_out_pin = Pin("GPIO6", Pin.OUT, value=0)
# TX_INH_out_pin = Pin("GPIO15", Pin.OUT, value=0)
# TX_INH_switch_input_pin = Pin("GPIO14", Pin.IN)


#K2_ATTENUATION_out_pin.value(1)
#K3_VNA_out_pin.value(1)


# led_on_out_pin = Pin("GPIO6", Pin.OUT, value=0)
# red_not_green_out_pin = Pin("GPIO8", Pin.OUT, value=0)


# uart_tx_out_pin = Pin("GPIO16", Pin.OUT, value=0)
# uart_rx_in_pin = Pin("GPIO17", Pin.IN)

# uart_tx_out_pin.value(0)


# led_off_timer = Timer()


# red_not_green_out_pin.value(0)


# def _turn_led_off(timer):
# 	led_on_out_pin.value(0)


# def start_led_rot_timer():
# 	led_on_out_pin.value(1)
# 	red_not_green_out_pin.value(1)
# 	led_off_timer.init(mode=Timer.ONE_SHOT, period=5000, callback=_turn_led_off)

# def start_led_gruen_timer():
# 	led_on_out_pin.value(1)
# 	red_not_green_out_pin.value(0)
# 	led_off_timer.init(mode=Timer.ONE_SHOT, period=5000, callback=_turn_led_off)


# # start_led_rot_timer()
# start_led_gruen_timer()

power_servo_magnetometer_out_pin = Pin("GPIO7", Pin.OUT, value=0)
power_servo_magnetometer_out_pin.value(1)



# while True:
#     time.sleep(1)