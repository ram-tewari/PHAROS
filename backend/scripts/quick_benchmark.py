#!/usr/bin/env python3
"""
Quick HTTP Benchmark for Context Assembly

Tests the running Docker container via HTTP requests.
No database initialization needed.

Usage:
    python quick_benchmark.py
"""

import json
import requests
import statistics
import time

# API endpoint
BASE_URL = "http://localhost:8000"
ENDPOINT = f"{BASE_URL}/api/mcp/context/retrieve"

# Test queries
TEST_QUERIES = [
    "How does authentication work?",
    "Implement OAuth login with JWT tokens",
    "Database query optimization",
    "Async/await patterns in Python",
    "REST API design best practices",
]


def run_single_test(query: str, run_number: int) -> dict:
    """Run a single benchmark test"""
    payload = {
        "query": query,
        "codebase": "myapp-backend",
        "max_code_chunks": 10,
        "max_graph_hops": 2,
        "max_pdf_chunks": 5,
        "timeout_ms": 5000,
    }
    
    start = time.time()
    try:
        response = requests.post(ENDPOINT, json=payload, timeout=10)
        elapsed_ms = (time.time() - start) * 1000
        
        if response.status_code != 200:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:200]}",
                "elapsed_ms": elapsed_ms,
            }
        
        data = response.json()
        
        if not data.get("success"):
            return {
                "success": False,
                "error": data.get("error", "Unknown error"),
                "elapsed_ms": elapsed_ms,
            }
        
        context = data.get("context", {})
        metrics = context.get("metrics", {})
        
        return {
            "success": True,
            "run": run_number,
            "query": query[:50],
            "elapsed_ms": elapsed_ms,
            "total_time_ms": metrics.get("total_time_ms", 0),
            "semantic_search_ms": metrics.get("semantic_search_ms", 0),
            "graphrag_ms": metrics.get("graphrag_ms", 0),
            "pattern_learning_ms": metrics.get("pattern_learning_ms", 0),
            "pdf_memory_ms": metrics.get("pdf_memory_ms", 0),
            "timeout_occurred": metrics.get("timeout_occurred", False),
            "code_chunks": len(context.get("code_chunks", [])),
            "dependencies": len(context.get("graph_dependencies", [])),
            "patterns": len(context.get("developer_patterns", [])),
            "annotations": len(context.get("pdf_annotations", [])),
            "warnings": len(context.get("warnings", [])),
        }
        
    except requests.exceptions.Timeout:
        elapsed_ms = (time.time() - start) * 1000
        return {
            "success": False,
            "error": "Request timeout",
            "elapsed_ms": elapsed_ms,
        }
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        return {
            "success": False,
            "error": str(e),
            "elapsed_ms": elapsed_ms,
        }


def main():
    print("=" * 70)
    print("CONTEXT ASSEMBLY PIPELINE - QUICK BENCHMARK")
    print("=" * 70)
    print(f"\nTesting endpoint: {ENDPOINT}")
    print(f"Queries: {len(TEST_QUERIES)}")
    print(f"Runs per query: 3")
    
    # Check if server is running
    print(f"\nChecking if server is running...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"[OK] Server is running (status: {response.status_code})")
    except:
        print(f"[FAIL] Server is not responding at {BASE_URL}")
        print(f"\nPlease ensure the backend is running:")
        print(f"  cd backend")
        print(f"  uvicorn app.main:app --reload")
        return 1
    
    all_results = []
    
    # Run benchmarks
    for query_idx, query in enumerate(TEST_QUERIES, 1):
        print(f"\n{'='*70}")
        print(f"Query {query_idx}/{len(TEST_QUERIES)}: {query[:50]}...")
        print(f"{'='*70}")
        
        query_results = []
        
        for run in range(1, 4):  # 3 runs per query
            result = run_single_test(query, run)
            query_results.append(result)
            all_results.append(result)
            
            if result["success"]:
                print(
                    f"  Run {run}: {result['elapsed_ms']:.0f}ms "
                    f"(code: {result['code_chunks']}, "
                    f"deps: {result['dependencies']}, "
                    f"patterns: {result['patterns']}, "
                    f"pdfs: {result['annotations']})"
                )
            else:
                print(f"  Run {run}: FAILED - {result['error']}")
        
        # Query statistics
        successful = [r for r in query_results if r["success"]]
        if successful:
            times = [r["elapsed_ms"] for r in successful]
            print(f"\n  Stats: min={min(times):.0f}ms, "
                  f"avg={statistics.mean(times):.0f}ms, "
                  f"max={max(times):.0f}ms")
    
    # Overall statistics
    print(f"\n{'='*70}")
    print("OVERALL STATISTICS")
    print(f"{'='*70}")
    
    successful = [r for r in all_results if r["success"]]
    failed = [r for r in all_results if not r["success"]]
    
    if successful:
        total_times = [r["elapsed_ms"] for r in successful]
        search_times = [r["semantic_search_ms"] for r in successful]
        graph_times = [r["graphrag_ms"] for r in successful]
        pattern_times = [r["pattern_learning_ms"] for r in successful]
        pdf_times = [r["pdf_memory_ms"] for r in successful]
        
        print(f"\n[OK] Successful runs: {len(successful)}/{len(all_results)}")
        if failed:
            print(f"[FAIL] Failed runs: {len(failed)}/{len(all_results)}")
        
        print(f"\nTotal Assembly Time:")
        print(f"   Min:     {min(total_times):.0f}ms")
        print(f"   Average: {statistics.mean(total_times):.0f}ms")
        print(f"   Median:  {statistics.median(total_times):.0f}ms")
        print(f"   Max:     {max(total_times):.0f}ms")
        
        print(f"\nService Breakdown (Average):")
        print(f"   Semantic Search:  {statistics.mean(search_times):.0f}ms")
        print(f"   GraphRAG:         {statistics.mean(graph_times):.0f}ms")
        print(f"   Pattern Learning: {statistics.mean(pattern_times):.0f}ms")
        print(f"   PDF Memory:       {statistics.mean(pdf_times):.0f}ms")
        
        # Calculate parallel speedup
        sequential_time = (
            statistics.mean(search_times) +
            statistics.mean(graph_times) +
            statistics.mean(pattern_times) +
            statistics.mean(pdf_times)
        )
        parallel_time = statistics.mean(total_times)
        speedup = sequential_time / parallel_time if parallel_time > 0 else 0
        
        print(f"\nParallel Execution:")
        print(f"   Sequential (sum):  {sequential_time:.0f}ms")
        print(f"   Parallel (actual): {parallel_time:.0f}ms")
        print(f"   Speedup:           {speedup:.2f}x")
        
        # Results breakdown
        code_chunks = [r["code_chunks"] for r in successful]
        dependencies = [r["dependencies"] for r in successful]
        patterns = [r["patterns"] for r in successful]
        annotations = [r["annotations"] for r in successful]
        
        print(f"\nResults Breakdown (Average):")
        print(f"   Code chunks:      {statistics.mean(code_chunks):.1f}")
        print(f"   Dependencies:     {statistics.mean(dependencies):.1f}")
        print(f"   Patterns:         {statistics.mean(patterns):.1f}")
        print(f"   PDF annotations:  {statistics.mean(annotations):.1f}")
        
        # Performance targets
        print(f"\nPerformance Targets:")
        avg_time = statistics.mean(total_times)
        target_met = "[OK]" if avg_time < 1000 else "[FAIL]"
        print(f"   Target: <1000ms")
        print(f"   Actual: {avg_time:.0f}ms {target_met}")
        
        if avg_time < 500:
            print(f"   [EXCELLENT] 2x better than target!")
        elif avg_time < 750:
            print(f"   [GREAT] Well under target!")
        elif avg_time < 1000:
            print(f"   [GOOD] Meets target!")
        else:
            print(f"   [NEEDS OPTIMIZATION] Exceeds target")
        
        # Save results
        with open("benchmark_results.json", "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\n[OK] Results saved to: benchmark_results.json")
        
    else:
        print("\n[FAIL] All benchmark runs failed!")
        for result in failed:
            print(f"   Error: {result['error']}")
    
    print(f"\n{'='*70}")
    print("BENCHMARK COMPLETE")
    print(f"{'='*70}\n")
    
    return 0 if successful else 1


if __name__ == "__main__":
    exit(main())
