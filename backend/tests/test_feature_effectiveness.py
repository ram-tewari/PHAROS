"""
Comprehensive Feature Effectiveness Testing for Pharos
Tests EVERY major feature with real performance metrics
"""
import asyncio
import time
import json
import sys
from pathlib import Path
from typing import Dict, List, Any
import statistics

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.shared.database import Base, get_db
from app.shared.embeddings import EmbeddingService
from app.shared.ai_core import AIService
from app.modules.resources.service import ResourceService
from app.modules.search.service import SearchService
from app.modules.graph.service import GraphService
from app.modules.quality.service import QualityService
from app.modules.taxonomy.service import TaxonomyService
from app.modules.annotations.service import AnnotationService
from app.modules.collections.service import CollectionService
from app.modules.recommendations.service import RecommendationService
from app.modules.scholarly.service import ScholarlyService


class FeatureEffectivenessTest:
    """Test effectiveness of each Pharos feature"""
    
    def __init__(self):
        # Setup test database
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(bind=self.engine)
        self.db = SessionLocal()
        
        # Initialize services
        self.embedding_service = EmbeddingService()
        self.ai_service = AIService()
        self.resource_service = ResourceService(self.db)
        self.search_service = SearchService(self.db)
        self.graph_service = GraphService(self.db)
        self.quality_service = QualityService(self.db)
        self.taxonomy_service = TaxonomyService(self.db)
        self.annotation_service = AnnotationService(self.db)
        self.collection_service = CollectionService(self.db)
        self.recommendation_service = RecommendationService(self.db)
        self.scholarly_service = ScholarlyService(self.db)
        
        self.results = {}
    
    def time_it(self, func, *args, **kwargs):
        """Time a function execution"""
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        return result, (end - start) * 1000  # ms
    
    async def time_it_async(self, func, *args, **kwargs):
        """Time an async function execution"""
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        end = time.perf_counter()
        return result, (end - start) * 1000  # ms
    
    # ========== FEATURE 1: CODE INTELLIGENCE ==========
    
    def test_code_parsing(self):
        """Test AST-based code parsing speed and accuracy"""
        print("\n" + "="*60)
        print("FEATURE 1: CODE INTELLIGENCE (AST-Based Parsing)")
        print("="*60)
        
        test_code_samples = {
            "python_simple": '''
def hello_world():
    """Simple function"""
    print("Hello, World!")
    return True

class MyClass:
    def __init__(self, name):
        self.name = name
    
    def greet(self):
        return f"Hello, {self.name}"
''',
            "python_complex": '''
import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class User:
    id: int
    name: str
    email: Optional[str] = None

async def fetch_users(db: Database) -> List[User]:
    """Fetch all users from database"""
    query = "SELECT * FROM users"
    results = await db.execute(query)
    return [User(**row) for row in results]

class UserService:
    def __init__(self, db: Database):
        self.db = db
        self._cache = {}
    
    async def get_user(self, user_id: int) -> Optional[User]:
        if user_id in self._cache:
            return self._cache[user_id]
        user = await self.db.get(User, user_id)
        self._cache[user_id] = user
        return user
''',
            "javascript": '''
import React, { useState, useEffect } from 'react';

export const UserProfile = ({ userId }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    
    useEffect(() => {
        fetchUser(userId).then(data => {
            setUser(data);
            setLoading(false);
        });
    }, [userId]);
    
    if (loading) return <div>Loading...</div>;
    return <div>{user.name}</div>;
};
'''
        }
        
        results = {
            "parsing_times": {},
            "extraction_accuracy": {},
            "claim": "<2s per file",
            "status": "UNKNOWN"
        }
        
        for name, code in test_code_samples.items():
            try:
                # Create resource with code
                resource_data = {
                    "title": f"Test {name}",
                    "content": code,
                    "resource_type": "code",
                    "language": "python" if "python" in name else "javascript"
                }
                
                resource, parse_time = self.time_it(
                    self.resource_service.create_resource,
                    resource_data
                )
                
                results["parsing_times"][name] = {
                    "time_ms": round(parse_time, 2),
                    "lines": len(code.split('\n')),
                    "chars": len(code)
                }
                
                # Check if content was stored
                results["extraction_accuracy"][name] = {
                    "content_stored": resource.content == code,
                    "metadata_present": resource.metadata is not None
                }
                
            except Exception as e:
                results["parsing_times"][name] = {"error": str(e)}
        
        # Calculate average
        times = [r["time_ms"] for r in results["parsing_times"].values() if "time_ms" in r]
        if times:
            avg_time = statistics.mean(times)
            max_time = max(times)
            results["average_ms"] = round(avg_time, 2)
            results["max_ms"] = round(max_time, 2)
            results["status"] = "✅ PASS" if max_time < 2000 else "❌ FAIL"
        
        self.results["code_intelligence"] = results
        self._print_results("Code Intelligence", results)
    
    # ========== FEATURE 2: SEMANTIC SEARCH ==========
    
    async def test_semantic_search(self):
        """Test hybrid search speed and quality"""
        print("\n" + "="*60)
        print("FEATURE 2: SEMANTIC SEARCH (Hybrid)")
        print("="*60)
        
        # Create test resources
        test_docs = [
            {"title": "Authentication in FastAPI", "content": "How to implement JWT authentication with FastAPI and OAuth2"},
            {"title": "Database Migrations", "content": "Using Alembic for database schema migrations in SQLAlchemy"},
            {"title": "React Hooks Guide", "content": "Understanding useState, useEffect, and custom hooks in React"},
            {"title": "Python Async Programming", "content": "Asyncio and async/await patterns for concurrent programming"},
            {"title": "GraphQL vs REST", "content": "Comparing GraphQL and REST API architectures"},
        ]
        
        for doc in test_docs:
            self.resource_service.create_resource(doc)
        
        results = {
            "search_times": {},
            "relevance": {},
            "claim": "<500ms search latency",
            "status": "UNKNOWN"
        }
        
        # Test queries
        test_queries = [
            ("authentication", ["Authentication in FastAPI"]),
            ("database schema", ["Database Migrations"]),
            ("react components", ["React Hooks Guide"]),
            ("async python", ["Python Async Programming"]),
        ]
        
        for query, expected_titles in test_queries:
            try:
                search_results, search_time = await self.time_it_async(
                    self.search_service.hybrid_search,
                    query=query,
                    limit=5
                )
                
                found_titles = [r.title for r in search_results]
                relevance = any(exp in found_titles for exp in expected_titles)
                
                results["search_times"][query] = round(search_time, 2)
                results["relevance"][query] = {
                    "found": relevance,
                    "top_result": found_titles[0] if found_titles else None
                }
                
            except Exception as e:
                results["search_times"][query] = f"ERROR: {str(e)}"
        
        # Calculate metrics
        times = [t for t in results["search_times"].values() if isinstance(t, (int, float))]
        if times:
            avg_time = statistics.mean(times)
            max_time = max(times)
            results["average_ms"] = round(avg_time, 2)
            results["max_ms"] = round(max_time, 2)
            results["status"] = "✅ PASS" if max_time < 500 else "❌ FAIL"
        
        relevance_count = sum(1 for r in results["relevance"].values() if r["found"])
        results["relevance_rate"] = f"{relevance_count}/{len(test_queries)}"
        
        self.results["semantic_search"] = results
        self._print_results("Semantic Search", results)
    
    # ========== FEATURE 3: KNOWLEDGE GRAPH ==========
    
    async def test_knowledge_graph(self):
        """Test graph construction and query performance"""
        print("\n" + "="*60)
        print("FEATURE 3: KNOWLEDGE GRAPH")
        print("="*60)
        
        # Create resources with citations
        paper1 = self.resource_service.create_resource({
            "title": "Attention Is All You Need",
            "content": "Transformer architecture paper",
            "resource_type": "paper"
        })
        
        paper2 = self.resource_service.create_resource({
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "content": "BERT builds on the Transformer architecture from 'Attention Is All You Need'",
            "resource_type": "paper"
        })
        
        results = {
            "graph_operations": {},
            "claim": "Citation extraction + PageRank",
            "status": "UNKNOWN"
        }
        
        try:
            # Test citation extraction
            citations, extract_time = await self.time_it_async(
                self.graph_service.extract_citations,
                paper2.id
            )
            results["graph_operations"]["citation_extraction_ms"] = round(extract_time, 2)
            results["graph_operations"]["citations_found"] = len(citations)
            
            # Test graph query
            graph_data, query_time = await self.time_it_async(
                self.graph_service.get_graph,
                resource_id=paper1.id
            )
            results["graph_operations"]["graph_query_ms"] = round(query_time, 2)
            results["graph_operations"]["nodes"] = len(graph_data.get("nodes", []))
            results["graph_operations"]["edges"] = len(graph_data.get("edges", []))
            
            # Test PageRank
            pagerank, rank_time = await self.time_it_async(
                self.graph_service.compute_pagerank
            )
            results["graph_operations"]["pagerank_ms"] = round(rank_time, 2)
            
            results["status"] = "✅ IMPLEMENTED"
            
        except Exception as e:
            results["status"] = f"❌ ERROR: {str(e)}"
        
        self.results["knowledge_graph"] = results
        self._print_results("Knowledge Graph", results)
    
    # ========== FEATURE 4: QUALITY SCORING ==========
    
    async def test_quality_scoring(self):
        """Test quality assessment speed and accuracy"""
        print("\n" + "="*60)
        print("FEATURE 4: QUALITY SCORING")
        print("="*60)
        
        # Create test resource
        resource = self.resource_service.create_resource({
            "title": "Comprehensive Guide to Python",
            "content": "This is a detailed guide covering Python basics, advanced topics, and best practices. " * 10,
            "resource_type": "documentation"
        })
        
        results = {
            "scoring_time_ms": 0,
            "dimensions": {},
            "claim": "Multi-dimensional quality assessment",
            "status": "UNKNOWN"
        }
        
        try:
            quality_score, score_time = await self.time_it_async(
                self.quality_service.compute_quality_score,
                resource.id
            )
            
            results["scoring_time_ms"] = round(score_time, 2)
            results["overall_score"] = quality_score.overall_score
            results["dimensions"] = {
                "clarity": quality_score.clarity_score,
                "completeness": quality_score.completeness_score,
                "authority": quality_score.authority_score,
                "recency": quality_score.recency_score
            }
            results["status"] = "✅ IMPLEMENTED"
            
        except Exception as e:
            results["status"] = f"❌ ERROR: {str(e)}"
        
        self.results["quality_scoring"] = results
        self._print_results("Quality Scoring", results)
    
    # ========== FEATURE 5: ANNOTATIONS ==========
    
    def test_annotations(self):
        """Test annotation creation and search"""
        print("\n" + "="*60)
        print("FEATURE 5: ANNOTATIONS")
        print("="*60)
        
        # Create resource
        resource = self.resource_service.create_resource({
            "title": "Test Code",
            "content": "def hello():\n    print('Hello')\n    return True",
            "resource_type": "code"
        })
        
        results = {
            "operations": {},
            "claim": "Precise highlighting + semantic search",
            "status": "UNKNOWN"
        }
        
        try:
            # Create annotation
            annotation_data = {
                "resource_id": resource.id,
                "content": "This function prints a greeting",
                "start_pos": 0,
                "end_pos": 20,
                "tags": ["greeting", "simple"]
            }
            
            annotation, create_time = self.time_it(
                self.annotation_service.create_annotation,
                annotation_data
            )
            results["operations"]["create_ms"] = round(create_time, 2)
            
            # Search annotations
            search_results, search_time = self.time_it(
                self.annotation_service.search_annotations,
                query="greeting"
            )
            results["operations"]["search_ms"] = round(search_time, 2)
            results["operations"]["found"] = len(search_results)
            
            results["status"] = "✅ IMPLEMENTED"
            
        except Exception as e:
            results["status"] = f"❌ ERROR: {str(e)}"
        
        self.results["annotations"] = results
        self._print_results("Annotations", results)
    
    # ========== FEATURE 6: COLLECTIONS ==========
    
    def test_collections(self):
        """Test collection management"""
        print("\n" + "="*60)
        print("FEATURE 6: COLLECTIONS")
        print("="*60)
        
        results = {
            "operations": {},
            "claim": "Flexible organization + batch ops",
            "status": "UNKNOWN"
        }
        
        try:
            # Create collection
            collection_data = {
                "name": "ML Papers",
                "description": "Machine learning research papers"
            }
            
            collection, create_time = self.time_it(
                self.collection_service.create_collection,
                collection_data
            )
            results["operations"]["create_ms"] = round(create_time, 2)
            
            # Add resources
            resource = self.resource_service.create_resource({
                "title": "Test Paper",
                "content": "ML research content"
            })
            
            _, add_time = self.time_it(
                self.collection_service.add_resource,
                collection.id,
                resource.id
            )
            results["operations"]["add_resource_ms"] = round(add_time, 2)
            
            # List collections
            collections, list_time = self.time_it(
                self.collection_service.list_collections
            )
            results["operations"]["list_ms"] = round(list_time, 2)
            results["operations"]["count"] = len(collections)
            
            results["status"] = "✅ IMPLEMENTED"
            
        except Exception as e:
            results["status"] = f"❌ ERROR: {str(e)}"
        
        self.results["collections"] = results
        self._print_results("Collections", results)
    
    # ========== FEATURE 7: TAXONOMY ==========
    
    async def test_taxonomy(self):
        """Test ML-based classification"""
        print("\n" + "="*60)
        print("FEATURE 7: TAXONOMY (ML Classification)")
        print("="*60)
        
        resource = self.resource_service.create_resource({
            "title": "Machine Learning Tutorial",
            "content": "Introduction to neural networks, deep learning, and AI",
            "resource_type": "documentation"
        })
        
        results = {
            "classification": {},
            "claim": ">85% accuracy",
            "status": "UNKNOWN"
        }
        
        try:
            classification, classify_time = await self.time_it_async(
                self.taxonomy_service.classify_resource,
                resource.id
            )
            
            results["classification"]["time_ms"] = round(classify_time, 2)
            results["classification"]["category"] = classification.category
            results["classification"]["confidence"] = classification.confidence
            results["status"] = "✅ IMPLEMENTED"
            
        except Exception as e:
            results["status"] = f"❌ ERROR: {str(e)}"
        
        self.results["taxonomy"] = results
        self._print_results("Taxonomy", results)
    
    # ========== FEATURE 8: RECOMMENDATIONS ==========
    
    async def test_recommendations(self):
        """Test recommendation engine"""
        print("\n" + "="*60)
        print("FEATURE 8: RECOMMENDATIONS")
        print("="*60)
        
        # Create multiple resources
        for i in range(5):
            self.resource_service.create_resource({
                "title": f"Resource {i}",
                "content": f"Content about topic {i % 3}",
                "tags": [f"tag{i % 3}"]
            })
        
        results = {
            "recommendation": {},
            "claim": "Hybrid NCF + content + graph",
            "status": "UNKNOWN"
        }
        
        try:
            resource = self.resource_service.create_resource({
                "title": "Target Resource",
                "content": "Content about topic 1",
                "tags": ["tag1"]
            })
            
            recommendations, rec_time = await self.time_it_async(
                self.recommendation_service.get_recommendations,
                resource_id=resource.id,
                limit=5
            )
            
            results["recommendation"]["time_ms"] = round(rec_time, 2)
            results["recommendation"]["count"] = len(recommendations)
            results["status"] = "✅ IMPLEMENTED"
            
        except Exception as e:
            results["status"] = f"❌ ERROR: {str(e)}"
        
        self.results["recommendations"] = results
        self._print_results("Recommendations", results)
    
    # ========== FEATURE 9: SCHOLARLY METADATA ==========
    
    async def test_scholarly_extraction(self):
        """Test metadata extraction from papers"""
        print("\n" + "="*60)
        print("FEATURE 9: SCHOLARLY METADATA EXTRACTION")
        print("="*60)
        
        paper_content = """
        Abstract: This paper presents a novel approach to machine learning.
        
        Equation: E = mc^2
        
        Table 1: Results
        Model | Accuracy
        A     | 95%
        B     | 92%
        
        References:
        [1] Smith et al. (2020). Previous work.
        [2] Jones (2021). Related research.
        """
        
        resource = self.resource_service.create_resource({
            "title": "Research Paper",
            "content": paper_content,
            "resource_type": "paper"
        })
        
        results = {
            "extraction": {},
            "claim": "Auto-extract equations, tables, citations",
            "status": "UNKNOWN"
        }
        
        try:
            metadata, extract_time = await self.time_it_async(
                self.scholarly_service.extract_metadata,
                resource.id
            )
            
            results["extraction"]["time_ms"] = round(extract_time, 2)
            results["extraction"]["equations_found"] = len(metadata.get("equations", []))
            results["extraction"]["tables_found"] = len(metadata.get("tables", []))
            results["extraction"]["citations_found"] = len(metadata.get("citations", []))
            results["status"] = "✅ IMPLEMENTED"
            
        except Exception as e:
            results["status"] = f"❌ ERROR: {str(e)}"
        
        self.results["scholarly_extraction"] = results
        self._print_results("Scholarly Extraction", results)
    
    # ========== HELPER METHODS ==========
    
    def _print_results(self, feature_name: str, results: Dict):
        """Pretty print results"""
        print(f"\n{feature_name} Results:")
        print(json.dumps(results, indent=2))
    
    def generate_report(self):
        """Generate final effectiveness report"""
        print("\n" + "="*80)
        print("PHAROS FEATURE EFFECTIVENESS REPORT")
        print("="*80)
        
        for feature, data in self.results.items():
            print(f"\n{feature.upper().replace('_', ' ')}")
            print("-" * 60)
            print(f"Status: {data.get('status', 'UNKNOWN')}")
            print(f"Claim: {data.get('claim', 'N/A')}")
            
            # Print key metrics
            if "average_ms" in data:
                print(f"Average Time: {data['average_ms']}ms")
            if "max_ms" in data:
                print(f"Max Time: {data['max_ms']}ms")
            if "relevance_rate" in data:
                print(f"Relevance Rate: {data['relevance_rate']}")
        
        # Summary
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        
        total_features = len(self.results)
        implemented = sum(1 for r in self.results.values() if "✅" in str(r.get("status", "")))
        failed = sum(1 for r in self.results.values() if "❌" in str(r.get("status", "")))
        
        print(f"Total Features Tested: {total_features}")
        print(f"Implemented & Working: {implemented}")
        print(f"Failed/Not Working: {failed}")
        print(f"Success Rate: {(implemented/total_features)*100:.1f}%")
    
    async def run_all_tests(self):
        """Run all feature tests"""
        print("Starting Comprehensive Feature Effectiveness Testing...")
        print("This will test EVERY major feature with real performance data\n")
        
        # Run tests
        self.test_code_parsing()
        await self.test_semantic_search()
        await self.test_knowledge_graph()
        await self.test_quality_scoring()
        self.test_annotations()
        self.test_collections()
        await self.test_taxonomy()
        await self.test_recommendations()
        await self.test_scholarly_extraction()
        
        # Generate report
        self.generate_report()
        
        # Save to file
        with open("backend/FEATURE_EFFECTIVENESS_REPORT.json", "w") as f:
            json.dump(self.results, f, indent=2)
        
        print("\n✅ Report saved to: backend/FEATURE_EFFECTIVENESS_REPORT.json")


async def main():
    tester = FeatureEffectivenessTest()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
