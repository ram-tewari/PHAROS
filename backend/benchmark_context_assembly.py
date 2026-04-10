#!/usr/bin/env python3
"""
Benchmark Context Assembly Pipeline

Measures actual performance against populated database.

Usage:
    python benchmark_context_assembly.py
"""

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.shared.database import init_database, get_db
from app.shared.embeddings import EmbeddingService
from app.modules.mcp.context_service import ContextAssemblyService
from app.modules.mcp.context_schema import ContextRetrievalRequest


# Test queries
TEST_QUERIES = [
    {
        "query": "How does authentication work?",
        "codebase": "myapp-backend",
        "description": "Authentication query",
    },
    {
        "query": "Implement OAuth login with JWT tokens",
        "codebase": "myapp-backend",
        "description": "OAuth implementation",
    },
    {
        "query": "Database query optimization",
        "codebase": "myapp-backend",
        "description": "Database performance",
    },
    {
        "query": "Async/await patterns in Python",
        "codebase": "myapp-backend",
        "description": "Async patterns",
    },
    {
        "query": "REST API design best practices",
        "codebase": "myapp-backend",
        "description": "API design",
    },
]


async def run_single_benchmark(
    service: ContextAssemblyService,
    query_data: dict,
    run_number: int,
) -> dict:
    """Run a single benchmark test"""
    request = ContextRetrievalRequest(
        query=query_data["query"],
        codebase=query_data["codebase"],
        max_code_chunks=10,
        max_graph_hops=2,
        max_pdf_chunks=5,
        timeout_ms=5000,
    )
    
    start = time.time()
    response = await service.assemble_context(request)
    elapsed_ms = (time.time() - start) * 1000
    
    if not response.success:
        return {
            "success": False,
            "error": response.error,
            "elapsed_ms": elapsed_ms,
        }
    
    metrics = response.context.metrics
    
    return {
        "success": True,
        "run": run_number,
        "query": query_data["description"],
        "elapsed_ms": elapsed_ms,
        "total_time_ms": metrics.total_time_ms,
        "semantic_search_ms": metrics.semantic_search_ms,
        "graphrag_ms": metrics.graphrag_ms,
        "pattern_learning_ms": metrics.pattern_learning_ms,
        "pdf_memory_ms": metrics.pdf_memory_ms,
        "timeout_occurred": metrics.timeout_occurred,
        "partial_results": metrics.partial_results,
        "code_chunks": len(response.context.code_chunks),
        "dependencies": len(response.context.graph_dependencies),
        "patterns": len(response.context.developer_patterns),
        "annotations": len(response.context.pdf_annotations),
        "warnings": len(response.context.warnings),
    }


async def run_benchmarks(runs_per_query: int = 5):
    """Run comprehensive benchmarks"""
    print("=" * 70)
    print("CONTEXT ASSEMBLY PIPELINE BENCHMARKS")
    print("=" * 70)
    
    # Initialize database
    print("\n🔧 Initializing database...")
    init_database()
    
    # Get service
    async for db_session in get_db():
        embedding_service = EmbeddingService()
        service = ContextAssemblyService(db_session, None, embedding_service)
        
        all_results = []
        
        # Run benchmarks for each query
        for query_idx, query_data in enumerate(TEST_QUERIES, 1):
            print(f"\n{'='*70}")
            print(f"Query {query_idx}/{len(TEST_QUERIES)}: {query_data['description']}")
            print(f"{'='*70}")
            print(f"Query: \"{query_data['query']}\"")
            print(f"Running {runs_per_query} iterations...\n")
            
            query_results = []
            
            for run in range(1, runs_per_query + 1):
                result = await run_single_benchmark(service, query_data, run)
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
            if query_results and query_results[0]["success"]:
                times = [r["elapsed_ms"] for r in query_results if r["success"]]
                search_times = [r["semantic_search_ms"] for r in query_results if r["success"]]
                graph_times = [r["graphrag_ms"] for r in query_results if r["success"]]
                pattern_times = [r["pattern_learning_ms"] for r in query_results if r["success"]]
                pdf_times = [r["pdf_memory_ms"] for r in query_results if r["success"]]
                
                print(f"\n  📊 Statistics for this query:")
                print(f"     Total time:    min={min(times):.0f}ms, "
                      f"avg={statistics.mean(times):.0f}ms, "
                      f"max={max(times):.0f}ms")
                print(f"     Search:        avg={statistics.mean(search_times):.0f}ms")
                print(f"     GraphRAG:      avg={statistics.mean(graph_times):.0f}ms")
                print(f"     Patterns:      avg={statistics.mean(pattern_times):.0f}ms")
                print(f"     PDF Memory:    avg={statistics.mean(pdf_times):.0f}ms")
        
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
            
            print(f"\n✅ Successful runs: {len(successful)}/{len(all_results)}")
            print(f"❌ Failed runs: {len(failed)}/{len(all_results)}")
            
            print(f"\n📊 Total Assembly Time:")
            print(f"   Min:     {min(total_times):.0f}ms")
            print(f"   Average: {statistics.mean(total_times):.0f}ms")
            print(f"   Median:  {statistics.median(total_times):.0f}ms")
            print(f"   Max:     {max(total_times):.0f}ms")
            print(f"   StdDev:  {statistics.stdev(total_times):.0f}ms")
            
            print(f"\n📊 Service Breakdown (Average):")
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
            
            print(f"\n⚡ Parallel Execution:")
            print(f"   Sequential (sum):  {sequential_time:.0f}ms")
            print(f"   Parallel (actual): {parallel_time:.0f}ms")
            print(f"   Speedup:           {speedup:.2f}x")
            
            # Results breakdown
            code_chunks = [r["code_chunks"] for r in successful]
            dependencies = [r["dependencies"] for r in successful]
            patterns = [r["patterns"] for r in successful]
            annotations = [r["annotations"] for r in successful]
            
            print(f"\n📦 Results Breakdown (Average):")
            print(f"   Code chunks:      {statistics.mean(code_chunks):.1f}")
            print(f"   Dependencies:     {statistics.mean(dependencies):.1f}")
            print(f"   Patterns:         {statistics.mean(patterns):.1f}")
            print(f"   PDF annotations:  {statistics.mean(annotations):.1f}")
            
            # Performance targets
            print(f"\n🎯 Performance Targets:")
            avg_time = statistics.mean(total_times)
            target_met = "✅" if avg_time < 1000 else "❌"
            print(f"   Target: <1000ms")
            print(f"   Actual: {avg_time:.0f}ms {target_met}")
            
            if avg_time < 500:
                print(f"   🎉 EXCELLENT: 2x better than target!")
            elif avg_time < 750:
                print(f"   ✨ GREAT: Well under target!")
            elif avg_time < 1000:
                print(f"   ✅ GOOD: Meets target!")
            else:
                print(f"   ⚠️  NEEDS OPTIMIZATION: Exceeds target")
            
            # Timeout analysis
            timeouts = [r for r in successful if r["timeout_occurred"]]
            if timeouts:
                print(f"\n⚠️  Timeouts: {len(timeouts)}/{len(successful)} runs")
            
            # Warnings analysis
            with_warnings = [r for r in successful if r["warnings"] > 0]
            if with_warnings:
                print(f"⚠️  Warnings: {len(with_warnings)}/{len(successful)} runs")
        
        else:
            print("\n❌ All benchmark runs failed!")
            for result in failed:
                print(f"   Error: {result['error']}")
        
        print(f"\n{'='*70}")
        print("BENCHMARK COMPLETE")
        print(f"{'='*70}\n")
        
        # Save results to file
        output_file = Path(__file__).parent / "benchmark_results.json"
        with open(output_file, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"📁 Results saved to: {output_file}")
        
        break  # Only need one session
    
    return 0


async def main():
    """Main entry point"""
    try:
        return await run_benchmarks(runs_per_query=5)
    except KeyboardInterrupt:
        print("\n\n⚠️  Benchmark interrupted by user")
        return 1
    except Exception as e:
        print(f"\n\n❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
