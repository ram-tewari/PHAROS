#!/usr/bin/env python3
"""
Set environment variables for Upstash Redis
"""

import os

# Set Upstash Redis environment variables
os.environ["UPSTASH_REDIS_REST_URL"] = "https://lucky-pug-47555.upstash.io"
os.environ["UPSTASH_REDIS_REST_TOKEN"] = "AbnDAAIncDFiZDgzMDAwZDNkNWU0YjFlYWFkZDc1ZTZhMjAxYmQyY3AxNDc1NTU"

print("✅ Set Upstash Redis environment variables")
print(f"URL: {os.environ['UPSTASH_REDIS_REST_URL']}")
print(f"Token: {os.environ['UPSTASH_REDIS_REST_TOKEN'][:20]}...")
