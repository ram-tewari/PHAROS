"""Check if resources have embeddings"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Resource
import json

engine = create_engine("sqlite:///./backend.db")
Session = sessionmaker(bind=engine)
db = Session()

resources = db.query(Resource).all()

print(f"Total resources: {len(resources)}")
print(f"\nChecking embeddings:")

for r in resources:
    has_embedding = r.embedding is not None and r.embedding != ""
    has_sparse = r.sparse_embedding is not None and r.sparse_embedding != ""

    print(f"\nResource: {r.title}")
    print(f"  Has dense embedding: {has_embedding}")
    print(f"  Has sparse embedding: {has_sparse}")

    if has_embedding:
        try:
            if isinstance(r.embedding, str):
                emb = json.loads(r.embedding)
            else:
                emb = r.embedding
            print(
                f"  Embedding dimension: {len(emb) if isinstance(emb, list) else 'N/A'}"
            )
        except:
            print(f"  Embedding parse error")

db.close()
