"""Test ingestion with a small repository."""

import requests

API_URL = "https://pharos-cloud-api.onrender.com"
TOKEN = "4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Use a small test repository (FastAPI has ~50 Python files)
test_repo = "github.com/tiangolo/fastapi"

print("=" * 60)
print(f"Testing with small repository: {test_repo}")
print("=" * 60)
print()

# Queue ingestion
print(f"[QUEUE] Queuing {test_repo}...")
response = requests.post(
    f"{API_URL}/api/v1/ingestion/ingest/{test_repo}",
    headers=headers
)

if response.status_code == 200:
    data = response.json()
    print(f"✅ Queued successfully!")
    print(f"   Job ID: {data['job_id']}")
    print(f"   Queue position: {data['queue_position']}")
    print()
    print("Now start the worker with: python worker.py repo")
    print("And watch for the ingestion to complete.")
else:
    print(f"❌ Failed to queue: {response.status_code}")
    print(f"   {response.text}")
