import pathlib


DIRECTORY_CWD = pathlib.Path.cwd()
DIRECTORY_LOG = DIRECTORY_CWD / "antenna_gui_log"
DIRECTORY_LOG.mkdir(parents=True, exist_ok=True)
