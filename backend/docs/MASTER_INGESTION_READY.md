# Master Repository Ingestion - Ready to Test

## ✅ Migrations Complete

All database migrations have been successfully applied:

- ✅ Fixed PostgreSQL-specific migrations for SQLite compatibility
- ✅ Created `coding_profiles` table
- ✅ Added `profile_id` foreign key to `proposed_rules`
- ✅ Created indexes for performance
- ✅ Merged all migration heads

## 🎯 Next Steps: Ingest Your First Master

### Prerequisites

1. **Clone a legendary repository** (recommended: FastAPI)
   ```bash
   git clone https://github.com/tiangolo/fastapi.git C:/temp/fastapi
   ```

2. **Get an M2M API token**
   - You need a machine-to-machine authentication token
   - Check your backend authentication setup
   - Or temporarily use a user token for testing

3. **Start local LLM** (Ollama with CodeLlama)
   ```bash
   ollama serve
   ollama pull codellama:13b
   ```

### Run the Ingestion

```bash
cd backend
python -m app.workers.local_extraction_worker ingest-master \
  C:/temp/fastapi \
  --max-files 30 \
  --llm-url http://localhost:11434 \
  --model codellama:13b \
  --api-url http://localhost:8000 \
  --api-token YOUR_M2M_TOKEN_HERE
```

### What This Does

1. **Analyzes the repository**
   - Parses up to 30 source files using Tree-sitter AST
   - Extracts code patterns, naming conventions, architectural decisions

2. **Creates a CodingProfile**
   - Name: "The Pythonic Architect" (for FastAPI)
   - Description: Extracted from Sebastian Ramirez's coding philosophy
   - Best suited for: FastAPI-style APIs, async Python, type hints

3. **Extracts coding rules**
   - Uses local LLM to analyze code patterns
   - Creates `proposed_rules` linked to the profile
   - Status: "approved" (master rules are pre-approved)

4. **Sends to backend**
   - POSTs the CodingProfile to `/api/coding-profiles`
   - POSTs each rule to `/api/proposed-rules`
   - Links rules to the profile via `profile_id`

### Expected Output

```
🔍 Analyzing master repository: C:/temp/fastapi
📊 Found 127 Python files, analyzing top 30...
🧠 Extracting patterns with CodeLlama...
✅ Created CodingProfile: fastapi-pythonic-architect
✅ Extracted 15 coding rules
📤 Uploading to backend...
✅ Profile created: fastapi-pythonic-architect
✅ 15 rules uploaded and linked
🎉 Master ingestion complete!
```

### Verification

Check the database:

```sql
-- View the created profile
SELECT * FROM coding_profiles;

-- View linked rules
SELECT pr.*, cp.name as profile_name
FROM proposed_rules pr
JOIN coding_profiles cp ON pr.profile_id = cp.id
WHERE cp.id = 'fastapi-pythonic-architect';
```

### Alternative: Test Without LLM

If you don't have Ollama set up, you can test the database structure:

```python
# backend/test_coding_profiles.py
from app.database.session import get_db
from app.modules.proposed_rules.model import CodingProfile, ProposedRule
from datetime import datetime

db = next(get_db())

# Create a test profile
profile = CodingProfile(
    id="test-profile",
    name="Test Master",
    description="A test coding profile",
    best_suited_for={"languages": ["Python"], "frameworks": ["FastAPI"]},
    created_at=datetime.utcnow(),
    updated_at=datetime.utcnow()
)
db.add(profile)
db.commit()

# Create a test rule linked to the profile
rule = ProposedRule(
    rule_text="Always use type hints",
    context="Type safety",
    status="approved",
    profile_id="test-profile"
)
db.add(rule)
db.commit()

print("✅ Test profile and rule created!")
print(f"Profile: {profile.name}")
print(f"Rule: {rule.rule_text}")
print(f"Linked: {rule.profile_id == profile.id}")
```

## 🚀 What's Next

After ingesting a master repository:

1. **Context Assembly**: Query rules by profile
   ```python
   # Get all approved rules for FastAPI profile
   rules = db.query(ProposedRule).filter(
       ProposedRule.profile_id == "fastapi-pythonic-architect",
       ProposedRule.status == "approved"
   ).all()
   ```

2. **LLM Context**: Feed rules to Ronin
   ```python
   context = f"""
   You are coding in the style of {profile.name}.
   
   {profile.description}
   
   Follow these rules:
   {chr(10).join(f"- {r.rule_text}" for r in rules)}
   """
   ```

3. **Multiple Profiles**: Ingest more masters
   - `expressjs/express` → "The Node.js Minimalist"
   - `rust-lang/rust` → "The Memory Safety Zealot"
   - `django/django` → "The Batteries-Included Pragmatist"

## 📊 Migration Summary

### Fixed Migrations

1. **20260108_add_authority_timestamps.py**
   - Issue: PostgreSQL `DO $$` blocks don't work in SQLite
   - Fix: Use SQLAlchemy inspector to check columns before adding

2. **20260410_add_pgvector_hnsw_indexes.py**
   - Issue: `CREATE EXTENSION` is PostgreSQL-only
   - Fix: Check dialect, skip for SQLite

3. **20260410_implement_pgvector_and_splade.py**
   - Issue: Entire migration is PostgreSQL-specific
   - Fix: Check dialect at start, return early for SQLite

4. **20260410_add_coding_profiles.py**
   - Issue: SQLite doesn't support ALTER TABLE ADD CONSTRAINT
   - Fix: Use batch mode for SQLite, direct operations for PostgreSQL

### Database State

```
Current revision: 25c9c391cb35 (merge_all_heads)
Tables created:
  - coding_profiles (id, name, description, best_suited_for, created_at, updated_at)
  - proposed_rules.profile_id (FK to coding_profiles.id)
Indexes created:
  - ix_coding_profiles_name
  - ix_proposed_rules_profile_id
  - ix_proposed_rules_profile_status (composite)
```

## 🎯 Success Criteria

You'll know it worked when:

1. ✅ Migrations complete without errors
2. ✅ `coding_profiles` table exists
3. ✅ `proposed_rules.profile_id` column exists
4. ✅ Foreign key constraint works
5. ✅ Ingestion command runs successfully
6. ✅ Profile appears in database
7. ✅ Rules are linked to profile

## 🐛 Troubleshooting

### "No module named 'tree_sitter'"
```bash
pip install tree-sitter tree-sitter-python
```

### "Connection refused to localhost:11434"
```bash
# Start Ollama
ollama serve
```

### "401 Unauthorized"
- Check your API token
- Ensure M2M authentication is configured
- Or use a valid user token for testing

### "Table already exists"
```bash
# Check current migration state
python -m alembic -c config/alembic.ini current

# If needed, stamp the migration as complete
python -m alembic -c config/alembic.ini stamp head
```

---

**Status**: ✅ Ready for master ingestion
**Next**: Clone FastAPI and run the ingest-master command
**Time to first profile**: ~5 minutes (with LLM running)
