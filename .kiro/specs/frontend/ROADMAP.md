# Neo Alexandria Frontend Roadmap
## "Second Brain" for Code - Fresh Start

**Philosophy**: Dual-Head Architecture (Dashboard + MCP)
**Current Status**: Phase 3 Complete ✅ | Ready for Phase 4
**Backend URL**: `https://pharos.onrender.com` (configured in `frontend/.env`)

---

## Pharos-Specific Enhancements

This roadmap leverages Neo Alexandria's unique backend capabilities:

**🧠 Terminology**: "Cortex/Knowledge Base" (Phase 4) emphasizes the "Second Brain" concept
**🔬 LBD Integration**: "Hypothesis Mode" in Phase 4 utilizes Literature-Based Discovery for contradiction detection and hidden connections
**⭐ Quality System**: "Quality Badges" in Phase 2 visualize multi-dimensional quality scores
**📐 Scholarly Assets**: "Equation/Table Drawers" in Phase 3 showcase extracted scholarly metadata
**🧩 AST Chunking**: Phase 2 visualizes "Semantic Chunks" using AST-based chunking, not just lines
**🎯 Curation**: Phase 9 adds content curation dashboard with review queues and batch operations
**🏷️ Taxonomy**: Phase 10 adds ML-powered classification and active learning
**🔐 Social Auth**: Phase 11 adds OAuth2 Google/GitHub login

---

## Phase Overview

| Phase | Name | Focus | Complexity |
|-------|------|-------|------------|
| Phase 1 | Core Workbench & Navigation | Foundation layout, sidebar, command palette | ⭐⭐⭐ Medium |
| Phase 2 | Living Code Editor | Monaco editor, AST chunks, quality badges, annotations | ⭐⭐⭐⭐ High |
| Phase 2.5 | Backend API Integration | Wire Phase 1 & 2 to live backend, replace mocks | ⭐⭐⭐ Medium |
| Phase 3 | Living Library | PDF management, scholarly assets (equations/tables) | ⭐⭐⭐⭐ High |
| Phase 4 | Cortex/Knowledge Base | Visual graph, hypothesis mode (LBD), contradictions | ⭐⭐⭐⭐⭐ Very High |
| Phase 5 | Implementation Planner | AI-powered planning, Kanban checklist | ⭐⭐⭐ Medium |
| Phase 6 | Unified RAG Interface | Split-pane search, streaming answers, evidence | ⭐⭐⭐⭐ High |
| Phase 7 | Ops & Edge Management | System health, worker status, monitoring | ⭐⭐ Low |
| Phase 8 | MCP Client Integration | IDE ghost interface, headless tools | ⭐⭐⭐⭐ High |
| Phase 9 | Content Curation Dashboard | Review queues, batch operations, quality analysis | ⭐⭐⭐ Medium |
| Phase 10 | Taxonomy Management | ML classification, active learning, category management | ⭐⭐⭐ Medium |
| Phase 11 | Social Authentication | OAuth2 Google/GitHub login, logout | ⭐⭐ Low |

---

## Tech Stack

**Framework**: React 18 + TypeScript + Vite
**Routing**: TanStack Router
**State**: Zustand
**Data Fetching**: TanStack Query
**Styling**: Tailwind CSS

**UI Component Strategy**:
- **shadcn-ui MCP** (`@jpisnice/shadcn-ui-mcp-server`) - Core primitives
- **magic-ui MCP** (`@magicuidesign/mcp`) - Animations & effects
- **magic-mcp** (`@21st-dev/magic-mcp`) - AI component generation

**Specialized Libraries**:
- Monaco Editor (code viewing)
- React Flow (graph visualization)
- React-PDF / PDF.js (PDF rendering)
- Dnd-Kit (drag & drop)
- Framer Motion (animations)

---


## Phase 1: Core Workbench & Navigation

**What It Delivers**: The foundational "Command Center" layout

**Key Features**:
- Sidebar navigation (Repositories, Cortex, Library, Planner, Wiki, Ops)
- Global Command Palette (Cmd+K)
- Repository switcher
- Responsive workbench layout
- Theme system
- Theme system

### Backend API Endpoints Used

| Endpoint | Method | Purpose | Router File | Doc File |
|----------|--------|---------|-------------|----------|
| `/api/auth/me` | GET | Get current user info | `backend/app/modules/auth/router.py` | `backend/docs/api/auth.md` |
| `/api/auth/rate-limit` | GET | Check rate limit status | `backend/app/modules/auth/router.py` | `backend/docs/api/auth.md` |
| `/api/auth/health` | GET | Auth module health check | `backend/app/modules/auth/router.py` | `backend/docs/api/auth.md` |
| `/resources` | GET | List resources (for repo switcher) | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/resources/health` | GET | Resources module health | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/api/monitoring/health` | GET | Overall system health | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |

**Backend Dependencies**: Minimal (auth + basic resource listing)

### Implementation Options

#### Option A: "Clean & Fast" ⭐⭐ Low Complexity
- **Style**: VS Code-inspired, minimalist, monochrome
- **Components**: shadcn-ui Command, Sheet, Sidebar
- **Interaction**: Keyboard-first, Vim-style navigation
- **Pros**: Fast, accessible, familiar to developers
- **Cons**: Less visually impressive

#### Option B: "Rich & Visual" ⭐⭐⭐⭐ High Complexity
- **Style**: Glassmorphism, animated, modern
- **Components**: magic-ui Dock, Spotlight, animated sidebar
- **Interaction**: Mouse-friendly, smooth animations
- **Pros**: Beautiful, impressive, high engagement
- **Cons**: Larger bundle, performance concerns

#### Option C: "Hybrid Power" ⭐⭐⭐ Medium Complexity ⭐ RECOMMENDED
- **Style**: Clean base with strategic animations
- **Components**: magic-mcp generated + shadcn-ui + magic-ui accents
- **Interaction**: Keyboard shortcuts + mouse polish
- **Pros**: Professional, performant, balanced
- **Cons**: Requires careful integration

---

## Phase 2: Living Code Editor (Active Reading)

**What It Delivers**: Monaco-based code viewer with intelligence

**Key Features**:
- Monaco Editor (read-only)
- **Semantic Chunk Visualization** (AST-based, not just lines)
- **Quality Badges** (leverages Quality scoring system)
- **Quality Analytics Dashboard** (NEW - uses unused quality endpoints)
- Annotation gutter with colored chips
- **Annotation Search & Export** (NEW - uses unused annotation endpoints)
- Hover cards (Node2Vec summaries + 1-hop graph)
- Reference overlay (book icons link to papers)
- Tree-sitter semantic highlighting

### Backend API Endpoints Used

| Endpoint | Method | Purpose | Router File | Doc File |
|----------|--------|---------|-------------|----------|
| `/resources/{resource_id}` | GET | Get resource content | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/resources/{resource_id}/chunks` | GET | Get resource chunks | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/resources/{resource_id}/chunks` | POST | Manual chunking trigger | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/chunks/{chunk_id}` | GET | Get specific chunk | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/resources/{resource_id}/status` | GET | Get processing status | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/annotations` | GET | List annotations | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/{annotation_id}` | GET | Get annotation | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/{annotation_id}` | PUT | Update annotation | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/{annotation_id}` | DELETE | Delete annotation | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/search/fulltext` | GET | **NEW** Full-text search in annotations | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/search/semantic` | GET | Semantic annotation search | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/search/tags` | GET | **NEW** Search by tags | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/export/markdown` | GET | **NEW** Export to Markdown | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/export/json` | GET | **NEW** Export to JSON | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/quality/recalculate` | POST | **NEW** Trigger quality recomputation | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/quality/outliers` | GET | **NEW** List quality outliers | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/quality/degradation` | GET | **NEW** Quality degradation report | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/quality/distribution` | GET | **NEW** Quality score distribution | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/quality/trends` | GET | **NEW** Quality trends over time | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/quality/dimensions` | GET | **NEW** Average scores per dimension | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/quality/review-queue` | GET | **NEW** Resources flagged for review | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/quality/health` | GET | Quality module health | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/api/graph/hover` | POST | Get hover information | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |

**Backend Dependencies**: 
- Annotation API ✅
- Code embeddings (needs work)
- Node2Vec summaries (needs work)
- Quality scoring API ✅
- AST chunking API ✅

### Implementation Options

#### Option A: "Clean & Fast" ⭐⭐⭐ Medium Complexity
- **Style**: IDE-like, minimal chrome
- **Components**: Monaco + shadcn-ui Popover, Tooltip, Badge
- **Interaction**: Click to annotate, hover for info
- **Pros**: Familiar IDE feel, fast rendering
- **Cons**: Basic visuals

#### Option B: "Rich & Visual" ⭐⭐⭐⭐ High Complexity
- **Style**: Animated annotations, glowing highlights
- **Components**: Monaco + magic-ui neon badges, spotlight
- **Interaction**: Smooth animations, cinematic hover
- **Pros**: Impressive demos, engaging
- **Cons**: Performance with large files

#### Option C: "Hybrid Power" ⭐⭐⭐⭐ Medium-High Complexity ⭐ RECOMMENDED
- **Style**: Professional with strategic polish
- **Components**: magic-mcp Monaco wrapper + shadcn-ui + magic-ui accents
- **Interaction**: Hover preview, click detail, keyboard nav
- **Pros**: Professional, performant, intelligent
- **Cons**: Requires Monaco expertise

---


## Phase 2.5: Backend API Integration

**What It Delivers**: Connect Phase 1 & 2 components to live backend API

**Key Features**:
- Replace all mock data with real backend calls
- Configure axios client with auth and retry logic
- Implement TanStack Query hooks for data fetching
- Add optimistic updates for mutations
- Comprehensive error handling and loading states
- TypeScript types matching backend schemas
- Integration and property-based tests

### Backend API Endpoints Integrated

**Phase 1 Endpoints (6 total)**:

| Endpoint | Method | Purpose | Router File | Doc File |
|----------|--------|---------|-------------|----------|
| `/api/auth/me` | GET | Get current user info | `backend/app/modules/auth/router.py` | `backend/docs/api/auth.md` |
| `/api/auth/rate-limit` | GET | Check rate limit status | `backend/app/modules/auth/router.py` | `backend/docs/api/auth.md` |
| `/api/auth/health` | GET | Auth module health check | `backend/app/modules/auth/router.py` | `backend/docs/api/auth.md` |
| `/resources` | GET | List resources (for repo switcher) | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/resources/health` | GET | Resources module health | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/api/monitoring/health` | GET | Overall system health | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |

**Phase 2 Endpoints (29 total)**:

| Endpoint | Method | Purpose | Router File | Doc File |
|----------|--------|---------|-------------|----------|
| `/resources/{resource_id}` | GET | Get resource content | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/resources/{resource_id}/chunks` | GET | Get resource chunks | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/resources/{resource_id}/chunks` | POST | Manual chunking trigger | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/chunks/{chunk_id}` | GET | Get specific chunk | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/resources/{resource_id}/status` | GET | Get processing status | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/annotations` | GET | List annotations | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/{annotation_id}` | GET | Get annotation | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/{annotation_id}` | PUT | Update annotation | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/{annotation_id}` | DELETE | Delete annotation | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/search/fulltext` | GET | Full-text search in annotations | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/search/semantic` | GET | Semantic annotation search | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/search/tags` | GET | Search by tags | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/export/markdown` | GET | Export to Markdown | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/annotations/export/json` | GET | Export to JSON | `backend/app/modules/annotations/router.py` | `backend/docs/api/annotations.md` |
| `/quality/recalculate` | POST | Trigger quality recomputation | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/quality/outliers` | GET | List quality outliers | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/quality/degradation` | GET | Quality degradation report | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/quality/distribution` | GET | Quality score distribution | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/quality/trends` | GET | Quality trends over time | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/quality/dimensions` | GET | Average scores per dimension | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/quality/review-queue` | GET | Resources flagged for review | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/quality/health` | GET | Quality module health | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/api/graph/hover` | POST | Get hover information | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |

**Total: 35 endpoints integrated**

**Backend Dependencies**: 
- Backend API deployed at `https://pharos.onrender.com` ✅
- All Phase 1 & 2 endpoints available ✅
- JWT authentication configured ✅

### Implementation Approach

**Recommended: Incremental Integration** ⭐⭐⭐ Medium Complexity
- **Step 1**: Configure API client foundation (axios, interceptors, retry logic)
- **Step 2**: Integrate Phase 1 endpoints (workbench, navigation, health)
- **Step 3**: Integrate Phase 2 core (resources, chunks)
- **Step 4**: Integrate Phase 2 advanced (annotations, quality, hover)
- **Step 5**: Add error handling, loading states, comprehensive tests

**Key Technologies**:
- `axios` - HTTP client with interceptors
- `@tanstack/react-query` - Data fetching and caching
- `zod` (optional) - Runtime type validation
- `msw` - Mock Service Worker for testing

**Testing Strategy**:
- Unit tests for API client and hooks
- Integration tests for complete workflows (annotation CRUD, resource loading)
- Property-based tests for correctness properties (optimistic updates, cache invalidation)
- Updated MSW handlers matching backend schemas

**Success Criteria**:
- All Phase 1 components display real data from backend
- All Phase 2 components display real data from backend
- Repository switcher shows actual repositories
- Monaco editor loads real file content
- Semantic chunks display real AST-based chunks
- Quality badges show real quality scores
- Annotations are persisted to backend
- All API calls include proper error handling
- Loading states are shown during API calls
- All tests pass (unit, integration, property-based)

---


## Phase 3: Living Library (PDF/Docs Management)

**What It Delivers**: PDF upload, viewing, and intelligent linking

**Key Features**:
- Grid view of uploaded PDFs/docs
- PDF viewer with text highlighting
- Auto-link suggestions (PDF ↔ Code via embeddings)
- **Equation/Table Drawers** (leverages Scholarly extraction metadata)
- **Batch Collection Operations** (NEW - uses unused collection endpoints)
- **Similar Collections Discovery** (NEW)
- Page-level navigation
- Search within PDFs
- Extracted scholarly assets visualization

### Backend API Endpoints Used

| Endpoint | Method | Purpose | Router File | Doc File |
|----------|--------|---------|-------------|----------|
| `/resources` | POST | Upload resource | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/resources` | GET | List resources | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/resources/{resource_id}` | GET | Get resource | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/resources/{resource_id}` | PUT | Update resource | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/resources/{resource_id}` | DELETE | Delete resource | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/resources/ingest-repo` | POST | **NEW** Repository ingestion | `backend/app/modules/resources/router.py` | `backend/docs/api/resources.md` |
| `/scholarly/resources/{resource_id}/equations` | GET | Get equations | `backend/app/modules/scholarly/router.py` | `backend/docs/api/scholarly.md` |
| `/scholarly/resources/{resource_id}/tables` | GET | Get tables | `backend/app/modules/scholarly/router.py` | `backend/docs/api/scholarly.md` |
| `/scholarly/metadata/{resource_id}` | GET | Get metadata | `backend/app/modules/scholarly/router.py` | `backend/docs/api/scholarly.md` |
| `/scholarly/metadata/completeness-stats` | GET | **NEW** Metadata completeness | `backend/app/modules/scholarly/router.py` | `backend/docs/api/scholarly.md` |
| `/scholarly/health` | GET | Scholarly module health | `backend/app/modules/scholarly/router.py` | `backend/docs/api/scholarly.md` |
| `/collections` | POST | Create collection | `backend/app/modules/collections/router.py` | `backend/docs/api/collections.md` |
| `/collections` | GET | List collections | `backend/app/modules/collections/router.py` | `backend/docs/api/collections.md` |
| `/collections/{collection_id}` | GET | Get collection | `backend/app/modules/collections/router.py` | `backend/docs/api/collections.md` |
| `/collections/{collection_id}` | PUT | Update collection | `backend/app/modules/collections/router.py` | `backend/docs/api/collections.md` |
| `/collections/{collection_id}` | DELETE | Delete collection | `backend/app/modules/collections/router.py` | `backend/docs/api/collections.md` |
| `/collections/{collection_id}/resources` | GET | List collection resources | `backend/app/modules/collections/router.py` | `backend/docs/api/collections.md` |
| `/collections/{collection_id}/resources` | PUT | Add resource to collection | `backend/app/modules/collections/router.py` | `backend/docs/api/collections.md` |
| `/collections/{collection_id}/similar-collections` | GET | **NEW** Find similar collections | `backend/app/modules/collections/router.py` | `backend/docs/api/collections.md` |
| `/collections/{collection_id}/resources/batch` | POST | **NEW** Batch add resources | `backend/app/modules/collections/router.py` | `backend/docs/api/collections.md` |
| `/collections/{collection_id}/resources/batch` | DELETE | **NEW** Batch remove resources | `backend/app/modules/collections/router.py` | `backend/docs/api/collections.md` |
| `/collections/health` | GET | Collections module health | `backend/app/modules/collections/router.py` | `backend/docs/api/collections.md` |
| `/search` | POST | Search resources | `backend/app/modules/search/router.py` | `backend/docs/api/search.md` |
| `/search/health` | GET | Search module health | `backend/app/modules/search/router.py` | `backend/docs/api/search.md` |

**Backend Dependencies**:
- PDF ingestion API (needs work)
- PDF chunking service (needs work)
- Vector similarity for auto-linking (needs work)
- Scholarly metadata API ✅ (equations, tables, citations)

### Implementation Options

#### Option A: "Clean & Fast" ⭐⭐⭐ Medium Complexity
- **Style**: Document-focused, clean grid
- **Components**: shadcn-ui Card, Dialog, Table + react-pdf
- **Interaction**: Click to open, scroll to navigate
- **Pros**: Fast PDF rendering, simple
- **Cons**: Basic visuals, limited preview

#### Option B: "Rich & Visual" ⭐⭐⭐⭐⭐ Very High Complexity
- **Style**: Magazine-style, animated previews
- **Components**: magic-ui Bento grid + custom PDF renderer
- **Interaction**: Hover previews, smooth transitions
- **Pros**: Beautiful library view, impressive
- **Cons**: PDF rendering complexity, performance

#### Option C: "Hybrid Power" ⭐⭐⭐⭐ High Complexity ⭐ RECOMMENDED
- **Style**: Professional document manager
- **Components**: magic-mcp library grid + shadcn-ui + react-pdf
- **Interaction**: Search, filter, preview, smart linking
- **Pros**: Powerful features, good UX
- **Cons**: Complex PDF/code syncing logic

---

## Phase 4: Cortex/Knowledge Base (Visual Intelligence + Hypothesis Mode)

**What It Delivers**: Interactive knowledge graph with 3 views + Hypothesis Mode

**Key Features**:
- **City Map**: High-level clusters
- **Blast Radius**: Refactoring impact analysis
- **Dependency Waterfall**: Data flow DAG
- **Hypothesis Mode** (NEW): Leverages LBD (Literature-Based Discovery) backend
  - Contradiction detection between papers
  - Hidden connection discovery
  - Research gap identification
- **Entity Extraction & Relationships** (NEW - uses unused graph endpoints)
- **Graph Embedding Similarity** (NEW)
- Node2Vec visualization
- Interactive zoom/pan/filter

### Backend API Endpoints Used

| Endpoint | Method | Purpose | Router File | Doc File |
|----------|--------|---------|-------------|----------|
| `/api/graph/resources/{resource_id}/citations` | GET | Get citations | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/resources/{resource_id}/extract-citations` | POST | **NEW** Extract citations | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/resources/{resource_id}/related` | GET | Get related resources | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/embeddings/generate` | POST | **NEW** Generate graph embeddings | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/embeddings/{node_id}` | GET | **NEW** Get node embedding | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/embeddings/{node_id}/similar` | GET | **NEW** Find similar nodes | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/discover` | POST | **NEW** Discover hypotheses (LBD) | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/hypotheses/{hypothesis_id}` | GET | **NEW** Get hypothesis details | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/extract/{chunk_id}` | POST | **NEW** Extract entities/relationships | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/entities` | GET | **NEW** List graph entities | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/entities/{id}/relationships` | GET | **NEW** Get entity relationships | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/traverse` | GET | **NEW** Traverse knowledge graph | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/visualization/communities` | GET | Get community detection | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/visualization/centrality` | GET | Get centrality metrics | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/visualization/export` | GET | Export graph data | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |
| `/api/graph/health` | GET | Graph module health | `backend/app/modules/graph/router.py` | `backend/docs/api/graph.md` |

**Backend Dependencies**:
- Graph computation API (needs work)
- Node2Vec embeddings (needs work)
- Cluster detection (needs work)
- Dependency analysis (needs work)
- **LBD hypothesis API** ✅ (contradiction detection, hidden connections)

### Implementation Options

#### Option A: "Clean & Fast" ⭐⭐⭐ Medium Complexity
- **Style**: Technical diagram, clear nodes/edges
- **Components**: React Flow + shadcn-ui controls
- **Interaction**: Click to select, drag to pan
- **Pros**: Fast rendering, clear visualization
- **Cons**: Basic visuals, limited interactivity

#### Option B: "Rich & Visual" ⭐⭐⭐⭐⭐ Very High Complexity
- **Style**: Animated graph, glowing nodes, particles
- **Components**: Custom WebGL/D3 + magic-ui effects
- **Interaction**: Cinematic animations, smooth zoom
- **Pros**: Stunning visuals, memorable
- **Cons**: Performance with large graphs, very complex

#### Option C: "Hybrid Power" ⭐⭐⭐⭐ High Complexity ⭐ RECOMMENDED
- **Style**: Professional graph with smart interactions
- **Components**: React Flow + magic-mcp nodes + magic-ui effects
- **Interaction**: Semantic zoom, smart filtering
- **Pros**: Powerful, performant, professional
- **Cons**: Complex graph algorithms

---


## Phase 5: Implementation Planner (Action)

**What It Delivers**: AI-powered implementation planning

**Key Features**:
- Natural language input ("Plan Payment Service")
- Kanban-style checklist
- Links to architecture docs
- Links to sample code
- Step tracking and completion
- Progress visualization

### Backend API Endpoints Used

| Endpoint | Method | Purpose | Router File | Doc File |
|----------|--------|---------|-------------|----------|
| `/api/planning/analyze` | POST | Analyze architecture | `backend/app/modules/planning/router.py` | `backend/docs/api/planning.md` |
| `/api/planning/generate` | POST | Generate implementation plan | `backend/app/modules/planning/router.py` | `backend/docs/api/planning.md` |
| `/api/planning/tasks/{task_id}` | GET | Get task details | `backend/app/modules/planning/router.py` | `backend/docs/api/planning.md` |
| `/api/planning/tasks/{task_id}` | PUT | Update task status | `backend/app/modules/planning/router.py` | `backend/docs/api/planning.md` |
| `/api/planning/health` | GET | Planning module health | `backend/app/modules/planning/router.py` | `backend/docs/api/planning.md` |

**Backend Dependencies**:
- Multi-hop MCP agent (needs work)
- Architecture doc parsing (needs work)
- Sample repo analysis (needs work)

### Implementation Options

#### Option A: "Clean & Fast" ⭐⭐ Low Complexity ⭐ RECOMMENDED
- **Style**: Simple checklist, text-focused
- **Components**: shadcn-ui Checkbox, Card, Accordion
- **Interaction**: Check off steps, click links
- **Pros**: Clear, simple, fast to implement
- **Cons**: Basic visuals, limited engagement

#### Option B: "Rich & Visual" ⭐⭐⭐⭐ High Complexity
- **Style**: Animated Kanban, progress viz
- **Components**: magic-ui cards + dnd-kit + confetti
- **Interaction**: Drag to reorder, animations on complete
- **Pros**: Engaging, motivating, beautiful
- **Cons**: May be overkill for planning

#### Option C: "Hybrid Power" ⭐⭐⭐⭐ High Complexity
- **Style**: Smart planner with AI assistance
- **Components**: magic-mcp planner + shadcn-ui + magic-ui accents
- **Interaction**: AI suggestions, smart linking
- **Pros**: Intelligent, helpful, professional
- **Cons**: Requires robust backend agent

---

## Phase 6: Unified RAG Interface (Deep Integration)

**What It Delivers**: Split-pane search with streaming answers

**Key Features**:
- Natural language queries
- Streaming markdown answers (left pane)
- Evidence rail (right pane) with tabs
- Code/Paper snippet highlighting
- Hover-to-highlight synchronization
- Citation tracking
- **Advanced RAG Search** (NEW - parent-child, GraphRAG, hybrid)
- **RAG Evaluation Metrics** (NEW)
- **Recommendation Feedback & Profile** (NEW)

### Backend API Endpoints Used

| Endpoint | Method | Purpose | Router File | Doc File |
|----------|--------|---------|-------------|----------|
| `/search` | POST | Hybrid search | `backend/app/modules/search/router.py` | `backend/docs/api/search.md` |
| `/search/advanced` | POST | **NEW** Advanced RAG search | `backend/app/modules/search/router.py` | `backend/docs/api/search.md` |
| `/search/health` | GET | Search module health | `backend/app/modules/search/router.py` | `backend/docs/api/search.md` |
| `/recommendations/simple` | GET | Simple recommendations | `backend/app/modules/recommendations/router.py` | `backend/docs/api/recommendations.md` |
| `/recommendations/profile` | GET | **NEW** Get user profile | `backend/app/modules/recommendations/router.py` | `backend/docs/api/recommendations.md` |
| `/recommendations/profile` | PUT | **NEW** Update user profile | `backend/app/modules/recommendations/router.py` | `backend/docs/api/recommendations.md` |
| `/recommendations/interactions` | GET | **NEW** Get interaction history | `backend/app/modules/recommendations/router.py` | `backend/docs/api/recommendations.md` |
| `/recommendations/feedback` | POST | **NEW** Submit feedback | `backend/app/modules/recommendations/router.py` | `backend/docs/api/recommendations.md` |
| `/recommendations/metrics` | GET | **NEW** Performance metrics | `backend/app/modules/recommendations/router.py` | `backend/docs/api/recommendations.md` |
| `/recommendations/refresh` | POST | **NEW** Trigger refresh | `backend/app/modules/recommendations/router.py` | `backend/docs/api/recommendations.md` |
| `/recommendations/health` | GET | Recommendations module health | `backend/app/modules/recommendations/router.py` | `backend/docs/api/recommendations.md` |
| `/evaluation/metrics` | GET | **NEW** RAG evaluation metrics | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/evaluation/history` | GET | **NEW** RAG evaluation history | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |
| `/summaries/{resource_id}/evaluate` | POST | **NEW** Evaluate summary quality | `backend/app/modules/quality/router.py` | `backend/docs/api/quality.md` |

**Backend Dependencies**:
- Hybrid search ✅
- RAG pipeline ✅
- PDF chunk retrieval (needs work)
- Reverse HyDE ✅

### Implementation Options

#### Option A: "Clean & Fast" ⭐⭐⭐ Medium Complexity
- **Style**: Split pane, clean markdown
- **Components**: shadcn-ui Tabs, Card + markdown renderer
- **Interaction**: Type query, read answer, click evidence
- **Pros**: Clear, fast, focused on content
- **Cons**: Basic visuals, limited interactivity

#### Option B: "Rich & Visual" ⭐⭐⭐⭐⭐ Very High Complexity
- **Style**: Cinematic search, animated streaming
- **Components**: magic-ui text animation + custom streaming
- **Interaction**: Smooth animations, hover effects
- **Pros**: Impressive, engaging, memorable
- **Cons**: Complex synchronization, performance

#### Option C: "Hybrid Power" ⭐⭐⭐⭐ High Complexity ⭐ RECOMMENDED
- **Style**: Professional RAG interface
- **Components**: magic-mcp RAG structure + shadcn-ui + magic-ui streaming
- **Interaction**: Natural queries, smart highlighting
- **Pros**: Powerful, professional, intelligent UX
- **Cons**: Complex PDF/code synchronization

---


## Phase 7: Ops & Edge Management

**What It Delivers**: System health and operations dashboard

**Key Features**:
- Live status board
- Ingestion queue visualization
- GPU worker heartbeat
- Manual re-index buttons
- Performance metrics
- Error tracking
- **Detailed Monitoring Dashboards** (NEW - uses unused monitoring endpoints)
- **Sparse Embedding Generation** (NEW)

### Backend API Endpoints Used

| Endpoint | Method | Purpose | Router File | Doc File |
|----------|--------|---------|-------------|----------|
| `/api/v1/ingestion/ingest/{repo_url:path}` | POST | Ingest repository | `backend/app/routers/ingestion.py` | `backend/docs/api/ingestion.md` |
| `/api/v1/ingestion/worker/status` | GET | Worker status | `backend/app/routers/ingestion.py` | `backend/docs/api/ingestion.md` |
| `/api/v1/ingestion/jobs/history` | GET | Job history | `backend/app/routers/ingestion.py` | `backend/docs/api/ingestion.md` |
| `/api/v1/ingestion/health` | GET | Ingestion health | `backend/app/routers/ingestion.py` | `backend/docs/api/ingestion.md` |
| `/api/monitoring/health` | GET | Overall health | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |
| `/api/monitoring/performance` | GET | **NEW** Performance metrics | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |
| `/api/monitoring/recommendation-quality` | GET | **NEW** Recommendation quality | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |
| `/api/monitoring/user-engagement` | GET | **NEW** User engagement | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |
| `/api/monitoring/model-health` | GET | **NEW** NCF model health | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |
| `/api/monitoring/health/ml` | GET | **NEW** ML model health | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |
| `/api/monitoring/database` | GET | **NEW** Database metrics | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |
| `/api/monitoring/db/pool` | GET | **NEW** DB connection pool | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |
| `/api/monitoring/events` | GET | **NEW** Event bus metrics | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |
| `/api/monitoring/events/history` | GET | **NEW** Event history | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |
| `/api/monitoring/cache/stats` | GET | **NEW** Cache statistics | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |
| `/api/monitoring/workers/status` | GET | **NEW** Celery worker status | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |
| `/api/monitoring/health/module/{module_name}` | GET | **NEW** Module health | `backend/app/modules/monitoring/router.py` | `backend/docs/api/monitoring.md` |
| `/admin/sparse-embeddings/generate` | POST | **NEW** Generate sparse embeddings | `backend/app/modules/search/router.py` | `backend/docs/api/search.md` |

**Backend Dependencies**:
- Redis queue API ✅
- Edge worker status API ✅
- Monitoring endpoints ✅

### Implementation Options

#### Option A: "Clean & Fast" ⭐⭐ Low Complexity ⭐ RECOMMENDED
- **Style**: Dashboard, simple metrics
- **Components**: shadcn-ui Card, Badge, Progress + recharts
- **Interaction**: View status, click to refresh
- **Pros**: Clear, functional, reliable
- **Cons**: Basic visuals, limited insights

#### Option B: "Rich & Visual" ⭐⭐⭐⭐ High Complexity
- **Style**: Animated dashboard, real-time effects
- **Components**: magic-ui animated progress + orbiting circles
- **Interaction**: Real-time updates, smooth animations
- **Pros**: Engaging, impressive, real-time feel
- **Cons**: Complexity, potential performance issues

#### Option C: "Hybrid Power" ⭐⭐⭐ Medium Complexity
- **Style**: Professional ops dashboard
- **Components**: magic-mcp dashboard + shadcn-ui + magic-ui alerts
- **Interaction**: Auto-refresh, smart alerts
- **Pros**: Professional, informative, reliable
- **Cons**: Requires robust monitoring backend

---

## Phase 8: MCP Client Integration (IDE Ghost Interface)

**What It Delivers**: Headless MCP tools for IDE integration

**Key Features**:
- `@SecondBrain search` - Text search with file links
- `@SecondBrain plan` - Implementation plan generator
- `@SecondBrain context` - Contextual suggestions
- IDE integration (VS Code, Cursor, Claude)
- Local file linking

### Backend API Endpoints Used

| Endpoint | Method | Purpose | Router File | Doc File |
|----------|--------|---------|-------------|----------|
| `/api/mcp/tools` | GET | List available tools | `backend/app/modules/mcp/router.py` | `backend/docs/api/mcp.md` |
| `/api/mcp/tools/{tool_name}` | POST | Execute tool | `backend/app/modules/mcp/router.py` | `backend/docs/api/mcp.md` |
| `/api/mcp/sessions` | POST | Create session | `backend/app/modules/mcp/router.py` | `backend/docs/api/mcp.md` |
| `/api/mcp/sessions/{session_id}` | GET | **NEW** Get session details | `backend/app/modules/mcp/router.py` | `backend/docs/api/mcp.md` |
| `/api/mcp/health` | GET | MCP module health | `backend/app/modules/mcp/router.py` | `backend/docs/api/mcp.md` |

**Backend Dependencies**:
- MCP server implementation (needs work)
- Tool definitions (needs work)
- Context management (needs work)

### Implementation Options

#### Option A: "Clean & Fast" ⭐⭐ Low Complexity
- **Style**: Text-based responses
- **Components**: Simple MCP tool definitions
- **Interaction**: Command-based, text responses
- **Pros**: Simple, reliable, fast
- **Cons**: Basic functionality, limited richness

#### Option B: "Rich & Visual" ⭐⭐⭐⭐ High Complexity
- **Style**: Rich markdown, embedded previews
- **Components**: Rich MCP tools + embedded code previews
- **Interaction**: Rich responses, embedded interactions
- **Pros**: Rich experience, engaging, powerful
- **Cons**: Complex MCP implementation, IDE limitations

#### Option C: "Hybrid Power" ⭐⭐⭐⭐ High Complexity ⭐ RECOMMENDED
- **Style**: Smart responses with contextual richness
- **Components**: magic-mcp tool structure + adaptive responses
- **Interaction**: Smart, adaptive, context-aware
- **Pros**: Intelligent, flexible, powerful
- **Cons**: Complex context management

---

## Phase 9: Content Curation Dashboard

**What It Delivers**: Professional content curation and quality management

**Key Features**:
- Review queue with quality threshold filtering
- Batch resource operations (update, tag, assign)
- Quality analysis dashboard
- Low-quality resource detection
- Bulk quality recalculation
- Curator assignment workflow
- Priority ranking system

### Backend API Endpoints Used

| Endpoint | Method | Purpose | Router File | Doc File |
|----------|--------|---------|-------------|----------|
| `/curation/review-queue` | GET | Review queue with quality threshold | `backend/app/modules/curation/router.py` | `backend/docs/api/curation.md` |
| `/curation/batch-update` | POST | Batch resource updates | `backend/app/modules/curation/router.py` | `backend/docs/api/curation.md` |
| `/curation/quality-analysis/{resource_id}` | GET | Quality analysis details | `backend/app/modules/curation/router.py` | `backend/docs/api/curation.md` |
| `/curation/low-quality` | GET | List low-quality resources | `backend/app/modules/curation/router.py` | `backend/docs/api/curation.md` |
| `/curation/bulk-quality-check` | POST | Bulk quality recalculation | `backend/app/modules/curation/router.py` | `backend/docs/api/curation.md` |
| `/curation/batch/review` | POST | Batch review operations | `backend/app/modules/curation/router.py` | `backend/docs/api/curation.md` |
| `/curation/batch/tag` | POST | Batch tagging | `backend/app/modules/curation/router.py` | `backend/docs/api/curation.md` |
| `/curation/batch/assign` | POST | Assign curator to resources | `backend/app/modules/curation/router.py` | `backend/docs/api/curation.md` |
| `/curation/queue` | GET | Enhanced review queue with filters | `backend/app/modules/curation/router.py` | `backend/docs/api/curation.md` |

**Backend Dependencies**:
- Curation module ✅ (fully implemented)
- Quality scoring integration ✅
- Batch operation support ✅

### Implementation Options

#### Option A: "Clean & Fast" ⭐⭐⭐ Medium Complexity ⭐ RECOMMENDED
- **Style**: Dashboard-focused, data tables
- **Components**: shadcn-ui Table, Badge, Dialog + recharts
- **Interaction**: Filter, sort, batch select, review
- **Pros**: Clear, functional, efficient for curation
- **Cons**: Basic visuals, limited engagement

#### Option B: "Rich & Visual" ⭐⭐⭐⭐ High Complexity
- **Style**: Animated dashboard, visual quality indicators
- **Components**: magic-ui cards + animated progress + confetti
- **Interaction**: Drag-to-batch, smooth animations
- **Pros**: Engaging, motivating, beautiful
- **Cons**: May be overkill for admin tasks

#### Option C: "Hybrid Power" ⭐⭐⭐⭐ High Complexity
- **Style**: Professional curation dashboard
- **Components**: magic-mcp dashboard + shadcn-ui + magic-ui alerts
- **Interaction**: Smart filtering, batch operations, AI suggestions
- **Pros**: Powerful, professional, efficient
- **Cons**: Complex batch operation logic

---

## Phase 10: Taxonomy Management & Active Learning

**What It Delivers**: ML-powered classification and taxonomy management

**Key Features**:
- Category creation and management
- Manual resource classification
- ML classification predictions with confidence scores
- Model retraining workflow
- Active learning with uncertain predictions
- Classification accuracy tracking
- Taxonomy tree visualization

### Backend API Endpoints Used

| Endpoint | Method | Purpose | Router File | Doc File |
|----------|--------|---------|-------------|----------|
| `/taxonomy/categories` | POST | Create taxonomy category | `backend/app/modules/taxonomy/router.py` | `backend/docs/api/taxonomy.md` |
| `/taxonomy/classify/{resource_id}` | POST | Classify resource | `backend/app/modules/taxonomy/router.py` | `backend/docs/api/taxonomy.md` |
| `/taxonomy/predictions/{resource_id}` | GET | Get classification predictions | `backend/app/modules/taxonomy/router.py` | `backend/docs/api/taxonomy.md` |
| `/taxonomy/retrain` | POST | Retrain ML classification model | `backend/app/modules/taxonomy/router.py` | `backend/docs/api/taxonomy.md` |
| `/taxonomy/uncertain` | GET | Get uncertain predictions for active learning | `backend/app/modules/taxonomy/router.py` | `backend/docs/api/taxonomy.md` |
| `/authority/subjects/suggest` | GET | Subject suggestions | `backend/app/modules/authority/router.py` | `backend/docs/api/authority.md` |
| `/authority/classification/tree` | GET | Classification tree | `backend/app/modules/authority/router.py` | `backend/docs/api/authority.md` |

**Backend Dependencies**:
- Taxonomy module ✅ (fully implemented)
- Authority module ✅ (fully implemented)
- ML classification model ✅
- Active learning pipeline ✅

### Implementation Options

#### Option A: "Clean & Fast" ⭐⭐⭐ Medium Complexity ⭐ RECOMMENDED
- **Style**: Tree view + prediction cards
- **Components**: shadcn-ui Tree, Card, Badge, Progress
- **Interaction**: Click to classify, review predictions
- **Pros**: Clear, functional, easy to understand
- **Cons**: Basic visuals, limited interactivity

#### Option B: "Rich & Visual" ⭐⭐⭐⭐⭐ Very High Complexity
- **Style**: Animated tree, confidence visualizations
- **Components**: Custom D3 tree + magic-ui effects
- **Interaction**: Smooth animations, interactive confidence
- **Pros**: Beautiful, engaging, impressive
- **Cons**: Complex tree rendering, performance

#### Option C: "Hybrid Power" ⭐⭐⭐⭐ High Complexity
- **Style**: Professional taxonomy manager
- **Components**: magic-mcp tree structure + shadcn-ui + magic-ui accents
- **Interaction**: Smart suggestions, batch classification
- **Pros**: Powerful, professional, intelligent
- **Cons**: Complex ML integration

---

## Phase 11: Social Authentication (Re-enable Phase 0)

**What It Delivers**: Re-enable OAuth2 social login from Phase 0

**Key Features**:
- Google OAuth2 login (already configured in Phase 0)
- GitHub OAuth2 login (already configured in Phase 0)
- Logout functionality
- Social profile integration
- Seamless authentication flow

**Note**: This was already implemented in Phase 0 but disabled during the fresh start. Just needs to be re-enabled in the frontend.

### Backend API Endpoints Used

| Endpoint | Method | Purpose | Router File | Doc File |
|----------|--------|---------|-------------|----------|
| `/api/auth/google` | GET | Initiate Google OAuth2 | `backend/app/modules/auth/router.py` | `backend/docs/api/auth.md` |
| `/api/auth/google/callback` | GET | Google OAuth2 callback | `backend/app/modules/auth/router.py` | `backend/docs/api/auth.md` |
| `/api/auth/github` | GET | Initiate GitHub OAuth2 | `backend/app/modules/auth/router.py` | `backend/docs/api/auth.md` |
| `/api/auth/github/callback` | GET | GitHub OAuth2 callback | `backend/app/modules/auth/router.py` | `backend/docs/api/auth.md` |
| `/api/auth/logout` | POST | Logout and revoke token | `backend/app/modules/auth/router.py` | `backend/docs/api/auth.md` |
| `/api/auth/me` | GET | Get current user info | `backend/app/modules/auth/router.py` | `backend/docs/api/auth.md` |

**Backend Dependencies**:
- OAuth2 integration ✅ (fully implemented in Phase 0)
- Google OAuth2 credentials ✅ (already configured)
- GitHub OAuth2 credentials ✅ (already configured)
- Backend URL: `https://pharos.onrender.com`

### Implementation Options

#### Option A: "Clean & Fast" ⭐⭐ Low Complexity ⭐ RECOMMENDED
- **Style**: Simple login buttons (re-enable Phase 0 components)
- **Components**: shadcn-ui Button, Card (already exists)
- **Interaction**: Click to login, redirect flow (already implemented)
- **Pros**: Simple, reliable, already tested in Phase 0
- **Cons**: Basic visuals, standard flow

#### Option B: "Rich & Visual" ⭐⭐⭐ Medium Complexity
- **Style**: Animated login, smooth transitions
- **Components**: magic-ui shimmer buttons + animated cards
- **Interaction**: Smooth animations, loading states
- **Pros**: Polished, engaging, professional
- **Cons**: May be overkill for simple auth

#### Option C: "Hybrid Power" ⭐⭐⭐ Medium Complexity
- **Style**: Professional auth flow
- **Components**: magic-mcp auth structure + shadcn-ui + magic-ui accents
- **Interaction**: Smart redirects, error handling
- **Pros**: Professional, reliable, good UX
- **Cons**: More work than just re-enabling Phase 0

**Recommendation**: Option A - Just re-enable the Phase 0 OAuth2 implementation that's already working on `https://pharos.onrender.com`

---


## Recommended Implementation Strategy

### Phase Priority & Approach

**Tier 1 (Foundation)** - Build First:
1. **Phase 1** (Workbench) - Option C: Hybrid Power ✅ COMPLETE
   - Establishes the entire UI foundation
   - All other phases depend on this

**Tier 2 (Core Features)** - Build Next:
2. **Phase 2** (Code Editor) - Option C: Hybrid Power ✅ COMPLETE
   - Monaco editor with semantic overlays
   - Annotation and quality systems
3. **Phase 2.5** (Backend API Integration) - Incremental Integration ✅ COMPLETE
   - Wire Phase 1 & 2 to live backend
   - Replace mocks with real data
   - Critical before moving to Phase 3+

**Tier 3 (Content Management)** - Build After Integration:🚧 NEXT
4. **Phase 3** (Library) - Option C: Hybrid Power
   - PDF management and scholarly assets
5. **Phase 7** (Ops) - Option A: Clean & Fast
   - System health and monitoring
   - Can be developed in parallel with Phase 3

**Tier 4 (Advanced Features)** - Build After Core:
6. **Phase 6** (RAG Interface) - Option C: Hybrid Power
   - Depends on Phase 2 & 3 for full power
7. **Phase 4** (Cortex/Knowledge Base) - Option C: Hybrid Power
   - Complex, can be developed independently
8. **Phase 5** (Planner) - Option A: Clean & Fast
   - Simpler, can be added anytime

**Tier 5 (Integration & Management)** - Build Last:
9. **Phase 8** (MCP Client) - Option C: Hybrid Power
   - Requires all other phases to be valuable
10. **Phase 9** (Content Curation) - Option A: Clean & Fast
    - Admin/power user feature
11. **Phase 10** (Taxonomy Management) - Option A: Clean & Fast
    - Admin/power user feature
12. **Phase 11** (Social Authentication) - Option A: Clean & Fast
    - Simple enhancement, can be added anytime


### Why "Hybrid Power" (Option C) for Most Phases?

**Balanced Approach**:
- Professional polish without over-engineering
- Strategic use of animations where they add value
- Leverages all 3 MCP servers effectively
- Manageable complexity
- Good performance

**MCP Server Usage**:
- **magic-mcp**: Generate initial component structure (saves time)
- **shadcn-ui**: Core UI primitives (reliability)
- **magic-ui**: Strategic animations and effects (delight)

### Backend Work Needed

**Before Phase 2**:
- Code embeddings API
- Node2Vec graph summaries

**Before Phase 3**:
- PDF ingestion API
- PDF chunking service
- Vector similarity for auto-linking

**Before Phase 4**:
- Graph computation API
- Cluster detection
- Dependency analysis

**Before Phase 5**:
- Multi-hop MCP agent
- Architecture doc parsing

**Before Phase 8**:
- MCP server implementation
- Tool definitions

**Before Phase 10**:
- OAuth2 credentials configuration (Google, GitHub)

### API Endpoint Coverage

**Total Backend Endpoints**: 90+
**Mapped to Frontend Phases**: 90+ (100% coverage)

**New Endpoints Utilized**:
- Phase 2: +10 endpoints (annotation search/export, quality analytics)
- Phase 3: +5 endpoints (batch operations, similar collections)
- Phase 4: +10 endpoints (LBD, entity extraction, graph embeddings)
- Phase 6: +8 endpoints (advanced RAG, recommendations, evaluation)
- Phase 7: +13 endpoints (detailed monitoring, sparse embeddings)
- Phase 8: +1 endpoint (session details)
- Phase 9: +9 endpoints (entire curation module)
- Phase 10: +7 endpoints (taxonomy + authority modules)
- Phase 11: +5 endpoints (OAuth2 social login)

**Total New Endpoints**: 68 previously unused endpoints now mapped

---

## Next Steps

1. **Choose Phase 1 Option** (Recommended: Option C - Hybrid Power)
2. **I'll create the full spec** (requirements.md, design.md, tasks.md)
3. **Start implementation** with the new UI MCP servers
4. **Iterate through phases** building the "Second Brain"

### Implementation Milestones

**Milestone 1: Foundation (Phases 1, 7)**
- Core workbench layout
- Basic ops dashboard
- ~6 API endpoints

**Milestone 2: Content Management (Phases 2, 3)**
- Living code editor
- Living library
- ~45 API endpoints

**Milestone 3: Intelligence (Phases 4, 5, 6)**
- Knowledge graph
- Implementation planner
- RAG interface
- ~35 API endpoints

**Milestone 4: Integration & Management (Phases 8, 9, 10, 11)**
- MCP client
- Content curation
- Taxonomy management
- Social authentication
- ~30 API endpoints

**Total**: 11 phases, 90+ API endpoints, 100% backend coverage

**Ready to start Phase 1?** Let me know which option you prefer!
