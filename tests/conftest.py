import os
import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("NINNA_INTEGRATION") == "1":
        return
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(
                pytest.mark.skip(reason="Set NINNA_INTEGRATION=1; real Docker integration tests")
            )
