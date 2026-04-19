"""Test LangChain search after ingestion completes."""

import time
import requests

API_URL = "https://pharos-cloud-api.onrender.com"
TOKEN = "4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

print("=" * 60)
print("LangChain Search Test")
print("=" * 60)
print()

# Wait a bit for ingestion to start
print("[WAIT] Waiting 120 seconds for ingestion to complete...")
time.sleep(120)

# Test search
print("\n[TEST] Testing search for 'langchain agent'...")
response = requests.post(
    f"{API_URL}/api/search/advanced",
    headers=headers,
    json={
        "query": "langchain agent",
        "strategy": "parent-child",
        "top_k": 5,
        "include_code": False  # Don't fetch code yet, just check if results exist
    }
)

if response.status_code == 200:
    data = response.json()
    print(f"\n[RESULTS] Found {data['total']} results")
    print(f"[LATENCY] {data['latency_ms']:.2f}ms")
    
    if data['total'] > 0:
        print("\n✅ SUCCESS! LangChain data is searchable!")
        print("\nTop results:")
        for i, result in enumerate(data['results'][:3], 1):
            print(f"\n{i}. {result.get('title', 'N/A')}")
            print(f"   Score: {result.get('score', 0):.4f}")
            if 'metadata' in result:
                meta = result['metadata']
                print(f"   Functions: {len(meta.get('functions', []))}")
                print(f"   Classes: {len(meta.get('classes', []))}")
        
        # Now test with code fetching
        print("\n[TEST] Testing with code fetching...")
        response = requests.post(
            f"{API_URL}/api/search/advanced",
            headers=headers,
            json={
                "query": "langchain agent",
                "strategy": "parent-child",
                "top_k": 2,
                "include_code": True
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            if data['results']:
                first_result = data['results'][0]
                if 'code' in first_result and first_result['code']:
                    print(f"\n✅ Code fetching works!")
                    print(f"   Fetched {len(first_result['code'])} characters")
                    print(f"   Preview: {first_result['code'][:100]}...")
                else:
                    print("\n⚠️  No code in results (might not be implemented yet)")
        
    else:
        print("\n❌ No results found. Ingestion may not be complete yet.")
        print("   Try running this script again in a few minutes.")
else:
    print(f"\n❌ Search failed: {response.status_code}")
    print(f"   {response.text}")

print("\n" + "=" * 60)
