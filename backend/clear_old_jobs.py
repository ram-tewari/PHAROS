#!/usr/bin/env python3
"""
Clear Old Jobs from Redis Queue

Removes stale LangChain ingestion jobs from the queue.
"""

import os
import sys
import json
from redis import Redis

def clear_old_jobs():
    """Remove old LangChain jobs from the queue."""
    
    # Get Redis URL from environment
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        print("❌ Error: REDIS_URL environment variable not set")
        sys.exit(1)
    
    print(f"🔗 Connecting to Redis...")
    
    try:
        # Connect to Redis
        redis_client = Redis.from_url(redis_url, decode_responses=True)
        redis_client.ping()
        print("✅ Connected to Redis successfully\n")
        
        # Keys to clean
        queue_key = "pharos:tasks"
        history_key = "pharos:history"
        jobs_hash_key = "pharos:jobs"
        
        # Get all jobs from queue
        print("📋 Checking queue...")
        queue_jobs = redis_client.lrange(queue_key, 0, -1)
        print(f"   Found {len(queue_jobs)} jobs in queue\n")
        
        removed_count = 0
        kept_count = 0
        
        for job_json in queue_jobs:
            try:
                job = json.loads(job_json)
                repo_url = job.get("repo_url", "")
                
                # Remove LangChain jobs
                if "langchain" in repo_url.lower():
                    print(f"   🗑️  Removing: {repo_url}")
                    redis_client.lrem(queue_key, 0, job_json)
                    
                    # Also remove from jobs hash
                    job_id = job.get("job_id") or job.get("task_id")
                    if job_id:
                        redis_client.hdel(jobs_hash_key, job_id)
                    
                    removed_count += 1
                else:
                    print(f"   ✅ Keeping: {repo_url}")
                    kept_count += 1
                    
            except (json.JSONDecodeError, ValueError) as e:
                print(f"   ⚠️  Skipping invalid job: {e}")
                continue
        
        # Clean history (keep only recent 100 entries, remove old LangChain)
        print(f"\n📚 Cleaning history...")
        history_jobs = redis_client.lrange(history_key, 0, -1)
        print(f"   Found {len(history_jobs)} jobs in history")
        
        # Clear history and rebuild without LangChain
        redis_client.delete(history_key)
        history_kept = 0
        
        for job_json in history_jobs[:100]:  # Keep only last 100
            try:
                job = json.loads(job_json)
                repo_url = job.get("repo_url", "")
                
                if "langchain" not in repo_url.lower():
                    redis_client.rpush(history_key, job_json)
                    history_kept += 1
                    
            except (json.JSONDecodeError, ValueError):
                continue
        
        print(f"   Kept {history_kept} recent non-LangChain jobs\n")
        
        # Summary
        print("=" * 50)
        print(f"✅ Queue cleanup complete!")
        print(f"   Removed: {removed_count} LangChain jobs")
        print(f"   Kept: {kept_count} jobs (Linux kernel)")
        print(f"   History: {history_kept} recent jobs")
        print("=" * 50)
        
        # Show current queue
        print("\n📊 Current queue:")
        current_queue = redis_client.lrange(queue_key, 0, -1)
        if current_queue:
            for i, job_json in enumerate(current_queue, 1):
                try:
                    job = json.loads(job_json)
                    print(f"   {i}. {job.get('repo_url', 'unknown')}")
                except:
                    print(f"   {i}. (invalid job)")
        else:
            print("   (empty)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("🧹 Pharos Queue Cleaner")
    print("=" * 50)
    clear_old_jobs()
