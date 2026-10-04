import os
import pytest


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "legacy_api" in item.keywords and os.environ.get("NINNA_LEGACY_API") != "1":
            item.add_marker(
                pytest.mark.skip(
                    reason="Historical v1 API suite; run against a v1 server with NINNA_LEGACY_API=1"
                )
            )
        elif "integration" in item.keywords and os.environ.get("NINNA_INTEGRATION") != "1":
            item.add_marker(
                pytest.mark.skip(reason="Set NINNA_INTEGRATION=1; real Docker integration tests")
            )
