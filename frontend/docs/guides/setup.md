# Development Setup Guide

Installation and environment configuration for Pharos Frontend.

> **Phase 1 Complete**: Pharos frontend now has a complete workbench layout with command palette, sidebar navigation, and theme system.

## Prerequisites

- Node.js 18+ or higher
- npm 9+ or pnpm 8+
- Git
- Modern browser (Chrome, Firefox, Safari, Edge)
- 4GB RAM minimum
- 1GB free disk space

## Installation Steps

### 1. Clone the Repository

```bash
git clone <repository-url>
cd frontend
```

### 2. Install Dependencies

```bash
npm install
```

Or with pnpm:
```bash
pnpm install
```

### 3. Configure Environment

Create a `.env` file in the frontend directory:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```bash
# API Configuration
VITE_API_BASE_URL=http://localhost:8000
VITE_API_TIMEOUT=30000

# Authentication (currently bypassed)
VITE_AUTH_ENABLED=false

# Feature Flags
VITE_ENABLE_ANALYTICS=false
VITE_ENABLE_ERROR_TRACKING=false
```

### 4. Start Development Server

```bash
npm run dev
```

The frontend will be available at `http://localhost:5173`

## Verify Installation

### Check Development Server

Open in browser:
- Frontend: http://localhost:5173

You should see the login page, which immediately redirects to `/repositories`

### Verify Workbench

After redirect, you should see:
- ✅ Sidebar with 6 navigation items
- ✅ Header with repository switcher and theme toggle
- ✅ Command palette trigger (Cmd+K)
- ✅ Responsive layout

### Test Keyboard Shortcuts

- **Cmd/Ctrl + K**: Open command palette
- **Cmd/Ctrl + B**: Toggle sidebar
- **Cmd/Ctrl + Shift + P**: Open command palette

### Test Theme Switching

1. Click theme toggle in header
2. Select Light/Dark/System
3. Theme should change immediately

### Run Tests

```bash
npm test
```

All tests should pass:
```
✓ stores/workbench.test.ts (3 tests)
✓ stores/theme.test.ts (4 tests)
✓ layouts/WorkbenchLayout.test.tsx (5 tests)
✓ layouts/WorkbenchSidebar.test.tsx (4 tests)
✓ components/CommandPalette.test.tsx (6 tests)
✓ components/RepositorySwitcher.test.tsx (3 tests)
✓ lib/hooks/useGlobalKeyboard.test.ts (3 tests)
```

## Understanding the Project Structure

### Phase 1 Architecture

Pharos frontend uses a **component-based architecture** with clear separation of concerns:

```
frontend/src/
├── app/                    # Application setup
│   └── providers/          # Context providers
│       ├── ThemeProvider.tsx
│       └── AuthProvider.tsx (preserved)
├── layouts/                # Layout components
│   ├── WorkbenchLayout.tsx
│   ├── WorkbenchSidebar.tsx
│   ├── WorkbenchHeader.tsx
│   └── navigation-config.ts
├── components/             # Reusable components
│   ├── CommandPalette.tsx
│   ├── RepositorySwitcher.tsx
│   ├── ThemeToggle.tsx
│   └── ui/                 # UI primitives (shadcn)
├── stores/                 # Zustand state management
│   ├── workbench.ts
│   ├── theme.ts
│   ├── repository.ts
│   └── command.ts
├── routes/                 # TanStack Router routes
│   ├── __root.tsx
│   ├── login.tsx
│   ├── _auth.tsx
│   └── _auth.*.tsx         # Protected routes
├── lib/                    # Utilities and hooks
│   ├── hooks/
│   │   └── useGlobalKeyboard.ts
│   └── utils.ts
├── core/                   # Core functionality
│   └── api/
│       └── client.ts       # API client (preserved)
└── features/               # Feature modules
    └── auth/               # Auth feature (preserved)
```

### Key Directories

**1. Layouts** (`src/layouts/`)
- Main layout containers
- Workbench structure
- Navigation configuration

**2. Components** (`src/components/`)
- Reusable UI components
- Global components (CommandPalette)
- UI primitives (shadcn/ui)

**3. Stores** (`src/stores/`)
- Zustand state management
- Client-side state
- Persistent preferences

**4. Routes** (`src/routes/`)
- TanStack Router file-based routing
- Route components
- Protected route wrappers

**5. Lib** (`src/lib/`)
- Custom hooks
- Utility functions
- Shared logic

## Development Workflow

### Running the Frontend

```bash
# Development server with HMR
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Run tests
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage

# Lint code
npm run lint

# Format code
npm run format
```

### Hot Module Replacement

Vite provides instant HMR for:
- React components
- CSS/Tailwind changes
- TypeScript updates
- Route changes

### Browser DevTools

Recommended extensions:
- **React Developer Tools** - Component inspection
- **Redux DevTools** - Zustand state inspection
- **TanStack Router DevTools** - Route debugging

## IDE Setup

### VS Code

Recommended extensions:
- ESLint
- Prettier
- Tailwind CSS IntelliSense
- TypeScript Vue Plugin (Volar)
- Error Lens

Settings (`.vscode/settings.json`):
```json
{
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.fixAll.eslint": true
  },
  "typescript.tsdk": "node_modules/typescript/lib",
  "tailwindCSS.experimental.classRegex": [
    ["cva\\(([^)]*)\\)", "[\"'`]([^\"'`]*).*?[\"'`]"],
    ["cn\\(([^)]*)\\)", "(?:'|\"|`)([^']*)(?:'|\"|`)"]
  ]
}
```

### WebStorm / IntelliJ IDEA

1. Enable ESLint
2. Enable Prettier
3. Configure Tailwind CSS support
4. Set Node.js interpreter

## MCP Servers Setup

### What are MCP Servers?

MCP (Model Context Protocol) servers provide AI-powered component generation for the frontend.

### Installed Servers

**1. shadcn-ui MCP Server**
- Package: `@jpisnice/shadcn-ui-mcp-server`
- Purpose: Core UI primitives
- Components: Button, Card, Dialog, Command, etc.

**2. magic-ui MCP Server**
- Package: `@magicuidesign/mcp`
- Purpose: Animations and effects
- Components: Animated text, particles, spotlight, etc.

**3. magic-mcp**
- Package: `@21st-dev/magic-mcp`
- Purpose: AI component generation
- Use: Generate initial component structures

### Configuration

MCP servers are configured in `~/.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "shadcn-ui": {
      "command": "npx",
      "args": ["-y", "@jpisnice/shadcn-ui-mcp-server"]
    },
    "magic-ui": {
      "command": "npx",
      "args": ["-y", "@magicuidesign/mcp"]
    },
    "magic-mcp": {
      "command": "npx",
      "args": ["-y", "@21st-dev/magic-mcp"]
    }
  }
}
```

### Using MCP Servers

See [MCP Servers Guide](mcp-servers.md) for detailed usage.

## Authentication Status

### Currently Bypassed ⚠️

Authentication is temporarily disabled for Phase 1 development.

**What's Bypassed**:
- Login page redirects to `/repositories`
- No token validation
- No OAuth flow
- No protected routes

**What's Preserved**:
- Auth provider structure
- API client with auth headers
- OAuth callback route
- Login page component

**See**: [Auth Shutdown](../history/auth-shutdown.md) for details

### Re-enabling Authentication

When Phase 2+ requires backend integration:

1. Restore login route
2. Enable protected routes
3. Connect API client
4. Test auth flow

See [Auth Shutdown](../history/auth-shutdown.md) for step-by-step instructions.

## Common Issues

### Port Already in Use

If port 5173 is already in use:

```bash
# Kill process on port 5173
npx kill-port 5173

# Or use a different port
npm run dev -- --port 3000
```

### Module Not Found

Clear node_modules and reinstall:

```bash
rm -rf node_modules
npm install
```

### Build Errors

Clear Vite cache:

```bash
rm -rf node_modules/.vite
npm run dev
```

### Test Failures

Run tests in isolation:

```bash
npm test -- --no-coverage
```

Check for:
- Async timing issues
- Mock data mismatches
- Environment variable issues

### TypeScript Errors

Restart TypeScript server:
- VS Code: Cmd+Shift+P → "TypeScript: Restart TS Server"
- WebStorm: File → Invalidate Caches / Restart

### Tailwind Not Working

Ensure Tailwind is configured:

```bash
# Check tailwind.config.js exists
ls tailwind.config.js

# Check PostCSS config
ls postcss.config.js

# Restart dev server
npm run dev
```

## Performance Optimization

### Development

- Use Vite's HMR for instant updates
- Lazy load routes with TanStack Router
- Use React DevTools Profiler

### Production

- Run production build: `npm run build`
- Analyze bundle: `npm run build -- --analyze`
- Check bundle size: `ls -lh dist/assets`

### Targets

- **Initial render**: < 100ms
- **Sidebar toggle**: < 200ms
- **Command palette**: < 50ms
- **Animation FPS**: 60fps
- **Bundle size**: < 200KB (gzipped)

## Testing Setup

### Test Environment

- **Framework**: Vitest
- **Library**: React Testing Library
- **Property Testing**: fast-check

### Running Tests

```bash
# All tests
npm test

# Watch mode
npm run test:watch

# Coverage
npm run test:coverage

# Specific file
npm test -- WorkbenchLayout.test.tsx

# Update snapshots
npm test -- -u
```

### Writing Tests

See [Testing Guide](testing.md) for detailed testing strategies.

## Next Steps

- [Development Guide](development.md) - Development workflow
- [Testing Guide](testing.md) - Testing strategies
- [MCP Servers Guide](mcp-servers.md) - UI component generation
- [Architecture Overview](../architecture/overview.md) - System design

## Related Documentation

- [Frontend Roadmap](../../../.kiro/specs/frontend/ROADMAP.md)
- [Phase 1 Spec](../../../.kiro/specs/frontend/phase1-workbench-navigation/)
- [Backend Setup](../../../backend/docs/guides/setup.md)

---

**Last Updated**: January 22, 2026
**Phase**: Phase 1 Complete
**Next**: Phase 2 - Living Code Editor
