# Phase 21: Universal CLI Interface - Tasks

## Task Breakdown

### Week 1-2: Foundation & Setup

#### Task 1.1: Project Setup
- [x] Create `pharos-cli` repository structure
- [x] Set up `pyproject.toml` with dependencies
- [x] Configure development tools (black, ruff, mypy, pytest)
- [x] Create initial README with installation instructions
- [x] Set up GitHub Actions for CI/CD
- [x] Create `.gitignore` for Python projects

**Estimated Time**: 4 hours

#### Task 1.2: CLI Framework Setup
- [x] Install and configure Typer
- [x] Create main CLI app in `cli.py`
- [x] Implement version command
- [x] Set up Rich console singleton
- [x] Create basic command structure (groups)
- [x] Test CLI entry point

**Estimated Time**: 6 hours

#### Task 1.3: Configuration Management
- [x] Create `Config` Pydantic model
- [x] Implement config file loading (YAML)
- [x] Implement profile management
- [x] Add environment variable overrides
- [x] Create `pharos init` command
- [x] Create `pharos config show` command
- [x] Write unit tests for config module

**Estimated Time**: 8 hours

#### Task 1.4: Credential Storage
- [x] Integrate keyring library
- [x] Create `KeyringStore` class
- [x] Implement secure API key storage
- [x] Implement API key retrieval
- [x] Handle keyring errors gracefully
- [x] Write unit tests for keyring module

**Estimated Time**: 6 hours

#### Task 1.5: API Client Base
- [x] Create `APIClient` base class
- [x] Implement HTTP methods (GET, POST, PUT, DELETE)
- [x] Add authentication header injection
- [x] Implement error handling
- [x] Add retry logic with exponential backoff
- [x] Create custom exceptions
- [x] Write unit tests with httpx mocks

**Estimated Time**: 10 hours

#### Task 1.6: Authentication Commands
- [x] Implement `pharos auth login --api-key`
- [x] Implement `pharos auth login --oauth` (interactive)
- [x] Implement `pharos auth logout`
- [x] Implement `pharos auth whoami`
- [x] Add token refresh logic
- [x] Write integration tests for auth commands

**Estimated Time**: 10 hours

**Week 1-2 Total**: 44 hours (~5.5 days)

---

### Week 3-4: Core Resource & Search Commands

#### Task 2.1: Resource Client
- [x] Create `ResourceClient` class
- [x] Implement `create()` method
- [x] Implement `list()` method with filters
- [x] Implement `get()` method
- [x] Implement `update()` method
- [x] Implement `delete()` method
- [x] Write unit tests for ResourceClient

**Estimated Time**: 8 hours

#### Task 2.2: Resource Commands - Basic CRUD
- [x] Implement `pharos resource add <file>`
- [x] Implement `pharos resource add --url <url>`
- [x] Implement `pharos resource add --stdin`
- [x] Implement `pharos resource list` with filters
- [x] Implement `pharos resource get <id>`
- [x] Implement `pharos resource update <id>`
- [x] Implement `pharos resource delete <id>` with confirmation
- [x] Write integration tests (33 tests, all passing)

**Estimated Time**: 12 hours
**Status**: COMPLETED ✅

#### Task 2.3: Resource Commands - Batch Operations
- [x] Implement `pharos resource import <dir>` with recursion
- [x] Implement `pharos resource export <id>`
- [x] Add progress bars for batch operations
- [x] Add parallel processing for imports
- [x] Handle errors gracefully (continue on failure)
- [x] Write integration tests (21 tests, all passing)

**Estimated Time**: 10 hours
**Status**: COMPLETED ✅

#### Task 2.4: Search Client
- [x] Create `SearchClient` class
- [x] Implement keyword search
- [x] Implement semantic search
- [x] Implement hybrid search
- [x] Add filter support
- [x] Add pagination support
- [x] Write unit tests

**Estimated Time**: 6 hours
**Status**: COMPLETED ✅

#### Task 2.5: Search Commands
- [x] Implement `pharos search <query>`
- [x] Add `--semantic` flag
- [x] Add `--hybrid` flag with weight option
- [x] Add filter options (type, language, quality)
- [x] Add pagination options
- [x] Add `--output` option to save results
- [x] Write integration tests (32 passed, 1 skipped)

**Estimated Time**: 8 hours
**Status**: COMPLETED ✅

#### Task 2.6: Collection Client & Commands
- [x] Create `CollectionClient` class
- [x] Implement `pharos collection create`
- [x] Implement `pharos collection list`
- [x] Implement `pharos collection show <id>`
- [x] Implement `pharos collection add <collection-id> <resource-id>`
- [x] Implement `pharos collection remove <collection-id> <resource-id>`
- [x] Implement `pharos collection delete <id>`
- [x] Implement `pharos collection export <id>`
- [x] Write tests (50 tests, all passing)

**Estimated Time**: 10 hours
**Status**: COMPLETED ✅

**Week 3-4 Total**: 54 hours (~6.75 days)

---

### Week 5-6: Annotations, Graph & Quality

#### Task 3.1: Annotation Client & Commands
- [x] Create `AnnotationClient` class
- [x] Implement `pharos annotate <resource-id>` (create)
- [x] Implement `pharos annotate list <resource-id>`
- [x] Implement `pharos annotate search <query>`
- [x] Implement `pharos annotate delete <id>`
- [x] Implement `pharos annotate export <resource-id>`
- [x] Implement `pharos annotate import <file>`
- [x] Write tests

**Estimated Time**: 10 hours
**Status**: COMPLETED ✅

#### Task 3.2: Graph Client & Commands
- [x] Create `GraphClient` class
- [x] Implement `pharos graph stats`
- [x] Implement `pharos graph citations <resource-id>`
- [x] Implement `pharos graph related <resource-id>`
- [x] Implement `pharos graph export`
- [x] Implement `pharos graph contradictions`
- [x] Implement `pharos graph discover`
- [x] Implement `pharos graph centrality`
- [x] Write tests

**Estimated Time**: 12 hours
**Status**: COMPLETED ✅

#### Task 3.3: Quality Client & Commands
- [x] Create `QualityClient` class
- [x] Implement `pharos quality score <resource-id>`
- [x] Implement `pharos quality outliers`
- [x] Implement `pharos quality recompute <resource-id>`
- [x] Implement `pharos quality report <collection-id>`
- [x] Add quality visualization (ASCII charts)
- [x] Write tests

**Estimated Time**: 8 hours
**Status**: COMPLETED ✅

#### Task 3.4: Taxonomy Client & Commands
- [x] Create `TaxonomyClient` class
- [x] Implement `pharos taxonomy list`
- [x] Implement `pharos taxonomy classify <resource-id>`
- [x] Implement `pharos taxonomy train`
- [x] Implement `pharos taxonomy stats`
- [x] Write tests

**Estimated Time**: 8 hours
**Status**: COMPLETED ✅

#### Task 3.5: Recommendation Client & Commands
- [x] Create `RecommendationClient` class
- [x] Implement `pharos recommend --user <user-id>` (as `pharos recommend for-user`)
- [x] Implement `pharos recommend similar <resource-id>`
- [x] Implement `pharos recommend explain`
- [x] Write tests (40 tests passing: 12 unit tests + 28 integration tests)

**Estimated Time**: 6 hours
**Status**: COMPLETED ✅

**Week 5-6 Total**: 44 hours (~5.5 days)  
**Status**: ✅ COMPLETE

---

### Week 7-8: Code Analysis, RAG & System Commands

#### Task 4.1: Code Analysis Client & Commands
- [x] Create `CodeClient` class
- [x] Implement `pharos code analyze <file>`
- [x] Implement `pharos code ast <file>`
- [x] Implement `pharos code deps <file>`
- [x] Implement `pharos code chunk <file>`
- [x] Implement `pharos code scan <dir>` (batch)
- [x] Add progress bars for batch operations
- [x] Write tests

**Estimated Time**: 12 hours
**Status**: COMPLETED ✅

#### Task 4.2: RAG Client & Commands
- [x] Create `RAGClient` class
- [x] Implement `pharos ask <question>`
- [x] Add `--show-sources` flag
- [x] Add `--strategy` option (graphrag, hybrid)
- [x] Implement streaming response display
- [x] Write tests

**Estimated Time**: 8 hours
**Status**: COMPLETED ✅

#### Task 4.3: Interactive Chat Mode
- [x] Implement `pharos chat` (REPL)
- [x] Add command history
- [x] Add multi-line input support
- [x] Add `/help`, `/exit`, `/clear` commands
- [x] Add syntax highlighting for code blocks
- [x] Write tests

**Estimated Time**: 10 hours

#### Task 4.4: Health & System Commands
- [x] Create `SystemClient` class
- [x] Implement `pharos health`
- [x] Implement `pharos stats`
- [x] Implement `pharos version`
- [x] Add health check visualization
- [x] Write tests

**Estimated Time**: 6 hours
**Status**: COMPLETED ✅

#### Task 4.5: Backup & Restore Commands
- [x] Implement `pharos backup --output <file>`
- [x] Implement `pharos restore <file>`
- [x] Add progress bars
- [x] Add verification step
- [x] Write tests

**Estimated Time**: 8 hours
**Status**: COMPLETED ✅

#### Task 4.6: Batch Operations
- [x] Implement `pharos batch delete --ids <ids>`
- [x] Implement `pharos batch update --file <file>`
- [x] Implement `pharos batch export --collection <id>`
- [x] Add `--dry-run` flag
- [x] Add parallel processing
- [x] Write tests (36 tests passing)

**Estimated Time**: 10 hours
**Status**: COMPLETED ✅

**Week 7-8 Total**: 54 hours (~6.75 days)  
**Status**: ✅ COMPLETE

---

### Week 9-10: Output Formatting & Polish

#### Task 5.1: JSON Formatter
- [x] Create `JSONFormatter` class
- [x] Implement `format()` method
- [x] Implement `format_list()` method
- [x] Implement `format_error()` method
- [x] Add pretty-printing options
- [x] Write tests

**Estimated Time**: 4 hours
**Status**: COMPLETED ✅

#### Task 5.2: Table Formatter (Rich)
- [x] Create `TableFormatter` class
- [x] Implement table rendering with Rich
- [x] Add column auto-sizing
- [x] Add row truncation for long content
- [x] Add pagination for large tables
- [x] Write tests

**Estimated Time**: 6 hours
**Status**: COMPLETED ✅

#### Task 5.3: Tree Formatter (Rich)
- [x] Create `TreeFormatter` class
- [x] Implement tree rendering for hierarchical data
- [x] Add collapsible branches
- [x] Add color coding
- [x] Write tests

**Estimated Time**: 6 hours
**Status**: COMPLETED ✅

#### Task 5.4: CSV Formatter
- [x] Create `CSVFormatter` class
- [x] Implement CSV output
- [x] Handle nested data (flatten)
- [x] Add Excel compatibility
- [x] Write tests

**Estimated Time**: 4 hours
**Status**: COMPLETED ✅

#### Task 5.5: Progress Indicators
- [x] Create progress bar helpers
- [x] Create spinner helpers
- [x] Add ETA calculation
- [x] Add throughput display (items/sec)
- [x] Write tests

**Estimated Time**: 6 hours
**Status**: COMPLETED ✅

#### Task 5.6: Error Display Enhancement
- [x] Create error display helpers
- [x] Add Rich panels for errors
- [x] Add suggestions for common errors
- [x] Add verbose mode with stack traces
- [x] Write tests

**Estimated Time**: 4 hours
**Status**: COMPLETED ✅

#### Task 5.7: Shell Completion
- [x] Implement bash completion
- [x] Implement zsh completion
- [x] Implement fish completion
- [x] Create installation script
- [x] Test on all shells
- [x] Write documentation

**Estimated Time**: 8 hours
**Status**: COMPLETED ✅

#### Task 5.8: Color & Theme Support
- [x] Implement color detection (TTY)
- [x] Add `--color` option (auto, always, never)
- [x] Add `--no-color` flag
- [x] Support `NO_COLOR` environment variable
- [x] Test on different terminals

**Estimated Time**: 4 hours
**Status**: COMPLETED ✅

#### Task 5.9: Pager Support
- [x] Implement automatic pager for long output
- [x] Support `less`, `more`, `bat`
- [x] Add `--no-pager` flag
- [x] Test on different platforms

**Estimated Time**: 4 hours
**Status**: COMPLETED ✅

**Week 9-10 Total**: 46 hours (~5.75 days)  
**Status**: ✅ COMPLETE

---

### Week 11-12: Testing, Documentation & Release

#### Task 6.1: Comprehensive Testing
- [x] Write unit tests for all modules (target 90% coverage)
- [x] Write integration tests for all commands
- [x] Write E2E tests with real backend
- [x] Add property-based tests (hypothesis)
- [ ] Test on Windows, macOS, Linux
- [ ] Test with different Python versions (3.8, 3.9, 3.10, 3.11, 3.12)

**Estimated Time**: 16 hours
**Status**: PARTIALLY COMPLETE (1255 tests passing, cross-platform testing pending)

#### Task 6.2: Documentation - Installation & Setup
- [x] Write installation guide (pip, pipx, source)
- [x] Write configuration guide
- [x] Write authentication guide
- [x] Add troubleshooting section
- [x] Add FAQ

**Estimated Time**: 6 hours
**Status**: COMPLETED ✅

#### Task 6.3: Documentation - Command Reference
- [x] Document all commands with examples
- [x] Add usage patterns
- [x] Add common workflows
- [x] Generate man pages
- [x] Create cheat sheet

**Estimated Time**: 10 hours
**Status**: COMPLETED ✅

#### Task 6.4: Documentation - Examples & Tutorials
- [x] Write "Getting Started" tutorial
- [x] Write "Batch Operations" tutorial
- [x] Write "CI/CD Integration" tutorial
- [x] Write "Scripting with Pharos CLI" guide
- [x] Add example scripts

**Estimated Time**: 8 hours
**Status**: COMPLETED ✅

#### Task 6.5: Performance Optimization
- [ ] Profile CLI startup time (target: <500ms)
- [ ] Optimize imports (lazy loading)
- [ ] Optimize config loading
- [ ] Add caching where appropriate
- [ ] Benchmark all commands

**Estimated Time**: 6 hours
**Status**: NOT STARTED (Pending profiling)

#### Task 6.6: Security Audit
- [x] Review credential storage
- [x] Review input validation
- [x] Review API communication
- [x] Add security documentation
- [x] Run security scanners (bandit, safety)

**Estimated Time**: 4 hours
**Status**: COMPLETED ✅

#### Task 6.7: Release Preparation
- [ ] Create release checklist
- [ ] Write CHANGELOG.md
- [ ] Update version numbers
- [ ] Create GitHub release
- [ ] Publish to PyPI (test first)
- [ ] Create Docker image (optional)

**Estimated Time**: 6 hours
**Status**: NOT STARTED (Ready for release preparation)

#### Task 6.8: User Feedback & Iteration
- [ ] Create feedback form
- [ ] Set up issue templates
- [ ] Monitor early adopter feedback
- [ ] Fix critical bugs
- [ ] Plan v0.2.0 features

**Estimated Time**: 4 hours
**Status**: NOT STARTED (Post-release activity)

**Week 11-12 Total**: 60 hours (~7.5 days)  
**Status**: ⚠️ PARTIALLY COMPLETE (Testing & documentation done, release preparation pending)

---

## Summary

### Total Estimated Time
- Week 1-2: 44 hours
- Week 3-4: 54 hours
- Week 5-6: 44 hours
- Week 7-8: 54 hours
- Week 9-10: 46 hours
- Week 11-12: 60 hours

**Total**: 302 hours (~38 working days or ~7.5 weeks at 40 hours/week)

### Critical Path
1. Foundation (Config, Auth, API Client) - Weeks 1-2
2. Core Commands (Resource, Search, Collections) - Weeks 3-4
3. Advanced Commands (Annotations, Graph, Quality) - Weeks 5-6
4. Specialized Commands (Code, RAG, System) - Weeks 7-8
5. Polish (Formatting, Completion) - Weeks 9-10
6. Testing & Release - Weeks 11-12

### Milestones

**M1: Alpha Release (Week 4)**
- Basic resource management
- Search functionality
- Collection management
- JSON output only

**M2: Beta Release (Week 8)**
- All command groups implemented
- Multiple output formats
- Shell completion
- Basic documentation

**M3: v1.0 Release (Week 12)**
- Full test coverage
- Complete documentation
- Performance optimized
- Published to PyPI

### Risk Mitigation

**Risk**: OAuth2 flow complexity
**Mitigation**: Start with API key auth, add OAuth2 later

**Risk**: Cross-platform compatibility issues
**Mitigation**: Test early and often on all platforms

**Risk**: API changes breaking CLI
**Mitigation**: Version API client, add compatibility checks

**Risk**: Performance issues with large datasets
**Mitigation**: Implement streaming and pagination early

### Dependencies

**External**:
- Pharos backend API must be stable
- PyPI account for publishing
- GitHub Actions for CI/CD

**Internal**:
- API documentation must be complete
- Backend endpoints must be tested
- Authentication system must be working

### Success Criteria

- [x] All 13 module groups have CLI commands
- [x] 90%+ test coverage (1255 tests passing)
- [ ] <500ms startup time (needs profiling)
- [ ] Works on Windows, macOS, Linux (needs cross-platform testing)
- [ ] Published to PyPI
- [x] Documentation complete
- [ ] 10+ early adopters using CLI
- [ ] <5 critical bugs in first month

## Related Documentation

- [Requirements](requirements.md)
- [Design](design.md)
- [API Documentation](../../../backend/docs/api/overview.md)
- [Tech Stack](../../../.kiro/steering/tech.md)
