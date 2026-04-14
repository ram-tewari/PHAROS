"""
PDF Ingestion Module - Integration Verification Script

Verifies that Phase 4 is properly integrated without running full E2E tests.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

def verify_imports():
    """Verify all PDF ingestion imports work."""
    print("✓ Checking imports...")
    try:
        from app.modules.pdf_ingestion import router, PDFIngestionService
        from app.modules.pdf_ingestion.schema import (
            PDFUploadRequest,
            PDFUploadResponse,
            PDFAnnotationRequest,
            PDFAnnotationResponse,
            GraphTraversalRequest,
            GraphTraversalResponse,
        )
        print("  ✓ All imports successful")
        return True
    except Exception as e:
        print(f"  ✗ Import failed: {e}")
        return False


def verify_pymupdf():
    """Verify PyMuPDF is installed."""
    print("✓ Checking PyMuPDF...")
    try:
        import fitz
        print(f"  ✓ PyMuPDF version: {fitz.version}")
        return True
    except ImportError:
        print("  ✗ PyMuPDF not installed")
        return False


def verify_database_models():
    """Verify required database models exist."""
    print("✓ Checking database models...")
    try:
        from app.database.models import (
            DocumentChunk,
            Annotation,
            GraphEntity,
            GraphRelationship,
        )
        print("  ✓ All required models exist")
        return True
    except Exception as e:
        print(f"  ✗ Model import failed: {e}")
        return False


def verify_routes():
    """Verify PDF routes are registered."""
    print("✓ Checking route registration...")
    try:
        from app import create_app
        app = create_app()
        
        pdf_routes = [r.path for r in app.routes if 'pdf' in r.path]
        
        expected_routes = [
            '/api/resources/pdf/ingest',
            '/api/resources/pdf/annotate',
            '/api/resources/pdf/search/graph'
        ]
        
        for route in expected_routes:
            if route in pdf_routes:
                print(f"  ✓ {route}")
            else:
                print(f"  ✗ {route} NOT FOUND")
                return False
        
        return True
    except Exception as e:
        print(f"  ✗ Route verification failed: {e}")
        return False


def verify_service_methods():
    """Verify service methods exist."""
    print("✓ Checking service methods...")
    try:
        from app.modules.pdf_ingestion.service import PDFIngestionService
        
        required_methods = [
            'ingest_pdf',
            'annotate_chunk',
            'graph_traversal_search',
            '_extract_pdf_content',
            '_create_chunks',
            '_link_to_graph',
        ]
        
        for method in required_methods:
            if hasattr(PDFIngestionService, method):
                print(f"  ✓ {method}")
            else:
                print(f"  ✗ {method} NOT FOUND")
                return False
        
        return True
    except Exception as e:
        print(f"  ✗ Service verification failed: {e}")
        return False


def verify_event_bus_integration():
    """Verify event bus integration."""
    print("✓ Checking event bus integration...")
    try:
        from app.shared.event_bus import event_bus
        
        # Check if event bus is available
        metrics = event_bus.get_metrics()
        print(f"  ✓ Event bus operational (events emitted: {metrics['events_emitted']})")
        return True
    except Exception as e:
        print(f"  ✗ Event bus check failed: {e}")
        return False


def main():
    """Run all verification checks."""
    print("\n" + "="*60)
    print("Phase 4: PDF Ingestion - Integration Verification")
    print("="*60 + "\n")
    
    checks = [
        ("Imports", verify_imports),
        ("PyMuPDF", verify_pymupdf),
        ("Database Models", verify_database_models),
        ("Routes", verify_routes),
        ("Service Methods", verify_service_methods),
        ("Event Bus", verify_event_bus_integration),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"  ✗ Unexpected error: {e}")
            results.append((name, False))
        print()
    
    # Summary
    print("="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} {name}")
    
    print(f"\nTotal: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n✅ Phase 4 integration SUCCESSFUL!")
        print("\nNext steps:")
        print("1. Start the server: uvicorn app.main:app --reload")
        print("2. Visit http://localhost:8000/docs to see PDF endpoints")
        print("3. Upload a PDF using POST /api/resources/pdf/ingest")
        return 0
    else:
        print("\n❌ Phase 4 integration INCOMPLETE")
        print("\nPlease fix the failed checks above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
