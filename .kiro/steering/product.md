# Pharos - Product Overview

## Purpose

Pharos is your second brain for code - an AI-powered knowledge management system that serves as the memory layer for LLM-based coding assistants like Ronin. It combines intelligent code analysis with research paper management to help you understand, organize, and discover connections across your technical knowledge base.

### The Pharos + Ronin Vision

Pharos acts as the **memory and knowledge layer** that feeds context to LLM coding assistants (Ronin). While traditional LLMs start fresh with each project, Pharos provides:

- **Code Memory**: 1000+ past codebases indexed with AST-based understanding
- **Research Memory**: Papers you've read, annotated, and extracted techniques from
- **Pattern Recognition**: Your coding style, common bugs, successful architectures learned over time
- **Knowledge Graph**: Connections between code, papers, and concepts across all your work

This creates a **self-improving coding system** where:
1. You code → Pharos ingests and learns
2. You make mistakes → Pharos remembers
3. You fix mistakes → Pharos learns the fix
4. You read papers → Pharos extracts techniques
5. You ask Ronin → Pharos provides context from your history
6. Ronin generates → Uses your learned patterns and avoids past mistakes
7. Next project → Even better recommendations

**Result**: A coding assistant that truly understands YOUR code, YOUR style, YOUR mistakes, and YOUR successes. Gets better with every project you work on.

## Target Users

### Primary Users (Pharos + Ronin Integration)
1. **Software Developers** - Engineers who want an LLM assistant that learns from their coding history
2. **Solo Developers** - Individual developers building multiple projects who want to reuse patterns
3. **Technical Leads** - Senior engineers who want to codify their expertise for team use

### Secondary Users (Standalone Pharos)
4. **Researchers** - Academic and industry researchers working with code and papers
5. **Technical Writers** - Documentation specialists organizing API docs and guides
6. **Engineering Teams** - Collaborative knowledge management for development organizations
7. **Students** - Computer science students learning from code and research papers

## Core Value Propositions

### Code Intelligence
- AST-based code analysis that understands structure, not just text
- Multi-language support (Python, JavaScript, TypeScript, Rust, Go, Java)
- Dependency graph extraction (imports, definitions, calls)
- Semantic code search - find by concept, not just keywords
- Repository-wide understanding with sub-2s per file parsing

### Research Integration
- Manage research papers alongside code
- Automatic citation extraction and resolution
- Scholarly metadata parsing (equations, tables, references)
- Quality assessment for papers and documentation
- Link papers to relevant code implementations

### Knowledge Graph
- Connect code, papers, and concepts through relationships
- Citation networks showing influence and dependencies
- Code dependency graphs visualizing architecture
- Contradiction detection across documentation
- PageRank scoring for importance

### Semantic Search and Discovery
- Hybrid search combining keyword and semantic approaches
- Advanced RAG with parent-child chunking
- GraphRAG retrieval using entity relationships
- Sub-500ms search latency
- Faceted filtering by language, quality, classification

### Active Reading and Annotation
- Precise text highlighting in code and papers
- Rich notes with semantic embeddings
- Tag organization with color-coding
- Semantic search across all annotations
- Export to Markdown and JSON

### Organization and Curation
- Flexible collection management
- Hierarchical taxonomy
- Quality-based filtering
- Batch operations
- Private, shared, or public visibility

### Self-Improving System (Pharos + Ronin)
- **Pattern Learning**: Automatically extracts successful patterns from your code history
- **Mistake Avoidance**: Remembers bugs you've fixed and prevents them in new code
- **Style Matching**: Learns your coding preferences (async/await, naming, error handling)
- **Research Integration**: Links academic papers to code implementations
- **Context Retrieval**: Provides relevant code + papers when you ask questions
- **Continuous Learning**: Gets smarter with every project you complete

## Non-Goals

### What We Are NOT Building

❌ **General-Purpose Note-Taking** - Focused on code and technical content, not general notes
❌ **Social Network** - No user profiles, followers, or social features
❌ **Content Creation Platform** - No authoring tools or publishing workflows (use your IDE/editor)
❌ **File Storage Service** - No general-purpose file hosting
❌ **Real-time Collaboration** - No simultaneous editing or live cursors
❌ **Mobile Apps** - Web-first, responsive design only (API-first for IDE integration)
❌ **Enterprise SSO** - Simple authentication only
❌ **Multi-tenancy** - Single-user or small team focus
❌ **Blockchain/Web3** - Traditional database architecture
❌ **Video/Audio Processing** - Code and text focus only
❌ **Code Execution** - Static analysis only, no code running or sandboxing

## Product Principles

1. **Code-First** - Optimized for understanding and navigating code repositories
2. **API-First** - All features accessible via RESTful API for LLM and IDE integration
3. **Privacy-Focused** - Your code and knowledge stays local or self-hosted
4. **Open Source** - Transparent, extensible, community-driven
5. **Performance** - Fast response times (<200ms for most operations, <1s for context retrieval)
6. **Simplicity** - Clean interfaces, minimal configuration
7. **Extensibility** - Plugin architecture for custom features and language support
8. **Self-Improving** - Learns from your coding history to provide better recommendations over time
9. **LLM-Agnostic** - Works with any LLM (Claude, GPT-4, Llama, etc.) via standard API

## Success Metrics

### Standalone Pharos Metrics
- **Code Analysis Speed**: <2s per file for AST parsing (P95)
- **Search Quality**: nDCG > 0.7 for hybrid search
- **Response Time**: P95 < 200ms for API endpoints
- **Classification Accuracy**: >85% for ML taxonomy
- **Repository Scale**: Handle 10K+ files per repository
- **System Reliability**: 99.9% uptime for self-hosted deployments

### Pharos + Ronin Integration Metrics
- **Context Retrieval Time**: <1s for relevant code + papers (target: 800ms)
- **Context Relevance**: >90% (measured by user feedback)
- **Pattern Learning Time**: <2s to extract patterns from history (target: 1000ms)
- **Code Quality**: Generated code quality >0.85 (using Pharos quality scoring)
- **Mistake Avoidance**: 90% of past mistakes avoided in new code
- **Style Matching**: 95% match to user's coding style
- **Time Savings**: 10x faster than manual coding for common patterns
- **Storage Efficiency**: 17x reduction with hybrid GitHub storage
- **Cost**: <$30/mo for 1000 codebases indexed
- **Scalability**: Handle 10K+ codebases with sub-second retrieval

## Current Status (April 2026)

### ✅ Production-Ready (Phases 5-8 COMPLETE)
- **Phase 5: Hybrid GitHub Storage** - 17x storage reduction, on-demand code fetching
- **Phase 6: Pattern Learning Engine** - AST + Git analysis, learns YOUR coding style
- **Phase 8: Self-Improving Loop** - LLM-based rule extraction, learns from mistakes
- **Phase 7: Ronin Integration** - API endpoints ready (desktop app separate project)

### ✅ Core Infrastructure Complete
- 14 self-contained modules with zero circular dependencies
- Hybrid edge-cloud architecture ($7/mo production cost)
- Context retrieval API (<800ms latency)
- Three-way hybrid search (keyword + dense + sparse)
- 3,302 LangChain resources indexed with dependency graphs

### ⚠️ Partial Implementation
- Ronin desktop app (API ready, app not started)
- Frontend UI (React app exists but dormant)
- PDF ingestion (module exists, not prioritized)

### Completed Phases (21+ phases over 18 months)
- ✅ Phases 1-4: Core infrastructure, search, PDF ingestion
- ✅ Phases 7-11: Collections, annotations, hybrid search, quality, recommendations
- ✅ Phases 12-14: Event-driven architecture, PostgreSQL, vertical slices
- ✅ Phases 17-19: Production hardening, advanced RAG, edge-cloud orchestration
- ✅ Phases 5-8: Hybrid storage, pattern learning, self-improving loop

**See `notebooklm/06_EVOLUTION_AND_HISTORY.md` for complete phase-by-phase analysis**

## Roadmap

### Immediate (Next 2 weeks)
- Build Ronin desktop app (API ready, needs UI)
- Test self-improving loop end-to-end
- Document pattern learning workflows

### Short-term (Next month)
- Production hardening (error tracking, monitoring)
- Scale testing with 1000 repos
- Frontend UI (rule review dashboard, PDF upload)

## Use Cases

### Use Case 1: Understanding & Debugging Old Codebases (with Ronin)

**Scenario**: You inherit a legacy authentication system and need to understand how it works.

**Workflow**:
1. Point Pharos to the codebase (GitHub URL or local path)
2. Ask Ronin: "Help me understand this authentication system"
3. Pharos retrieves context:
   - Semantic search finds auth-related code across entire codebase
   - GraphRAG traces dependencies (auth → database → session → cookies)
   - Pattern matching finds similar code you've written before
   - Research papers on authentication from your library
4. Ronin receives context and generates explanation with:
   - Code flow diagram
   - Identified issues (missing validation, sync calls, etc.)
   - Suggested refactorings based on your past successful patterns
   - References to relevant papers you've read

**Time Savings**: Minutes instead of hours/days exploring unfamiliar code

### Use Case 2: Creating New Codebases (with Ronin)

**Scenario**: You need to build a new authentication microservice.

**Workflow**:
1. Ask Ronin: "Create an authentication microservice with OAuth, JWT, and rate limiting"
2. Pharos learns from your history:
   - Analyzes 5 past auth systems you've built
   - Identifies successful patterns (async/await, bcrypt, token refresh)
   - Identifies failed patterns (no rate limiting → DDoS, MD5 → security issue)
   - Extracts your coding style (naming, error handling, structure)
   - Retrieves relevant research papers (OAuth 2.0 Security, JWT Best Practices)
3. Ronin generates production-ready code that:
   - Includes rate limiting (learned from 2022 DDoS incident)
   - Uses bcrypt (learned from 2023 security fix)
   - Uses async/await (your preferred style)
   - Follows your naming conventions
   - Implements OAuth with PKCE (from research paper)
   - Includes comprehensive error handling (your pattern)

**Time Savings**: 10x faster than manual coding, avoids 90% of past mistakes

### Use Case 3: Self-Improving Loop

**The Continuous Learning Cycle**:

```
Project 1 (2022):
├─ You write auth system manually
├─ Make mistake: No rate limiting → DDoS attack
├─ Fix: Add rate limiting
└─ Pharos learns: "Rate limiting is critical for auth"

Project 2 (2023):
├─ Ronin generates auth system with rate limiting (learned)
├─ You make mistake: Use MD5 for passwords
├─ Fix: Switch to bcrypt
└─ Pharos learns: "Use bcrypt, not MD5"

Project 3 (2024):
├─ Ronin generates auth with rate limiting + bcrypt (learned)
├─ You make mistake: Sync database calls → slow
├─ Fix: Switch to async SQLAlchemy
└─ Pharos learns: "Use async for performance"

Project 4 (2025):
├─ Ronin generates auth with all learned patterns
├─ You add: OAuth integration
├─ Works perfectly on first try
└─ Pharos learns: "OAuth pattern that works"

Project 5 (2026):
├─ Ronin generates production-ready auth system
├─ Includes: Rate limiting + bcrypt + async + OAuth
├─ Matches: Your exact coding style
├─ Avoids: All past mistakes
└─ Result: Production-ready in minutes, not days
```

## Integration Architecture

### Pharos + Ronin API Endpoints

**1. Context Retrieval** (Understanding old code)
```
POST /api/context/retrieve
{
  "query": "How does authentication work?",
  "codebase": "myapp-backend",
  "context_types": ["code", "graph", "patterns", "research"],
  "max_chunks": 10
}

Response: Code chunks + dependency graph + similar patterns + papers
Time: <1s (target: 800ms)
```

**2. Pattern Learning** (Creating new code)
```
POST /api/patterns/learn
{
  "task": "create auth microservice",
  "language": "Python",
  "framework": "FastAPI"
}

Response: Successful patterns + failed patterns + coding style + research
Time: <2s (target: 1000ms)
```

**3. Codebase Ingestion** (Hybrid GitHub storage)
```
POST /api/ingest/github
{
  "repo_url": "https://github.com/user/repo",
  "branch": "main"
}

Response: Metadata + embeddings stored (code stays on GitHub)
Storage: ~100MB for 10K files (17x reduction)
Time: ~45s for typical repo
```

### Storage Strategy: Hybrid GitHub Architecture

**Problem**: Storing 1000 codebases = 100GB+ of storage = expensive

**Solution**: Store only metadata + embeddings locally, fetch code from GitHub on-demand

**Storage Breakdown**:
- **PostgreSQL**: Metadata, embeddings, graph (1.7GB for 1000 repos)
- **Redis**: Query cache, rate limiting (1GB)
- **GitHub**: Actual code files (stays on GitHub, free)

**Benefits**:
- 17x storage reduction (100GB → 6GB)
- Cost: ~$20/mo instead of $340/mo
- Performance: <100ms to fetch code from GitHub (cached in Redis)
- Scalability: Handle 10K+ codebases

**Trade-offs**:
- Requires GitHub API access (rate limits: 5000 req/hour)
- Slight latency for first code fetch (cached after)
- Requires internet connection for code retrieval


### Medium-term (Next 3 months)
- IDE plugins (VS Code, JetBrains, Vim)
- Advanced graph visualization
- Multi-language expansion (C++, C#, Ruby, PHP, Kotlin)

### Long-term (6+ months)
- Plugin ecosystem for custom analyzers
- Community-contributed patterns library
- Distributed knowledge graph federation

---

## Documentation

For comprehensive technical details, see:
- **NotebookLM Docs** (`notebooklm/`) - 6 files covering architecture, data model, API, deployment, and evolution history
- **Tech Stack** (`tech.md`) - Technology choices and constraints
- **Repository Structure** (`structure.md`) - Where to find things
- **Quick References** - Phase 4 PDF ingestion, Pharos + Ronin integration
