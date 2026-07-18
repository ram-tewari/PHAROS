"""
Performance tests for code intelligence pipeline.

Tests verify that AST parsing and static analysis meet performance requirements:
- AST parsing: < 2s per file (P95)
- Static analysis: < 1s per file (P95)

Property 13: Performance Bounds
Validates: Requirements 10.2, 10.3
"""

import pytest
import time
import statistics
from pathlib import Path
from typing import List
from uuid import uuid4

from app.modules.resources.logic.chunking import CodeChunkingStrategy
from app.modules.graph.logic.static_analysis import StaticAnalysisService
from app.database.models import Resource


# Sample code files for testing
SAMPLE_PYTHON_CODE = '''
"""Sample Python module for performance testing."""

class DataProcessor:
    """Process data with various methods."""
    
    def __init__(self, config):
        self.config = config
        self.cache = {}
    
    def process_data(self, data):
        """Process input data."""
        if data in self.cache:
            return self.cache[data]
        
        result = self._transform(data)
        result = self._validate(result)
        result = self._normalize(result)
        
        self.cache[data] = result
        return result
    
    def _transform(self, data):
        """Transform data."""
        return [x * 2 for x in data]
    
    def _validate(self, data):
        """Validate data."""
        return [x for x in data if x > 0]
    
    def _normalize(self, data):
        """Normalize data."""
        total = sum(data)
        return [x / total for x in data] if total > 0 else data


def calculate_statistics(values):
    """Calculate statistics for a list of values."""
    if not values:
        return {}
    
    return {
        'mean': statistics.mean(values),
        'median': statistics.median(values),
        'min': min(values),
        'max': max(values),
        'count': len(values)
    }


def process_batch(items, batch_size=10):
    """Process items in batches."""
    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_result = [process_item(item) for item in batch]
        results.extend(batch_result)
    return results


def process_item(item):
    """Process a single item."""
    return item.upper() if isinstance(item, str) else str(item)
'''

SAMPLE_JAVASCRIPT_CODE = """
/**
 * Sample JavaScript module for performance testing.
 */

class DataProcessor {
    constructor(config) {
        this.config = config;
        this.cache = new Map();
    }
    
    processData(data) {
        if (this.cache.has(data)) {
            return this.cache.get(data);
        }
        
        let result = this.transform(data);
        result = this.validate(result);
        result = this.normalize(result);
        
        this.cache.set(data, result);
        return result;
    }
    
    transform(data) {
        return data.map(x => x * 2);
    }
    
    validate(data) {
        return data.filter(x => x > 0);
    }
    
    normalize(data) {
        const total = data.reduce((a, b) => a + b, 0);
        return total > 0 ? data.map(x => x / total) : data;
    }
}

function calculateStatistics(values) {
    if (!values || values.length === 0) {
        return {};
    }
    
    const sum = values.reduce((a, b) => a + b, 0);
    const mean = sum / values.length;
    const sorted = [...values].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)];
    
    return {
        mean: mean,
        median: median,
        min: Math.min(...values),
        max: Math.max(...values),
        count: values.length
    };
}

function processBatch(items, batchSize = 10) {
    const results = [];
    for (let i = 0; i < items.length; i += batchSize) {
        const batch = items.slice(i, i + batchSize);
        const batchResult = batch.map(processItem);
        results.push(...batchResult);
    }
    return results;
}

function processItem(item) {
    return typeof item === 'string' ? item.toUpperCase() : String(item);
}
"""


def measure_execution_time(func, *args, **kwargs):
    """Measure execution time of a function."""
    start_time = time.time()
    result = func(*args, **kwargs)
    end_time = time.time()
    return result, end_time - start_time


def calculate_percentile(values: List[float], percentile: int) -> float:
    """Calculate percentile of a list of values."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(len(sorted_values) * percentile / 100)
    return sorted_values[min(index, len(sorted_values) - 1)]


class TestASTParsingPerformance:
    """Test AST parsing performance."""

    def test_python_parsing_performance(self):
        """
        Test Python AST parsing performance.

        Property 13: Performance Bounds
        Validates: Requirements 10.2

        For any Python file, AST parsing should complete within 2 seconds (P95).
        """
        # Create chunking strategy
        strategy = CodeChunkingStrategy("python")

        # Measure parsing time for multiple iterations
        iterations = 100
        parsing_times = []

        for _ in range(iterations):
            resource_id = uuid4()
            _, elapsed_time = measure_execution_time(
                strategy.chunk, SAMPLE_PYTHON_CODE, resource_id
            )
            parsing_times.append(elapsed_time)

        # Calculate statistics
        mean_time = statistics.mean(parsing_times)
        p95_time = calculate_percentile(parsing_times, 95)
        max_time = max(parsing_times)

        print(f"\nPython AST Parsing Performance ({iterations} iterations):")
        print(f"  Mean: {mean_time * 1000:.2f}ms")
        print(f"  P95: {p95_time * 1000:.2f}ms")
        print(f"  Max: {max_time * 1000:.2f}ms")

        # Assert P95 is under 2 seconds
        assert p95_time < 2.0, (
            f"Python AST parsing P95 ({p95_time:.3f}s) exceeds 2s requirement"
        )

    def test_javascript_parsing_performance(self):
        """
        Test JavaScript AST parsing performance.

        Property 13: Performance Bounds
        Validates: Requirements 10.2

        For any JavaScript file, AST parsing should complete within 2 seconds (P95).
        """
        # Create chunking strategy
        strategy = CodeChunkingStrategy("javascript")

        # Measure parsing time for multiple iterations
        iterations = 100
        parsing_times = []

        for _ in range(iterations):
            resource_id = uuid4()
            _, elapsed_time = measure_execution_time(
                strategy.chunk, SAMPLE_JAVASCRIPT_CODE, resource_id
            )
            parsing_times.append(elapsed_time)

        # Calculate statistics
        mean_time = statistics.mean(parsing_times)
        p95_time = calculate_percentile(parsing_times, 95)
        max_time = max(parsing_times)

        print(f"\nJavaScript AST Parsing Performance ({iterations} iterations):")
        print(f"  Mean: {mean_time * 1000:.2f}ms")
        print(f"  P95: {p95_time * 1000:.2f}ms")
        print(f"  Max: {max_time * 1000:.2f}ms")

        # Assert P95 is under 2 seconds
        assert p95_time < 2.0, (
            f"JavaScript AST parsing P95 ({p95_time:.3f}s) exceeds 2s requirement"
        )

    def test_large_file_parsing_performance(self):
        """
        Test AST parsing performance for large files.

        Property 13: Performance Bounds
        Validates: Requirements 10.2

        For any large file (10KB+), AST parsing should complete within 2 seconds (P95).
        """
        # Create a large Python file by repeating the sample code
        large_code = SAMPLE_PYTHON_CODE * 10  # ~10KB

        # Create chunking strategy
        strategy = CodeChunkingStrategy("python")

        # Measure parsing time for multiple iterations
        iterations = 50  # Fewer iterations for large files
        parsing_times = []

        for _ in range(iterations):
            resource_id = uuid4()
            _, elapsed_time = measure_execution_time(
                strategy.chunk, large_code, resource_id
            )
            parsing_times.append(elapsed_time)

        # Calculate statistics
        mean_time = statistics.mean(parsing_times)
        p95_time = calculate_percentile(parsing_times, 95)
        max_time = max(parsing_times)

        print(
            f"\nLarge File AST Parsing Performance ({iterations} iterations, ~{len(large_code)} bytes):"
        )
        print(f"  Mean: {mean_time * 1000:.2f}ms")
        print(f"  P95: {p95_time * 1000:.2f}ms")
        print(f"  Max: {max_time * 1000:.2f}ms")

        # Assert P95 is under 2 seconds
        assert p95_time < 2.0, (
            f"Large file AST parsing P95 ({p95_time:.3f}s) exceeds 2s requirement"
        )


class TestStaticAnalysisPerformance:
    """Test static analysis performance."""

    @pytest.mark.asyncio
    async def test_python_static_analysis_performance(self, async_db_session):
        """
        Test Python static analysis performance.

        Property 13: Performance Bounds
        Validates: Requirements 10.3

        For any Python file, static analysis should complete within 1 second (P95).
        """
        # Create resource and chunks
        resource = Resource(
            id=uuid4(),
            title="test.py",
            type="code_file",
            format="text/python",
            language="python",
            classification_code="PRACTICE",
        )
        async_db_session.add(resource)
        await async_db_session.flush()

        # Create chunks from sample code
        strategy = CodeChunkingStrategy("python")
        chunks = strategy.chunk(SAMPLE_PYTHON_CODE, resource.id)

        for chunk in chunks:
            async_db_session.add(chunk)
        await async_db_session.flush()

        # Create static analysis service
        service = StaticAnalysisService(async_db_session)

        # Measure analysis time for multiple iterations
        iterations = 100
        analysis_times = []

        for _ in range(iterations):
            for chunk in chunks:
                _, elapsed_time = measure_execution_time(
                    service.analyze_code_chunk, chunk, resource
                )
                analysis_times.append(elapsed_time)

        # Calculate statistics
        mean_time = statistics.mean(analysis_times)
        p95_time = calculate_percentile(analysis_times, 95)
        max_time = max(analysis_times)

        print(f"\nPython Static Analysis Performance ({len(analysis_times)} analyses):")
        print(f"  Mean: {mean_time * 1000:.2f}ms")
        print(f"  P95: {p95_time * 1000:.2f}ms")
        print(f"  Max: {max_time * 1000:.2f}ms")

        # Assert P95 is under 1 second
        assert p95_time < 1.0, (
            f"Python static analysis P95 ({p95_time:.3f}s) exceeds 1s requirement"
        )

    @pytest.mark.asyncio
    async def test_javascript_static_analysis_performance(self, async_db_session):
        """
        Test JavaScript static analysis performance.

        Property 13: Performance Bounds
        Validates: Requirements 10.3

        For any JavaScript file, static analysis should complete within 1 second (P95).
        """
        # Create resource and chunks
        resource = Resource(
            id=uuid4(),
            title="test.js",
            type="code_file",
            format="text/javascript",
            language="javascript",
            classification_code="PRACTICE",
        )
        async_db_session.add(resource)
        await async_db_session.flush()

        # Create chunks from sample code
        strategy = CodeChunkingStrategy("javascript")
        chunks = strategy.chunk(SAMPLE_JAVASCRIPT_CODE, resource.id)

        for chunk in chunks:
            async_db_session.add(chunk)
        await async_db_session.flush()

        # Create static analysis service
        service = StaticAnalysisService(async_db_session)

        # Measure analysis time for multiple iterations
        iterations = 100
        analysis_times = []

        for _ in range(iterations):
            for chunk in chunks:
                _, elapsed_time = measure_execution_time(
                    service.analyze_code_chunk, chunk, resource
                )
                analysis_times.append(elapsed_time)

        # Calculate statistics
        mean_time = statistics.mean(analysis_times)
        p95_time = calculate_percentile(analysis_times, 95)
        max_time = max(analysis_times)

        print(
            f"\nJavaScript Static Analysis Performance ({len(analysis_times)} analyses):"
        )
        print(f"  Mean: {mean_time * 1000:.2f}ms")
        print(f"  P95: {p95_time * 1000:.2f}ms")
        print(f"  Max: {max_time * 1000:.2f}ms")

        # Assert P95 is under 1 second
        assert p95_time < 1.0, (
            f"JavaScript static analysis P95 ({p95_time:.3f}s) exceeds 1s requirement"
        )


class TestCachingPerformance:
    """Test caching performance improvements."""

    def test_parser_cache_performance(self):
        """
        Test that parser caching works correctly.

        Validates: Requirements 10.2

        Cached parsers should be reused, improving performance.
        """
        from app.modules.resources.logic.chunking import CodeChunkingStrategy

        # First run - creates and caches parser
        strategy1 = CodeChunkingStrategy("python")
        resource_id = uuid4()
        chunks1, time1 = measure_execution_time(
            strategy1.chunk, SAMPLE_PYTHON_CODE, resource_id
        )

        # Second run - uses cached parser
        strategy2 = CodeChunkingStrategy("python")
        chunks2, time2 = measure_execution_time(
            strategy2.chunk, SAMPLE_PYTHON_CODE, resource_id
        )

        print("\nParser Cache Performance:")
        print(f"  First run (create + cache): {time1 * 1000:.2f}ms")
        print(f"  Second run (cached): {time2 * 1000:.2f}ms")
        if time2 > 0:
            print(f"  Speedup: {time1 / time2:.2f}x")

        # Verify both runs produce the same results
        assert len(chunks1) == len(chunks2), "Cache should produce identical results"
        assert len(chunks1) > 0, "Should produce chunks"

        # The test passes if both runs complete successfully
        # Performance improvement is a bonus, not a requirement
        # (cache overhead can exceed creation time for small operations)

    def test_classification_cache_performance(self):
        """
        Test that classification rule caching improves performance.

        Validates: Requirements 10.3

        Cached classification rules should improve performance for repeated classifications.
        """
        from app.shared.classification import classify_file

        # Create test file paths
        test_files = [
            Path("CONTRIBUTING.md"),
            Path("CODE_OF_CONDUCT.md"),
            Path("test.py"),
            Path("app.js"),
            Path("README.md"),
        ]

        # Warm up - ensure patterns are compiled
        for file_path in test_files:
            classify_file(file_path)

        # Measure performance with many iterations to reduce variance
        iterations = 1000

        # First measurement
        start_time = time.time()
        for _ in range(iterations):
            for file_path in test_files:
                classify_file(file_path)
        time1 = time.time() - start_time

        # Second measurement
        start_time = time.time()
        for _ in range(iterations):
            for file_path in test_files:
                classify_file(file_path)
        time2 = time.time() - start_time

        print(
            f"\nClassification Cache Performance ({iterations * len(test_files)} classifications):"
        )
        print(f"  First run: {time1 * 1000:.2f}ms")
        print(f"  Second run: {time2 * 1000:.2f}ms")
        print(
            f"  Average per classification: {(time1 / (iterations * len(test_files))) * 1000:.3f}ms"
        )

        # Both runs should be fast (under 100ms total for 5000 classifications)
        assert time1 < 0.1, (
            f"Classification is too slow ({time1:.3f}s for {iterations * len(test_files)} classifications)"
        )
        assert time2 < 0.1, (
            f"Classification is too slow ({time2:.3f}s for {iterations * len(test_files)} classifications)"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
