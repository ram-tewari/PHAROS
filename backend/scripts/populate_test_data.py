#!/usr/bin/env python3
"""
Populate Development Database with Test Data

Creates realistic test data for performance benchmarking:
- Code chunks (resources)
- Graph relationships
- Developer profiles
- PDF annotations

Usage:
    python populate_test_data.py
"""

import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db, init_database
from app.modules.resources.model import Resource
from app.modules.graph.model import GraphEntity, GraphRelationship
from app.modules.patterns.model import DeveloperProfileRecord
from app.database.models import DocumentChunk


# Sample code snippets for different languages
CODE_SAMPLES = {
    "python": [
        """def authenticate_user(username: str, password: str) -> Optional[User]:
    \"\"\"Authenticate user with username and password\"\"\"
    user = db.query(User).filter_by(username=username).first()
    if user and verify_password(password, user.password_hash):
        return user
    return None""",
        """async def create_token(user_id: int) -> str:
    \"\"\"Create JWT token for authenticated user\"\"\"
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")""",
        """class UserService:
    def __init__(self, db: Session):
        self.db = db
    
    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()""",
        """@router.post("/login")
async def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    \"\"\"Login endpoint\"\"\"
    user = await authenticate_user(credentials.username, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = await create_token(user.id)
    return {"access_token": token, "token_type": "bearer"}""",
        """def hash_password(password: str) -> str:
    \"\"\"Hash password using bcrypt\"\"\"
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt).decode()""",
    ],
    "typescript": [
        """export async function fetchUser(userId: string): Promise<User | null> {
  const response = await fetch(`/api/users/${userId}`);
  if (!response.ok) return null;
  return response.json();
}""",
        """interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
}

export const useAuth = (): AuthState => {
  const [state, setState] = useState<AuthState>({
    user: null,
    token: null,
    isAuthenticated: false,
  });
  return state;
}""",
        """export class ApiClient {
  private baseUrl: string;
  
  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }
  
  async get<T>(path: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`);
    return response.json();
  }
}""",
    ],
    "javascript": [
        """function validateEmail(email) {
  const regex = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
  return regex.test(email);
}""",
        """async function handleSubmit(event) {
  event.preventDefault();
  const formData = new FormData(event.target);
  const data = Object.fromEntries(formData);
  
  try {
    const response = await fetch('/api/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return response.json();
  } catch (error) {
    console.error('Submit failed:', error);
  }
}""",
    ],
}

# Sample PDF content
PDF_SAMPLES = [
    {
        "title": "OAuth 2.0 Security Best Practices",
        "content": "PKCE (Proof Key for Code Exchange) MUST be used for public clients to prevent authorization code interception attacks. This is critical for mobile and single-page applications.",
        "concepts": ["OAuth", "Security", "PKCE", "Authentication"],
        "page": 12,
    },
    {
        "title": "JWT Best Practices",
        "content": "JSON Web Tokens should have short expiration times (15-30 minutes) and be paired with refresh tokens for long-lived sessions. Always validate the signature and claims.",
        "concepts": ["JWT", "Security", "Authentication", "Tokens"],
        "page": 5,
    },
    {
        "title": "REST API Design Principles",
        "content": "Use HTTP methods correctly: GET for retrieval, POST for creation, PUT for full updates, PATCH for partial updates, DELETE for removal. Return appropriate status codes.",
        "concepts": ["REST", "API", "HTTP", "Design"],
        "page": 8,
    },
    {
        "title": "Database Indexing Strategies",
        "content": "Create indexes on columns used in WHERE clauses, JOIN conditions, and ORDER BY clauses. Avoid over-indexing as it slows down writes. Use EXPLAIN to analyze query performance.",
        "concepts": ["Database", "Performance", "Indexing", "SQL"],
        "page": 15,
    },
    {
        "title": "Async/Await Patterns in Python",
        "content": "Use async/await for I/O-bound operations like database queries and HTTP requests. Avoid blocking the event loop with CPU-intensive tasks. Use asyncio.gather() for parallel execution.",
        "concepts": ["Python", "Async", "Performance", "Concurrency"],
        "page": 22,
    },
]

# Sample developer profile
SAMPLE_PROFILE = {
    "repository_url": "https://github.com/test/myapp-backend",
    "repository_name": "myapp-backend",
    "total_files_analyzed": 150,
    "total_lines_analyzed": 12500,
    "languages_detected": ["Python", "TypeScript", "JavaScript"],
    "architecture": {
        "framework": {"framework": "FastAPI", "confidence": 0.95},
        "orm": {"orm_detected": "SQLAlchemy", "confidence": 0.9},
        "dependency_injection": {"uses_di": True, "di_style": "FastAPI Depends"},
        "detected_patterns": [
            "Repository Pattern",
            "Service Layer",
            "Dependency Injection",
        ],
    },
    "style": {
        "async_patterns": {"async_density": 0.75, "await_density": 0.7},
        "naming": {
            "snake_case_ratio": 0.85,
            "type_hint_density": 0.9,
        },
        "error_handling": {
            "exception_logging_style": "logger.error with exc_info=True",
        },
        "avg_function_length": 15.5,
    },
    "git_analysis": {
        "total_commits_analyzed": 250,
        "kept_patterns": [
            {
                "description": "Async database operations with SQLAlchemy",
                "examples": ["async with session.begin():", "await session.execute()"],
                "frequency": 0.8,
            },
            {
                "description": "Pydantic models for request/response validation",
                "examples": ["class UserCreate(BaseModel):", "class UserResponse(BaseModel):"],
                "frequency": 0.9,
            },
            {
                "description": "FastAPI dependency injection for services",
                "examples": ["def get_service(db: Session = Depends(get_db)):"],
                "frequency": 0.85,
            },
        ],
        "abandoned_patterns": [
            {
                "description": "Synchronous database calls (replaced with async)",
                "examples": ["db.query(User).filter_by()"],
                "frequency": 0.3,
            },
            {
                "description": "MD5 password hashing (replaced with bcrypt)",
                "examples": ["hashlib.md5(password.encode())"],
                "frequency": 0.1,
            },
        ],
    },
    "summary": {
        "framework": "FastAPI",
        "orm": "SQLAlchemy",
        "async_density": "75%",
        "type_hint_coverage": "90%",
        "kept_patterns_count": 3,
        "abandoned_patterns_count": 2,
    },
}


async def populate_code_chunks(session: AsyncSession, count: int = 50):
    """Populate database with code chunks"""
    print(f"\n📝 Creating {count} code chunks...")
    
    created = 0
    for i in range(count):
        # Rotate through languages
        languages = list(CODE_SAMPLES.keys())
        lang = languages[i % len(languages)]
        samples = CODE_SAMPLES[lang]
        code = samples[i % len(samples)]
        
        # Create resource
        resource = Resource(
            id=str(uuid.uuid4()),
            title=f"Code Sample {i+1}: {lang}",
            content=code,
            resource_type="code",
            language=lang,
            file_path=f"src/{lang}/module_{i}.{lang}",
            start_line=1,
            end_line=len(code.split('\n')),
            semantic_summary=f"Code snippet demonstrating {lang} patterns",
            quality_score=0.75 + (i % 25) * 0.01,  # 0.75 to 0.99
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        session.add(resource)
        created += 1
        
        if (i + 1) % 10 == 0:
            await session.commit()
            print(f"  ✓ Created {i+1}/{count} code chunks")
    
    await session.commit()
    print(f"✅ Created {created} code chunks")
    return created


async def populate_graph_entities(session: AsyncSession, count: int = 30):
    """Populate database with graph entities"""
    print(f"\n🔗 Creating {count} graph entities...")
    
    entity_types = ["Function", "Class", "Module", "Concept"]
    entity_names = [
        "authenticate_user", "create_token", "UserService", "login",
        "hash_password", "verify_password", "get_user_by_id",
        "OAuth", "JWT", "Authentication", "Security", "REST API",
        "Database", "Async", "FastAPI", "SQLAlchemy",
    ]
    
    created = 0
    entities = []
    
    for i in range(count):
        entity_type = entity_types[i % len(entity_types)]
        entity_name = entity_names[i % len(entity_names)]
        
        entity = GraphEntity(
            id=str(uuid.uuid4()),
            name=f"{entity_name}_{i}",
            entity_type=entity_type,
            description=f"Entity representing {entity_name}",
            properties={"source": "test_data", "index": i},
            created_at=datetime.utcnow(),
        )
        
        session.add(entity)
        entities.append(entity)
        created += 1
    
    await session.commit()
    print(f"✅ Created {created} graph entities")
    return entities


async def populate_graph_relationships(session: AsyncSession, entities: list, count: int = 50):
    """Populate database with graph relationships"""
    print(f"\n🔗 Creating {count} graph relationships...")
    
    relationship_types = ["calls", "imports", "extends", "implements", "uses", "mentions"]
    
    created = 0
    for i in range(count):
        if len(entities) < 2:
            break
            
        # Create relationships between entities
        source = entities[i % len(entities)]
        target = entities[(i + 1) % len(entities)]
        rel_type = relationship_types[i % len(relationship_types)]
        
        relationship = GraphRelationship(
            id=str(uuid.uuid4()),
            source_id=source.id,
            target_id=target.id,
            relationship_type=rel_type,
            weight=0.5 + (i % 50) * 0.01,  # 0.5 to 0.99
            properties={"test": True, "index": i},
            created_at=datetime.utcnow(),
        )
        
        session.add(relationship)
        created += 1
        
        if (i + 1) % 10 == 0:
            await session.commit()
            print(f"  ✓ Created {i+1}/{count} relationships")
    
    await session.commit()
    print(f"✅ Created {created} graph relationships")
    return created


async def populate_developer_profiles(session: AsyncSession, count: int = 3):
    """Populate database with developer profiles"""
    print(f"\n👤 Creating {count} developer profiles...")
    
    created = 0
    for i in range(count):
        user_id = uuid.uuid4()
        
        # Modify profile slightly for each user
        profile = SAMPLE_PROFILE.copy()
        profile["repository_name"] = f"myapp-backend-{i+1}"
        profile["repository_url"] = f"https://github.com/test/myapp-backend-{i+1}"
        
        record = DeveloperProfileRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            repository_url=profile["repository_url"],
            repository_name=profile["repository_name"],
            profile_data=profile,
            total_files_analyzed=profile["total_files_analyzed"],
            total_commits_analyzed=profile["git_analysis"]["total_commits_analyzed"],
            languages_detected=json.dumps(profile["languages_detected"]),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        session.add(record)
        created += 1
    
    await session.commit()
    print(f"✅ Created {created} developer profiles")
    return created


async def populate_document_chunks(session: AsyncSession, count: int = 20):
    """Populate database with document chunks (simulating PDF content)"""
    print(f"\n📄 Creating {count} document chunks...")
    
    created_chunks = 0
    
    for i in range(count):
        sample = PDF_SAMPLES[i % len(PDF_SAMPLES)]
        
        # Create document chunk
        chunk = DocumentChunk(
            id=str(uuid.uuid4()),
            resource_id=str(uuid.uuid4()),  # Would link to actual resource
            content=sample["content"],
            chunk_index=i,
            start_char=0,
            end_char=len(sample["content"]),
            semantic_summary=sample["content"][:100],
            metadata={"page": sample["page"], "concepts": sample["concepts"]},
            created_at=datetime.utcnow(),
        )
        
        session.add(chunk)
        created_chunks += 1
        
        if (i + 1) % 5 == 0:
            await session.commit()
            print(f"  ✓ Created {i+1}/{count} document chunks")
    
    await session.commit()
    print(f"✅ Created {created_chunks} document chunks")
    return created_chunks


async def main():
    """Main function to populate database"""
    print("=" * 60)
    print("POPULATING DEVELOPMENT DATABASE")
    print("=" * 60)
    
    # Initialize database
    print("\n🔧 Initializing database connection...")
    init_database()
    print("✅ Database initialized")
    
    # Get async session
    async for session in get_db():
        try:
            # Populate data
            code_count = await populate_code_chunks(session, count=50)
            entities = await populate_graph_entities(session, count=30)
            rel_count = await populate_graph_relationships(session, entities, count=50)
            profile_count = await populate_developer_profiles(session, count=3)
            chunk_count = await populate_document_chunks(session, count=20)
            
            # Summary
            print("\n" + "=" * 60)
            print("POPULATION COMPLETE")
            print("=" * 60)
            print(f"✅ Code chunks: {code_count}")
            print(f"✅ Graph entities: {len(entities)}")
            print(f"✅ Graph relationships: {rel_count}")
            print(f"✅ Developer profiles: {profile_count}")
            print(f"✅ Document chunks: {chunk_count}")
            print(f"\n📊 Total records: {code_count + len(entities) + rel_count + profile_count + chunk_count}")
            print("\n✅ Database is ready for performance testing!")
            print("\nNext steps:")
            print("  1. Run: python benchmark_context_assembly.py")
            print("  2. Or test API: curl -X POST http://localhost:8000/api/mcp/context/retrieve ...")
            
        except Exception as e:
            print(f"\n❌ Error populating database: {e}")
            import traceback
            traceback.print_exc()
            await session.rollback()
            return 1
        
        break  # Only need one session
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
