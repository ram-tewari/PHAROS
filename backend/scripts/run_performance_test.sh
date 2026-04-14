#!/bin/bash
# Run complete performance test: populate + benchmark

echo "=========================================="
echo "PHASE 5: PERFORMANCE TESTING"
echo "=========================================="
echo ""

# Step 1: Populate database
echo "Step 1: Populating database with test data..."
python populate_test_data.py
if [ $? -ne 0 ]; then
    echo "❌ Failed to populate database"
    exit 1
fi

echo ""
echo "Step 2: Running performance benchmarks..."
python benchmark_context_assembly.py
if [ $? -ne 0 ]; then
    echo "❌ Benchmarks failed"
    exit 1
fi

echo ""
echo "✅ Performance testing complete!"
echo "📊 Check benchmark_results.json for detailed results"
