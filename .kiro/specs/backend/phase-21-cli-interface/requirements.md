# Phase 21: Universal CLI Interface - Requirements

## Overview

Create a comprehensive command-line interface (CLI) that exposes all Pharos backend functionality, enabling developers to interact with the system without a GUI. This CLI will support scripting, automation, CI/CD integration, and power-user workflows.

## User Stories

### Core CLI Experience

**As a developer**, I want to:
- Install Pharos CLI via pip/pipx so I can use it globally
- Configure API endpoint and authentication once so subsequent commands work seamlessly
- Get helpful command suggestions and autocomplete so I can discover features
- See progress indicators for long operations so I know the CLI is working
- Get structured output (JSON, table, tree) so I can pipe to other tools

**As a researcher**, I want to:
- Add papers and code from the command line so I can batch import resources
- Search my knowledge base from terminal so I can stay in my workflow
- Annotate resources via CLI so I can script my reading workflow
- Export collections to files so I can share with collaborators

**As a DevOps engineer**, I want to:
- Integrate Pharos into CI/CD pipelines so code analysis runs automatically
- Monitor system health via CLI so I can script alerts
- Backup and restore data so I can manage deployments
- Run batch operations so I can process large datasets

## Functional Requirements

### 1. Installation & Setup

**FR-1.1**: CLI installable via `pip install pharos-cli` or `pipx install pharos-cli`
**FR-1.2**: Support Python 3.8+ on Windows, macOS, Linux
**FR-1.3**: Configuration wizard on first run (`pharos init`)
**FR-1.4**: Store config in `~/.pharos/config.yaml` or `~/.config/pharos/config.yaml`
**FR-1.5**: Support multiple profiles (dev, staging, prod)
**FR-1.6**: Environment variable overrides for CI/CD (`PHAROS_API_URL`, `PHAROS_API_KEY`)

### 2. Authentication

**FR-2.1**: Support API key authentication (`pharos auth login --api-key`)
**FR-2.2**: Support OAuth2 flow for interactive login (`pharos auth login --oauth`)
**FR-2.3**: Token refresh handling (automatic)
**FR-2.4**: Logout command (`pharos auth logout`)
**FR-2.5**: Show current user (`pharos auth whoami`)

### 3. Resource Management

**FR-3.1**: Create resource from file (`pharos resource add <file>`)
**FR-3.2**: Create resource from URL (`pharos resource add --url <url>`)
**FR-3.3**: Create resource from stdin (`cat file.py | pharos resource add --stdin`)
**FR-3.4**: List resources with filters (`pharos resource list --type code --language python`)
**FR-3.5**: Get resource details (`pharos resource get <id>`)
**FR-3.6**: Update resource metadata (`pharos resource update <id> --title "New Title"`)
**FR-3.7**: Delete resource (`pharos resource delete <id>`)
**FR-3.8**: Batch import from directory (`pharos resource import ./papers/ --recursive`)
**FR-3.9**: Export resource content (`pharos resource export <id> --output file.pdf`)

### 4. Search

**FR-4.1**: Keyword search (`pharos search "machine learning"`)
**FR-4.2**: Semantic search (`pharos search --semantic "neural networks"`)
**FR-4.3**: Hybrid search with weight (`pharos search "AI" --hybrid --weight 0.7`)
**FR-4.4**: Filter by type, language, quality (`pharos search "python" --type code --min-quality 0.8`)
**FR-4.5**: Output formats: table, JSON, IDs only (`--format json`)
**FR-4.6**: Pagination support (`--page 2 --per-page 50`)
**FR-4.7**: Save search results to file (`pharos search "AI" --output results.json`)

### 5. Collections

**FR-5.1**: Create collection (`pharos collection create "ML Papers"`)
**FR-5.2**: List collections (`pharos collection list`)
**FR-5.3**: Add resource to collection (`pharos collection add <collection-id> <resource-id>`)
**FR-5.4**: Remove resource from collection (`pharos collection remove <collection-id> <resource-id>`)
**FR-5.5**: Show collection contents (`pharos collection show <id>`)
**FR-5.6**: Delete collection (`pharos collection delete <id>`)
**FR-5.7**: Export collection (`pharos collection export <id> --format zip`)

### 6. Annotations

**FR-6.1**: Create annotation (`pharos annotate <resource-id> --text "Important" --start 100 --end 200`)
**FR-6.2**: List annotations for resource (`pharos annotate list <resource-id>`)
**FR-6.3**: Search annotations (`pharos annotate search "TODO"`)
**FR-6.4**: Delete annotation (`pharos annotate delete <id>`)
**FR-6.5**: Export annotations to Markdown (`pharos annotate export <resource-id> --format md`)
**FR-6.6**: Batch annotate from file (`pharos annotate import annotations.json`)

### 7. Knowledge Graph

**FR-7.1**: Show graph statistics (`pharos graph stats`)
**FR-7.2**: Find citations for resource (`pharos graph citations <resource-id>`)
**FR-7.3**: Find related resources (`pharos graph related <resource-id> --limit 10`)
**FR-7.4**: Export graph data (`pharos graph export --format graphml`)
**FR-7.5**: Detect contradictions (`pharos graph contradictions`)
**FR-7.6**: Find hidden connections (`pharos graph discover --source <id> --target <id>`)
**FR-7.7**: Show centrality scores (`pharos graph centrality --top 20`)

### 8. Quality Assessment

**FR-8.1**: Get quality score (`pharos quality score <resource-id>`)
**FR-8.2**: List quality outliers (`pharos quality outliers --threshold 0.3`)
**FR-8.3**: Recompute quality scores (`pharos quality recompute <resource-id>`)
**FR-8.4**: Quality report for collection (`pharos quality report <collection-id>`)

### 9. Taxonomy & Classification

**FR-9.1**: List taxonomy nodes (`pharos taxonomy list`)
**FR-9.2**: Classify resource (`pharos taxonomy classify <resource-id>`)
**FR-9.3**: Train classifier (`pharos taxonomy train`)
**FR-9.4**: Show classification distribution (`pharos taxonomy stats`)

### 10. Recommendations

**FR-10.1**: Get recommendations for user (`pharos recommend --user <user-id> --limit 10`)
**FR-10.2**: Get similar resources (`pharos recommend similar <resource-id>`)
**FR-10.3**: Explain recommendation (`pharos recommend explain <resource-id> --for-user <user-id>`)

### 11. Code Analysis

**FR-11.1**: Analyze code file (`pharos code analyze <file>`)
**FR-11.2**: Extract AST (`pharos code ast <file> --format json`)
**FR-11.3**: Find dependencies (`pharos code deps <file>`)
**FR-11.4**: Chunk code file (`pharos code chunk <file> --strategy ast`)
**FR-11.5**: Batch analyze repository (`pharos code scan ./repo/ --recursive`)

### 12. RAG & Chat

**FR-12.1**: Ask question (`pharos ask "How does authentication work?"`)
**FR-12.2**: Chat mode (`pharos chat` - interactive REPL)
**FR-12.3**: Show evidence sources (`pharos ask "..." --show-sources`)
**FR-12.4**: Specify retrieval strategy (`pharos ask "..." --strategy graphrag`)

### 13. System Management

**FR-13.1**: Health check (`pharos health`)
**FR-13.2**: System statistics (`pharos stats`)
**FR-13.3**: Database backup (`pharos backup --output backup.sql`)
**FR-13.4**: Database restore (`pharos restore backup.sql`)
**FR-13.5**: Clear cache (`pharos cache clear`)
**FR-13.6**: Run migrations (`pharos migrate`)
**FR-13.7**: Show version (`pharos version`)

### 14. Batch Operations

**FR-14.1**: Batch delete resources (`pharos batch delete --ids 1,2,3`)
**FR-14.2**: Batch update metadata (`pharos batch update --file updates.json`)
**FR-14.3**: Batch export (`pharos batch export --collection <id> --output ./exports/`)
**FR-14.4**: Dry-run mode for batch operations (`--dry-run`)

### 15. Output Formatting

**FR-15.1**: JSON output (`--format json`)
**FR-15.2**: Table output (`--format table`)
**FR-15.3**: Tree output for hierarchical data (`--format tree`)
**FR-15.4**: CSV output (`--format csv`)
**FR-15.5**: Quiet mode (IDs only) (`--quiet`)
**FR-15.6**: Verbose mode with debug info (`--verbose`)
**FR-15.7**: Color output (auto-detect TTY) (`--color auto|always|never`)

## Non-Functional Requirements

### Performance

**NFR-1**: Command startup time < 500ms
**NFR-2**: Streaming output for large datasets
**NFR-3**: Progress bars for operations > 2 seconds
**NFR-4**: Parallel execution for batch operations
**NFR-5**: Efficient pagination (don't load all results)

### Usability

**NFR-6**: Shell completion (bash, zsh, fish)
**NFR-7**: Helpful error messages with suggestions
**NFR-8**: Consistent command structure (noun-verb pattern)
**NFR-9**: Interactive prompts for destructive operations
**NFR-10**: Man pages and `--help` for all commands

### Compatibility

**NFR-11**: Works with existing Pharos API (no backend changes)
**NFR-12**: Backward compatible with config format
**NFR-13**: Graceful degradation for older API versions
**NFR-14**: Cross-platform path handling

### Security

**NFR-15**: Secure credential storage (keyring integration)
**NFR-16**: No credentials in command history
**NFR-17**: TLS/SSL for API communication
**NFR-18**: Token expiration handling

## Acceptance Criteria

### AC-1: Installation
- [ ] CLI installable via pip/pipx
- [ ] Works on Windows, macOS, Linux
- [ ] `pharos --version` shows version
- [ ] `pharos --help` shows command list

### AC-2: Configuration
- [ ] `pharos init` creates config file
- [ ] Config supports multiple profiles
- [ ] Environment variables override config
- [ ] `pharos config show` displays current config

### AC-3: Authentication
- [ ] API key authentication works
- [ ] OAuth2 flow works (interactive)
- [ ] Token refresh is automatic
- [ ] `pharos auth whoami` shows current user

### AC-4: Core Operations
- [ ] All 13 modules have CLI commands
- [ ] CRUD operations work for all resources
- [ ] Search with all filter options works
- [ ] Batch operations work with progress bars

### AC-5: Output Formatting
- [ ] JSON output is valid and parseable
- [ ] Table output is readable
- [ ] CSV output works with Excel
- [ ] Quiet mode outputs IDs only

### AC-6: Error Handling
- [ ] Network errors show helpful messages
- [ ] API errors display status code and message
- [ ] Invalid arguments show usage help
- [ ] Destructive operations require confirmation

### AC-7: Documentation
- [ ] README with installation instructions
- [ ] Command reference documentation
- [ ] Example workflows
- [ ] Shell completion instructions

### AC-8: Testing
- [ ] Unit tests for all commands
- [ ] Integration tests with mock API
- [ ] E2E tests with real backend
- [ ] CI/CD pipeline for releases

## Out of Scope

- ❌ GUI or TUI (terminal UI) - CLI only
- ❌ Built-in text editor - use external editor
- ❌ Real-time collaboration features
- ❌ Embedded database - always connects to API
- ❌ Plugin system - core functionality only
- ❌ Custom scripting language - use shell scripts

## Success Metrics

- **Adoption**: 30% of users try CLI within 3 months
- **Usage**: 20% of API calls come from CLI
- **Satisfaction**: 4.5/5 rating from CLI users
- **Performance**: 95% of commands complete < 2s
- **Reliability**: < 1% error rate for valid commands

## Dependencies

- Existing Pharos API (all modules)
- Python 3.8+ ecosystem
- Click or Typer for CLI framework
- Rich for beautiful terminal output
- Requests or httpx for API calls

## Timeline Estimate

- **Week 1-2**: CLI framework setup, auth, config
- **Week 3-4**: Resource, search, collection commands
- **Week 5-6**: Annotations, graph, quality commands
- **Week 7-8**: Code analysis, RAG, system commands
- **Week 9-10**: Output formatting, shell completion, docs
- **Week 11-12**: Testing, polish, release

**Total**: 12 weeks (3 months)

## Related Documentation

- [Tech Stack](../../../.kiro/steering/tech.md)
- [API Documentation](../../../backend/docs/api/overview.md)
- [Architecture Overview](../../../backend/docs/architecture/overview.md)
