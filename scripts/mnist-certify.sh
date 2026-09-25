#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Development regression suite, outside the production API and MCP catalog.
NINNA_INTEGRATION=1 exec poetry run pytest tests/integration/test_mnist.py "$@"
