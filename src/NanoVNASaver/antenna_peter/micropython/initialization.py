from machine import Pin
import time

pin_led = Pin("LED", Pin.OUT, value=0)
TX_GND_input_pin = Pin("GPIO21", Pin.IN)
K1_UHF_out_pin = Pin("GPIO12", Pin.OUT, value=0)
K2_ATTENUATION_out_pin = Pin("GPIO11", Pin.OUT, value=0)
K3_VNA_out_pin = Pin("GPIO10", Pin.OUT, value=0)
K4_50_OHM_out_pin = Pin("GPIO9", Pin.OUT, value=0)
K5_FREQ_UP_center_minus_out_pin = Pin("GPIO8", Pin.OUT, value=0)
motor_out_pin = Pin("GPIO6", Pin.OUT, value=0)
TX_INH_out_pin = Pin("GPIO15", Pin.OUT, value=0)


#K2_ATTENUATION_out_pin.value(1)
#K3_VNA_out_pin.value(1)


'''

falls attenuation (ckeckbox) sendeleistung reduzieren beim senden
if not TX_GND_input_pin: # radio moechte senden
    
    K2_ATTENUATION_out_pin.value(True)
    time.sleep(0.01)
    TX_INH_out_pin.value(False) # TX sperre aufheben


'''



def pulse(direction_up:bool, duration_s: float) -> None:
    K5_FREQ_UP_center_minus_out_pin.value(direction_up)
    motor_out_pin.value(1)
    time.sleep(duration_s)
    motor_out_pin.value(0)

def run(direction_up: bool, on: bool) -> None:
    K5_FREQ_UP_center_minus_out_pin.value(direction_up)
    motor_out_pin.value(on)

def get_tx_aktiv():
    return not TX_GND_input_pin.value()

def set_tx_sperren(sperren: bool):
    TX_INH_out_pin(sperren)

def tune_enable(tunen: bool):
    if tunen:
        set_tx_sperren(sperren=True)
        time.sleep(0.3)
        K2_ATTENUATION_out_pin.value(True)
        K3_VNA_out_pin.value(True)
    else:
        K2_ATTENUATION_out_pin.value(False)
        K3_VNA_out_pin.value(False)
        time.sleep(0.01)
        set_tx_sperren(sperren=False)

def reference_50_ohm(enable:bool):
    K4_50_OHM_out_pin.value(enable)
    K3_VNA_out_pin.value(not enable)