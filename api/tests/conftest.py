"""Test-suite guard: the API suite always exercises the deterministic dummy
provider. Live-model runs are manual acceptance only (same env, real key),
never part of `pytest`.
"""

import os

os.environ["LLM_PROVIDER"] = "dummy"
for _key in ("LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY"):
    os.environ.pop(_key, None)
