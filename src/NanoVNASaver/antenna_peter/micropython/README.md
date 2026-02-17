```bash
.\.venv\Scripts\activate
mpremote run src/antenna/micropython/initialization.py
mpremote resume exec "pulse(True, 1.0)"
```


Run code on micropython

```bash
.\.venv\Scripts\activate
mpremote run initialization_BMM350.py 
mpremote resume run initialization.py 
```
