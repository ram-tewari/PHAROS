#!/usr/bin/env python3
print("RAG Benchmark Script")
import sys

sys.path.insert(0, ".")
from app.shared.database import init_database, get_sync_db
from app.database.models import DocumentChunk, Resource

init_database()
db_gen = get_sync_db()
db = next(db_gen)
chunks = db.query(DocumentChunk).count()
resources = db.query(Resource).count()
print(f"Database: {resources} resources, {chunks} chunks")
print("Benchmark would run here...")
