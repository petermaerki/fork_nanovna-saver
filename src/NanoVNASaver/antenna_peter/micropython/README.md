```bash
.\.venv\Scripts\activate
mpremote run src/antenna/micropython/initialization.py
mpremote resume exec "pulse(True, 1.0)"
```