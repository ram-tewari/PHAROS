# Steering Documentation

Project-level context and guidelines for Pharos.

## Purpose

Steering docs provide high-level context for AI agents and developers without loading large implementation files. They serve as a "map" to the codebase and establish project boundaries.

## Documentation Layers

### Quick Reference (Steering Docs)
**Purpose**: Lightweight, focused guidance for AI agents and daily development
**Token Budget**: 2-8KB per file
**Update Frequency**: With every significant code change

- `product.md` - What we're building (vision, use cases, roadmap)
- `tech.md` - How we're building it (stack, architecture, commands)
- `structure.md` - Where things are (repo map, navigation)
- `admin-credentials.md` - Production secrets and access
- `frontend-polish.md` - UI/UX standards
- `issue-tracking.md` - Issue management process

### Deep Dive (NotebookLM Docs)
**Purpose**: Comprehensive technical documentation for NotebookLM/Gemini
**Token Budget**: 20-50KB per file
**Update Frequency**: At major milestones (phases complete)

Located in `notebooklm/`:
- **File 1**: Complete project overview (what, who, why)
- **File 2**: System architecture (cloud/edge split, modules, event bus)
- **File 3**: Data model & module reference (30+ tables, 14 modules)
- **File 4**: Ingestion & search pipelines (how data flows)
- **File 5**: API catalog & deployment (100+ endpoints, operations)
- **File 6**: Evolution & history (21+ phases, what survived, what was cut)

### When to Use Which

| Task | Use Steering Docs | Use NotebookLM Docs |
|------|------------------|---------------------|
| Quick lookup | ✅ | ❌ |
| AI agent context | ✅ | ❌ |
| Daily development | ✅ | ❌ |
| Onboarding | ⚠️ Start here | ✅ Then deep dive |
| Architecture decisions | ⚠️ Overview | ✅ Full rationale |
| Historical context | ❌ | ✅ |
| API reference | ⚠️ Key endpoints | ✅ Complete catalog |
| Operational runbooks | ⚠️ Common tasks | ✅ Full procedures |

## Files

### `product.md` - Product Vision
**When to read**: Understanding what we're building and why

Contains:
- Product purpose and value propositions
- Target users and use cases
- Explicit non-goals (what we're NOT building)
- Success metrics and roadmap

**Use cases**:
- New contributor onboarding
- Feature prioritization decisions
- Scope boundary questions
- Product direction discussions

### `tech.md` - Technical Stack
**When to read**: Understanding how we're building it

Contains:
- Complete technology inventory
- Architecture patterns and constraints
- Performance requirements
- Common development commands
- Environment configuration

**Use cases**:
- Technology choice questions
- Performance requirement checks
- Development environment setup
- Command reference

### `structure.md` - Repository Map
**When to read**: Finding where things are

Contains:
- Visual repository structure
- Truth sources for different concerns
- "How to find X" guides
- Documentation hierarchy
- Migration status

**Use cases**:
- Navigating the codebase
- Finding relevant documentation
- Understanding component relationships
- Locating implementation files

### `frontend-polish.md` - UI/UX Standards
**When to read**: Implementing or reviewing frontend features

Contains:
- Comprehensive visual design system (colors, typography, spacing)
- Component-level excellence guidelines (forms, buttons, cards, tables)
- Accessibility and responsive design standards
- Animation and micro-interaction patterns
- Performance optimization techniques
- Pharos-specific enhancements for each phase

**Use cases**:
- Frontend feature implementation
- UI/UX review and polish
- Design system consistency checks
- Accessibility compliance verification

## Documentation Hierarchy

```
┌─────────────────────────────────────────────────────────┐
│ Level 1: Steering Docs (High-Level Context)            │
│ ├── AGENTS.md - Routing rules                          │
│ ├── product.md - What we're building                   │
│ ├── tech.md - How we're building it                    │
│ ├── frontend-polish.md - UI/UX standards               │
│ └── structure.md - Where things are                    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Level 2: Feature Specs (Feature Planning)              │
│ ├── requirements.md - User stories & criteria          │
│ ├── design.md - Technical architecture                 │
│ └── tasks.md - Implementation checklist                │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Level 3: Technical Docs (Deep Dives)                   │
│ ├── API_DOCUMENTATION.md - Complete API reference      │
│ ├── ARCHITECTURE_DIAGRAM.md - System architecture      │
│ └── DEVELOPER_GUIDE.md - Development workflows         │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Level 4: Implementation (Code & Details)               │
│ ├── Module READMEs - Module-specific docs              │
│ ├── Service files - Business logic                     │
│ └── Component READMEs - Component docs                 │
└─────────────────────────────────────────────────────────┘
```

## Usage Patterns

### For AI Agents

**Starting a new task**:
1. Read `AGENTS.md` for routing rules
2. Check `structure.md` to locate relevant files
3. Load only files needed for current task
4. Reference other docs by path

**Working on a feature**:
1. Load feature spec (requirements + design)
2. Reference steering docs for context
3. Load implementation files as needed
4. Close completed work

**Answering questions**:
1. Check steering docs first
2. If not found, check technical docs
3. If still not found, check implementation
4. Ask user if still unclear

### For Developers

**Getting started**:
1. Read `product.md` for vision
2. Read `tech.md` for stack
3. Read `structure.md` for navigation
4. Dive into relevant specs

**Implementing features**:
1. Start with feature spec
2. Reference steering docs for constraints
3. Follow technical docs for patterns
4. Update docs as you go

**Reviewing code**:
1. Check against requirements in spec
2. Verify tech stack compliance
3. Ensure proper structure
4. Update docs if needed

## Token Budget Guidelines

| Task Type | Recommended Approach |
|-----------|---------------------|
| Quick question | Load steering doc only (~2-8KB) |
| Feature planning | Load spec + steering (~15-25KB) |
| Implementation | Load spec + relevant files (~30-50KB) |
| Architecture review | Load steering + technical docs (~40-60KB) |

## Maintenance

### When to Update

**`product.md`**:
- Product vision changes
- New user segments identified
- Non-goals clarified
- Success metrics updated

**`tech.md`**:
- Technology choices change
- New tools adopted
- Performance requirements updated
- Commands added/changed

**`structure.md`**:
- Major refactoring completed
- New modules added
- Documentation reorganized
- Migration milestones reached

### Update Frequency

- **Steering docs**: Monthly or on major changes
- **Feature specs**: Per feature lifecycle
- **Technical docs**: Per release or major change
- **Implementation docs**: Continuous with code changes

## Related Documentation

- [Agent Routing Rules](../../AGENTS.md)
- [Kiro Configuration](../README.md)
- [Spec Organization](../specs/README.md)
- [Backend Developer Guide](../../backend/docs/DEVELOPER_GUIDE.md)
- [API Documentation](../../backend/docs/API_DOCUMENTATION.md)
