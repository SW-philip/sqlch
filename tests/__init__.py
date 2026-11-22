import os
import tempfile

# The daemon code under test writes small state files (queue.json, ...) into
# data_dir(); keep every test run out of the real ~/.local/share/sqlch.
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="sqlch-tests-")
