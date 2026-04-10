# Pharos Frontend Documentation

**Version**: 2.0
**Status**: Phase 1 Complete ✅
**Last Updated**: January 22, 2026

## Overview

Pharos's frontend is a "Second Brain" interface for code and knowledge management. Built with React 18, TypeScript, and TanStack Router, it provides an intelligent workspace for developers to explore, annotate, and understand their codebases.

## Documentation Structure

```
frontend/docs/
├── README.md (this file)           # Documentation hub
├── history/                        # Project history
│   ├── phase0-fresh-start.md       # Clean slate and roadmap
│   ├── phase1-workbench.md         # Foundation implementation
│   └── auth-shutdown.md            # Temporary auth bypass
├── architecture/                   # System architecture
│   ├── overview.md                 # High-level architecture
│   ├── routing.md                  # TanStack Router setup
│   ├── state-management.md         # Zustand stores
│   └── component-patterns.md       # Component design patterns
├── guides/                         # Developer guides
│   ├── setup.md                    # Getting started
│   ├── development.md              # Development workflow
│   ├── testing.md                  # Testing strategies
│   └── mcp-servers.md              # UI MCP server usage
└── api/                            # API integration
    ├── client.md                   # API client setup
    ├── authentication.md           # Auth flow (currently bypassed)
    └── endpoints.md                # Backend endpoint reference
```

## Quick Links

### Getting Started
- [Setup Guide](guides/setup.md) - Install and run the frontend
- [Development Guide](guides/development.md) - Development workflow
- [Architecture Overview](architecture/overview.md) - System design

### Project History
- [Phase 0: Fresh Start](history/phase0-fresh-start.md) - Clean slate and 8-phase roadmap
- [Phase 1: Workbench Navigation](history/phase1-workbench.md) - Foundation implementation
- [Auth Shutdown](history/auth-shutdown.md) - Temporary authentication bypass

### Technical Details
- [Routing](architecture/routing.md) - TanStack Router configuration
- [State Management](architecture/state-management.md) - Zustand stores
- [Testing](guides/testing.md) - Unit, integration, and property-based tests
- [MCP Servers](guides/mcp-servers.md) - UI component generation

## Current Status

### Phase 1: Core Workbench & Navigation ✅ COMPLETE

**Implemented Features**:
- ✅ Workbench layout with collapsible sidebar
- ✅ Global command palette (Cmd+K)
- ✅ Repository switcher
- ✅ Theme system (light/dark/system)
- ✅ Keyboard navigation
- ✅ Responsive design
- ✅ Comprehensive test suite (100% passing)

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

**Current State**: Authentication is temporarily disabled to focus on core UI development.

**What's Bypassed**:
- Login page redirects directly to `/repositories`
- No token validation
- No OAuth flow
- No protected routes

**What's Preserved**:
- Auth provider structure
- API client with auth headers
- OAuth callback route
- Login page component

**Re-enable**: See [Auth Shutdown](history/auth-shutdown.md) for details

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

## Development Workflow

### Running the Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173`

### Running Tests

```bash
# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage

# Run specific test file
npm test -- WorkbenchLayout.test.tsx
```

### Building for Production

```bash
npm run build
npm run preview
```

## Key Concepts

### Workbench Architecture

The workbench is the primary UI container that provides:
- **Sidebar Navigation**: Six module links (Repositories, Cortex, Library, Planner, Wiki, Ops)
- **Command Palette**: Global keyboard-driven interface (Cmd+K)
- **Repository Context**: Current repository selection
- **Theme System**: Light/dark/system modes

### State Management Pattern

We use Zustand for client state with a clear separation:
- **UI State**: Sidebar collapsed, command palette open
- **User Preferences**: Theme, repository selection
- **Command State**: Recent commands, search query

### Component Patterns

- **Layouts**: Full-page containers (WorkbenchLayout)
- **Components**: Reusable UI elements (CommandPalette)
- **UI Primitives**: Base components from shadcn/ui
- **Stores**: Zustand state management

### Testing Strategy

- **Property-Based Tests**: Universal behaviors (6 properties)
- **Unit Tests**: Component rendering and interactions
- **Integration Tests**: Full user workflows
- **Accessibility Tests**: WCAG 2.1 AA compliance

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

## Backend Integration

### API Client

The frontend uses a centralized API client (`src/core/api/client.ts`) that:
- Handles authentication headers (when enabled)
- Provides type-safe request/response handling
- Manages error handling
- Supports request cancellation

### Backend Dependencies

**Phase 1 Requirements**:
- ✅ Authentication endpoints (bypassed)
- ⚠️ Repository listing endpoint (mocked)
- ⚠️ Repository selection endpoint (mocked)

**Future Phases**:
- Code embeddings API
- PDF ingestion API
- Graph computation API
- RAG pipeline API

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

## Troubleshooting

### Common Issues

**Build Errors**:
- Clear `node_modules` and reinstall: `rm -rf node_modules && npm install`
- Clear Vite cache: `rm -rf node_modules/.vite`

**Test Failures**:
- Run tests in isolation: `npm test -- --no-coverage`
- Check for async timing issues
- Verify mock data matches expectations

**Routing Issues**:
- Check TanStack Router configuration
- Verify route file naming conventions
- Check for circular dependencies

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

## Questions?

- Check the [guides](guides/) for how-to documentation
- Check the [architecture](architecture/) for system design
- Check the [history](history/) for project evolution
- Ask in team discussions or create an issue

---

**Last Updated**: January 22, 2026
**Maintainer**: Pharos Team
