"""Test-suite guard: the API suite exercises the deterministic dummy provider
by default so runs are hermetic and free. The live-model smoke test is
opt-in only: `MRPROF_LIVE_SMOKE=1 pytest tests/test_live_smoke.py -q`.
"""

import os

if os.environ.get("MRPROF_LIVE_SMOKE") != "1":
    os.environ["LLM_PROVIDER"] = "dummy"
