

# Gui draft
Tune checkbox
VNA enable, TX inhibit checkbox
Tune heading checkbox
Tune heading target textfeld, button set
Tune heading current textfeld
Tune heading servo_h textfeld, button set

Frequency enable checkbox
Frequency Offset textfeld mit button set
Frequency auto get from TX checkbox
Frequency TX textfeld mit button set
Frequency target textfeld
Frequency servo_f textfeld button set

Impedance enable checkbox
Impedance target textfeld mit button set
Impedance target current textfeld
Impedance servo_z textfeld button set

# Servo Ansteuerung

- f, mehrere Umdrehungen wie gehabt
- heading: float, kein rundherum

# States

```mermaid
stateDiagram-v2
	[*] --> tx_enable
	tx_enable: RED tx_enable - Switch TX inhibit_tx is off or send relay closd
	inhibit_tx: GREEN inhibit_tx

    tx_enable --> inhibit_tx: pico gpio
    inhibit_tx --> tx_enable: pico gpio
```


GREEN `inhibit_tx` substate

```mermaid
stateDiagram-v2
	tuning: tuning - Fancy logic for heading frequency and impedance
    idle: idle - We might need to tune
    idle --> tuning: User checks 'auto'
    tuning --> idle: error
    tuning --> idle: tuninig ok
    tuning --> idle: User unchecks 'auto'
```

# servo

Implementation: Blocks GUI while moveing

```mermaid
stateDiagram-v2
    moveing --> stopped: position reached
    stopped --> moveing: new position
```

<hr>


```mermaid
stateDiagram-v2
	[*] --> untuned
	tx_enable: tx_enable - Switch TX inhibit_tx is off or send relay closd
	tuning: tuning - Fancy logic for heading frequency and impedance
    untuned: untuned - We might need to tune
    tuned: tuned - All conditions in 'tuning' are ok
    untuned --> tuning: User checks 'auto'
    tuning --> tuned: All conditions ok
    tuning --> untuned: Abort for some reason
    untuned --> tx_enable: pico gpio
    tx_enable --> untuned: pico gpio
```


```mermaid
stateDiagram-v2
	tuning: tuning - Fancy logic for heading frequency and impedance
    untuned: untuned - We might need to tune
    tuned: tuned - All conditions in 'tuning' are ok
    tuned --> tuning: Check 'auto'
    untuned --> tuning: User checks 'auto'
    tuning --> tuned: All conditions ok
    tuning --> untuned: Abort for some reason
```
