#!/bin/bash
# HEI-agent Benchmark Runner
# Usage: bash tests/run_benchmark.sh [metric|all]
#   all - run all 5 metrics (default)
#   rag - RAG Recall only
#   tool - Tool Accuracy only
#   latency - E2E Latency only
#   memory - Hybrid Search Recall only
#   confirm - Confirmation Mechanism only

# Must be run from project root
set -euo pipefail
cd "$(dirname "$0")/.."

# Activate venv if exists
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

METRIC="${1:-all}"
RESULTS_DIR="tests/results"
mkdir -p "$RESULTS_DIR"

echo "🔬 HEI-agent Benchmark Runner"
echo "=============================="
echo "Metric: $METRIC"
echo ""

python tests/benchmark_runner.py "$METRIC"

echo ""
echo "✅ Done! Report: $RESULTS_DIR/report.md"
