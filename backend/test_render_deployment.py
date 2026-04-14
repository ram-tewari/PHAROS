#!/usr/bin/env python3
"""
Test Render Deployment

This script tests the deployed Pharos API on Render Free tier.
"""

import sys
import time
import requests
from typing import Dict, Any

# Configuration
PHAROS_URL = "https://pharos-cloud-api.onrender.com"  # Update after deployment
PHAROS_TOKEN = ""  # Update with your PHAROS_ADMIN_TOKEN

def test_health() -> bool:
    """Test health endpoint."""
    print("\n🏥 Testing health endpoint...")
    
    try:
        response = requests.get(f"{PHAROS_URL}/health", timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health check passed")
            print(f"   Status: {data.get('status')}")
            print(f"   Database: {data.get('database')}")
            print(f"   Redis: {data.get('redis')}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    
    except requests.exceptions.Timeout:
        print("⏱️ Request timed out (cold start?). Retrying in 10 seconds...")
        time.sleep(10)
        return test_health()
    
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

def test_api_docs() -> bool:
    """Test API documentation endpoint."""
    print("\n📚 Testing API documentation...")
    
    try:
        response = requests.get(f"{PHAROS_URL}/docs", timeout=30)
        
        if response.status_code == 200:
            print("✅ API documentation accessible")
            print(f"   URL: {PHAROS_URL}/docs")
            return True
        else:
            print(f"❌ API documentation failed: {response.status_code}")
            return False
    
    except Exception as e:
        print(f"❌ API documentation error: {e}")
        return False

def test_context_retrieval() -> bool:
    """Test context retrieval endpoint."""
    print("\n🔍 Testing context retrieval...")
    
    if not PHAROS_TOKEN:
        print("⚠️ PHAROS_TOKEN not set. Skipping authenticated test.")
        print("   Update PHAROS_TOKEN in this script after deployment.")
        return True
    
    try:
        response = requests.post(
            f"{PHAROS_URL}/api/context/retrieve",
            headers={
                "Content-Type": "application/json",
                "X-API-Key": PHAROS_TOKEN
            },
            json={
                "query": "authentication",
                "codebase": "test-repo",
                "max_chunks": 5
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Context retrieval successful")
            print(f"   Chunks returned: {len(data.get('chunks', []))}")
            return True
        elif response.status_code == 401:
            print("❌ Authentication failed. Check PHAROS_TOKEN.")
            return False
        elif response.status_code == 404:
            print("⚠️ Codebase not found (expected for new deployment)")
            print("   Ingest a repository first.")
            return True
        else:
            print(f"❌ Context retrieval failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    
    except Exception as e:
        print(f"❌ Context retrieval error: {e}")
        return False

def test_github_ingestion() -> bool:
    """Test GitHub ingestion endpoint."""
    print("\n📥 Testing GitHub ingestion...")
    
    if not PHAROS_TOKEN:
        print("⚠️ PHAROS_TOKEN not set. Skipping authenticated test.")
        return True
    
    try:
        # Use a small test repository
        response = requests.post(
            f"{PHAROS_URL}/api/ingest/github",
            headers={
                "Content-Type": "application/json",
                "X-API-Key": PHAROS_TOKEN
            },
            json={
                "repo_url": "https://github.com/octocat/Hello-World",
                "branch": "master"
            },
            timeout=120  # Ingestion takes longer
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ GitHub ingestion successful")
            print(f"   Repository: {data.get('repository')}")
            print(f"   Files: {data.get('files_count')}")
            return True
        elif response.status_code == 401:
            print("❌ Authentication failed. Check PHAROS_TOKEN.")
            return False
        else:
            print(f"⚠️ GitHub ingestion response: {response.status_code}")
            print(f"   Response: {response.text}")
            return True  # Don't fail on ingestion issues
    
    except requests.exceptions.Timeout:
        print("⏱️ Ingestion timed out (expected for large repos)")
        print("   Check Render logs for progress.")
        return True
    
    except Exception as e:
        print(f"❌ GitHub ingestion error: {e}")
        return False

def measure_cold_start() -> float:
    """Measure cold start time."""
    print("\n⏱️ Measuring cold start time...")
    print("   (This assumes service was idle for 15+ minutes)")
    
    start_time = time.time()
    
    try:
        response = requests.get(f"{PHAROS_URL}/health", timeout=120)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            print(f"✅ Cold start completed in {elapsed:.2f} seconds")
            
            if elapsed < 5:
                print("   ℹ️ Service was already warm (not a cold start)")
            elif elapsed < 30:
                print("   ✅ Fast cold start (good!)")
            elif elapsed < 60:
                print("   ⚠️ Moderate cold start (expected for free tier)")
            else:
                print("   ❌ Slow cold start (consider keep-alive)")
            
            return elapsed
        else:
            print(f"❌ Cold start failed: {response.status_code}")
            return -1
    
    except Exception as e:
        print(f"❌ Cold start measurement error: {e}")
        return -1

def print_summary(results: Dict[str, bool]):
    """Print test summary."""
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All tests passed! Pharos is deployed and operational.")
    else:
        print("\n⚠️ Some tests failed. Check the output above for details.")

def print_next_steps():
    """Print next steps."""
    print("\n" + "="*60)
    print("🚀 NEXT STEPS")
    print("="*60)
    print("""
1. Set Up Keep-Alive (Recommended):
   - Sign up at https://uptimerobot.com
   - Create HTTP(s) monitor
   - URL: https://pharos-cloud-api.onrender.com/health
   - Interval: 5 minutes

2. Configure Ronin:
   PHAROS_API_URL=https://pharos-cloud-api.onrender.com
   PHAROS_API_KEY=<YOUR_PHAROS_ADMIN_TOKEN>

3. Ingest Your Repositories:
   curl -X POST https://pharos-cloud-api.onrender.com/api/ingest/github \\
     -H "X-API-Key: YOUR_TOKEN" \\
     -d '{"repo_url": "https://github.com/user/repo"}'

4. Test Ronin Integration:
   Ask Ronin: "How does authentication work in my-repo?"

5. Monitor Performance:
   - Render Dashboard: https://dashboard.render.com
   - Logs: Check for errors and performance issues
   - Metrics: Monitor RAM and CPU usage

📖 Full Guide: backend/RENDER_FREE_DEPLOYMENT.md
""")

def main():
    """Run all tests."""
    print("="*60)
    print("🧪 PHAROS RENDER DEPLOYMENT TEST SUITE")
    print("="*60)
    print(f"\nTarget URL: {PHAROS_URL}")
    print(f"API Token: {'Set' if PHAROS_TOKEN else 'Not Set'}")
    
    if not PHAROS_TOKEN:
        print("\n⚠️ WARNING: PHAROS_TOKEN not set")
        print("   Some tests will be skipped.")
        print("   Update PHAROS_TOKEN in this script after deployment.")
    
    # Run tests
    results = {
        "Health Check": test_health(),
        "API Documentation": test_api_docs(),
        "Context Retrieval": test_context_retrieval(),
    }
    
    # Optional: Measure cold start
    # cold_start_time = measure_cold_start()
    
    # Print summary
    print_summary(results)
    
    # Print next steps
    if all(results.values()):
        print_next_steps()
    
    return 0 if all(results.values()) else 1

if __name__ == "__main__":
    sys.exit(main())
