import util_iteration_regula_falsi
import math

from NanoVNASaver.antenna_peter import statemachine_tuner

"""
  >>> iter = iteration(ySoll=1.0, yToleranz=0.01, xMin=4000, xMax=60000, iMax=20)
  >>> x = iter.startX()
  >>> x
  32000
  >>> iter.weiter()
  True
  >>> x = int(iter.naechstesX(x, 2.063439))
  >>> x
  22760
  >>> x = int(iter.naechstesX(x, 1.454376))
  >>> x
  16569
  
"""

impedanz_target_ohm = 50.0


def dummy_messung_impedanz_ohm(servo_z_target_ta: float):
    return 1000.0 * servo_z_target_ta + math.sin(servo_z_target_ta)


iter = util_iteration_regula_falsi.iteration(
    ySoll=impedanz_target_ohm,
    yToleranz=4.0,
    xMin=statemachine_tuner.IMPEDANCE_TARGET_TA_MIN,
    xMax=statemachine_tuner.IMPEDANCE_TARGET_TA_MAX,
    iMax=20,
    iPlus=2
)


# start mit preset wert
servo_z_target_ta = 0.1
iteration = 0

while True:
    iteration += 1
    impedanz_ohm = dummy_messung_impedanz_ohm(
        servo_z_target_ta=servo_z_target_ta
    )
    print(f"{iteration=}, {impedanz_ohm=} bei {servo_z_target_ta=}")
    #iter.write_to_print()
    servo_z_target_ta = iter.naechstesX(x=servo_z_target_ta, y=impedanz_ohm)
    weiter = iter.weiter()
    print(f'{weiter=}')
    if not weiter:
        print(f'favorit: {servo_z_target_ta=}')
        break

