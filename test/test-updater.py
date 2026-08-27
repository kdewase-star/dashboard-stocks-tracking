import importlib.util
import subprocess
import sys
import time
import types

# Prevent the updater module from installing/importing the real nse package in unit tests.
fake_nse = types.SimpleNamespace(NSE=object)
sys.modules["nse"] = fake_nse
real_run = subprocess.run
subprocess.run = lambda *args, **kwargs: None
try:
    spec = importlib.util.spec_from_file_location("updater", "/mnt/data/updater_new.py")
    updater = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updater)
finally:
    subprocess.run = real_run

def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("PASS:", label)

check("list payload parser", updater.first_mapping([{"x": 1}]) == {"x": 1})
now = time.time()
points = [
    {"t": int(now - 40 * 86400), "c": 100.0, "v": 1},
    {"t": int(now - 10 * 86400), "c": 110.0, "v": 2},
    {"t": int(now), "c": 120.0, "v": 3},
]
hist = updater.historical_fields(120.0, points)
check("1M uses actual historical close", hist["m1Price"] == 100.0)
check("1M percentage is exact", hist["m1"] == 20.0)
check("all-time uses oldest point", hist["allTimePrice"] == 100.0)
check("failed refresh preserves last value",
      updater.merge_stock({"last": 100.0, "points": points}, {"last": None})["last"] == 100.0)
score = updater.opportunity_score({
    "today": 5.0, "last": 95.0, "high": 100.0, "low": 50.0, "volume": 100000
})
check("opportunity score bounded", 0 <= score <= 100)
print("All updater unit checks passed.")
