import os
import tempfile

# The daemon code under test writes small state files (queue.json, ...) into
# data_dir(), and the now-playing panel reads its saved history from the cache;
# keep every test run out of the real ones.
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="sqlch-tests-")
os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="sqlch-tests-")
