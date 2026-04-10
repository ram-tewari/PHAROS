# Frontend Documentation Index

## Quick Navigation

| Need | Read |
|------|------|
| Project history | [History](history/) |
| System architecture | [Architecture](architecture/) |
| Development setup | [Setup Guide](guides/setup.md) |
| Testing strategies | [Testing Guide](guides/testing.md) |
| API integration | [API Client](api/client.md) |

## Documentation Structure

```
frontend/docs/
├── index.md                    # This file
├── history/                    # Project History
│   ├── phase0-fresh-start.md   # Clean slate and 8-phase roadmap
│   ├── phase1-workbench.md     # Foundation implementation
│   └── auth-shutdown.md        # Temporary authentication bypass
├── architecture/               # System Architecture
│   ├── overview.md             # High-level architecture
│   ├── routing.md              # TanStack Router setup
│   ├── state-management.md     # Zustand stores
│   └── component-patterns.md   # Component design patterns
├── guides/                     # Developer Guides
│   ├── setup.md                # Installation & environment
│   ├── development.md          # Development workflow
│   ├── testing.md              # Testing strategies
│   └── mcp-servers.md          # UI MCP server usage
└── api/                        # API Integration
    ├── client.md               # API client setup
    ├── authentication.md       # Auth flow (currently bypassed)
    └── endpoints.md            # Backend endpoint reference
```

## Project History

Evolution of the Pharos frontend:

- [Phase 0: Fresh Start](history/phase0-fresh-start.md) - Clean slate and 8-phase roadmap (January 2026)
- [Phase 1: Workbench Navigation](history/phase1-workbench.md) - Foundation implementation (January 22, 2026) ✅
- [Auth Shutdown](history/auth-shutdown.md) - Temporary authentication bypass for Phase 1 development

## Architecture

System design and technical decisions:

- [Architecture Overview](architecture/overview.md) - High-level system design
- [Routing](architecture/routing.md) - TanStack Router configuration
- [State Management](architecture/state-management.md) - Zustand stores
- [Component Patterns](architecture/component-patterns.md) - Component design patterns

## Developer Guides

Getting started and development workflows:

- [Setup Guide](guides/setup.md) - Installation and environment setup
- [Development Guide](guides/development.md) - Development workflow
- [Testing Guide](guides/testing.md) - Testing strategies and patterns
- [MCP Servers Guide](guides/mcp-servers.md) - UI component generation with MCP

## API Integration

Backend API integration:

- [API Client](api/client.md) - API client setup and usage
- [Authentication](api/authentication.md) - Auth flow (currently bypassed)
- [Endpoints](api/endpoints.md) - Backend endpoint reference

## Current Status

### Phase 1: Core Workbench & Navigation ✅ COMPLETE

**Implemented Features**:
- ✅ Workbench layout with collapsible sidebar
- ✅ Global command palette (Cmd+K)
- ✅ Repository switcher
- ✅ Theme system (light/dark/system)
- ✅ Keyboard navigation
- ✅ Responsive design
- ✅ Comprehensive test suite

**Key Components**:
- `WorkbenchLayout` - Main layout container
- `WorkbenchSidebar` - Navigation sidebar
- `WorkbenchHeader` - Top header bar
- `CommandPalette` - Global command interface
- `RepositorySwitcher` - Repository selection
- `ThemeToggle` - Theme switcher

**State Management**:
- `workbench` store - Sidebar and layout state
- `theme` store - Theme preferences
- `repository` store - Repository selection
- `command` store - Command palette state

### Authentication Status ⚠️ TEMPORARILY BYPASSED

Authentication is temporarily disabled to focus on core UI development.

**See**: [Auth Shutdown](history/auth-shutdown.md) for details

### Next Phase: Phase 2 - Living Code Editor

**Planned Features**:
- Monaco editor integration
- AST-based semantic chunking visualization
- Quality badges
- Annotation gutter
- Hover cards with Node2Vec summaries
- Reference overlay

**Status**: Spec in progress

## Technology Stack

### Core Framework
- **React 18** - UI library
- **TypeScript 5** - Type safety
- **Vite 5** - Build tool and dev server
- **TanStack Router** - Type-safe routing

### State Management
- **Zustand** - Lightweight state management
- **TanStack Query** - Server state (planned)

### UI Components
- **shadcn/ui** - Core UI primitives (via MCP)
- **magic-ui** - Animations and effects (via MCP)
- **lucide-react** - Icon library
- **cmdk** - Command palette
- **Framer Motion** - Animations

### Styling
- **Tailwind CSS** - Utility-first CSS
- **CSS Modules** - Component-scoped styles

### Testing
- **Vitest** - Unit testing
- **React Testing Library** - Component testing
- **fast-check** - Property-based testing

### MCP Servers
- `@jpisnice/shadcn-ui-mcp-server` - Core UI components
- `@magicuidesign/mcp` - Animations and effects
- `@21st-dev/magic-mcp` - AI component generation

## Interactive Development

### Development Server

```bash
cd frontend
npm run dev
```

Frontend runs on `http://localhost:5173`

### Hot Module Replacement

Vite provides instant HMR for:
- React components
- CSS/Tailwind changes
- TypeScript updates

### Browser DevTools

Recommended extensions:
- React Developer Tools
- Redux DevTools (for Zustand)
- TanStack Router DevTools

## Performance Targets

- **Initial render**: < 100ms
- **Sidebar toggle**: < 200ms animation
- **Command palette open**: < 50ms
- **Animation frame rate**: 60fps
- **Initial bundle**: < 200KB (gzipped)

## Accessibility

**WCAG 2.1 AA Compliance**:
- ✅ Keyboard navigation for all features
- ✅ Visible focus indicators
- ✅ Color contrast ≥ 4.5:1
- ✅ Screen reader support
- ✅ Touch-friendly targets (44x44px minimum)

## Related Documentation

### Backend Documentation
- [Backend README](../../backend/README.md)
- [API Documentation](../../backend/docs/index.md)
- [Architecture Overview](../../backend/docs/architecture/overview.md)

### Steering Documentation
- [Product Overview](../../.kiro/steering/product.md)
- [Tech Stack](../../.kiro/steering/tech.md)
- [Repository Structure](../../.kiro/steering/structure.md)

### Specifications
- [Frontend Roadmap](../../.kiro/specs/frontend/ROADMAP.md)
- [Phase 1 Spec](../../.kiro/specs/frontend/phase1-workbench-navigation/)

## Contributing

### Adding New Features

1. Create spec in `.kiro/specs/frontend/[feature-name]/`
2. Write requirements, design, and tasks
3. Implement components and tests
4. Update documentation
5. Submit for review

### Code Style

- Use TypeScript strict mode
- Follow ESLint rules
- Use Prettier for formatting
- Write tests for all features
- Document complex logic

### Testing Requirements

- All components must have unit tests
- Critical paths need integration tests
- Property-based tests for core behaviors
- Accessibility tests for interactive elements

## Questions?

- Check the [guides](guides/) for how-to documentation
- Check the [architecture](architecture/) for system design
- Check the [history](history/) for project evolution
- Ask in team discussions or create an issue

---

**Last Updated**: January 22, 2026
**Maintainer**: Pharos Team
