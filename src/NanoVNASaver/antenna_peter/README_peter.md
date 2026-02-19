

# Gui draft
DONE Tune checkbox
DONE VNA enable, TX inhibit checkbox

Tune heading checkbox
Tune heading target textfeld, button set
Tune heading current textfeld
Tune heading servo_h textfeld, button set

Frequency enable checkbox
Frequency Offset textfeld mit button set
Frequency auto get from TX checkbox
Frequency TX textfeld mit button set
Frequency target textfeld
Frequency current textfeld
Frequency servo_f textfeld button set


Impedance enable checkbox
Impedance target textfeld mit button set
Impedance current textfeld
Impedance servo_z textfeld button set

# Servo Ansteuerung

- f, mehrere Umdrehungen wie gehabt
- heading: float, kein rundherum

# States

```mermaid
stateDiagram-v2
	[*] --> enable_tx
	enable_tx: 
	inhibit_tx: 

    enable_tx --> inhibit_tx: checkbox
    inhibit_tx --> enable_tx: checkbox
```

* enable_tx

  * inhibit_tx=False,VNAenable=False, servo_power=True.

* inhibit_tx

  * inhibit_tx=True,VNAenable=True, servo_power=False.



```mermaid
stateDiagram-v2
	tuning: tuning - inhibit_tx=True. Fancy logic for heading frequency and impedance
    idle: idle - inhibit_tx=False. We might need to tune
    idle --> tuning: User checks 'auto'
    tuning --> idle: error
    tuning --> idle: tuninig ok
    tuning --> idle: User unchecks 'auto'
```

* idle entry action: State `enable_tx`
* tuning entry action: State `inhibit_tx`

```mermaid
stateDiagram-v2
    results_ready: results_ready
    sweeping: sweeping
    results_outdated: results_outdated
    results_outdated --> sweeping: sweep()
    sweeping --> results_ready: sweepFinished_peter_antenna
    results_ready --> results_outdated: servo z oder f fahren
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
