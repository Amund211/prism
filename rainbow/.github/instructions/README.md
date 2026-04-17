# Rainbow - Prism Overlay Web Interface

## Overview

Rainbow is a React-based web application that serves as the frontend interface for the Prism Overlay project. Prism is a real-time statistics overlay tool for Hypixel Bedwars that automatically tracks player performance and displays game statistics. The Rainbow web app provides:

- Download links for the Prism desktop application (Windows, macOS, Linux)
- Interactive charts and statistics visualization
- Session tracking and history exploration
- Player search and comparison tools

**Repository Size**: ~30 source files in TypeScript/React
**Tech Stack**: React 19, TypeScript, Vite, Material-UI, TanStack Router/Query, Sentry
**Target Runtime**: Web browsers (deployed as static site)

## Build System Requirements

### Node.js Version Requirement (CRITICAL)

**Always use Node.js 24 or higher.**

If Node.js version is below 24, install Node 24 first:

```bash
sudo n 24  # if 'n' is available
node --version  # verify version is 24+
```

### Development Environment Setup

**Always run these commands in order:**

1. **Install dependencies** (always run first):

```bash
pnpm install --frozen-lockfile
```

2. **Type checking** (verify TypeScript compiles):

```bash
pnpm run tsc
```

3. **Linting** (verify code style):

```bash
pnpm run lint:check
```

4. **Testing** (verify functionality):

```bash
pnpm test
```

5. **Build** (verify production build):

```bash
pnpm run build
```

### Development Server

**Always use production proxy mode for development work:**

```bash
pnpm run dev:production
```

This starts the server at http://localhost:5173/ with proxy to production backend.

**Always take screenshots after making UI changes** to verify visual correctness.

### Alternative Development Modes

- `pnpm run dev` - Local development (Never use this unless absolutely necessary. This will not show any data, and will not behave like the app does in production)
- `pnpm run dev:staging` - Proxy to staging backend
- `pnpm run dev:production` - Proxy to production backend (recommended) Always use dev:production when possible

## Build Commands Reference

### Core Commands (Use These Regularly)

| Command                          | Purpose              | Typical Duration | Critical Notes                            |
| -------------------------------- | -------------------- | ---------------- | ----------------------------------------- |
| `pnpm install --frozen-lockfile` | Install dependencies | 30-60s           | Always run before other commands          |
| `pnpm run lint:check`            | Check code style     | 10-30s           | Must pass for CI                          |
| `pnpm test`                      | Run all tests        | 5-10s            | Requires Node 24+                         |
| `pnpm run build`                 | Production build     | 2-3 minutes      | May show Sentry warnings (safe to ignore) |
| `pnpm run tsc`                   | Type checking only   | 10-20s           | Faster than full build                    |

### Linting and Formatting

```bash
pnpm run oxfmt:check     # Check formatting
pnpm run oxfmt:write     # Fix formatting
pnpm run oxlint:check       # Check oxlint rules
pnpm run oxlint:write       # Fix oxlint issues
pnpm run lint:check         # Run both oxfmt + oxlint check
pnpm run lint:fix           # Fix both oxfmt + oxlint issues
```

### Known Build Issues and Workarounds

1. **Sentry Auth Token Warnings**: Safe to ignore during development

    ```
    [sentry-vite-plugin] Warning: No auth token provided
    ```

2. **Large Bundle Size Warnings**: Expected behavior, not breaking

    ```
    Some chunks are larger than 500 kB after minification
    ```

## Testing

### Running Tests

```bash
pnpm test  # Requires Node.js 24+
```

Tests use Node.js built-in test runner with TypeScript support. All tests should pass in a clean repository.

### Test Structure

- Unit tests for utility functions (`*.test.ts` files)
- No UI/integration tests currently
- Tests cover: time intervals, UUID handling, Bedwars level calculations, data processing

### Test Files Location

```
src/
├── intervals.test.ts
├── helpers/
│   ├── session.test.ts
│   ├── userId.test.ts
│   └── uuid.test.ts
├── stats/stars.test.ts
└── charts/history/data.test.ts
```

## Project Architecture

### Key Configuration Files

```
/
├── package.json           # Dependencies and scripts
├── vite.config.ts         # Build configuration + proxies
├── .oxlintrc.json         # Linting rules (strict TypeScript)
├── tsconfig.json         # TypeScript configuration
├── tsconfig.app.json     # App-specific TypeScript config
└── .pre-commit-config.yaml # Git hooks configuration
```

### Source Code Structure

```
src/
├── main.tsx              # Application entry point
├── App.tsx               # Root component with routing
├── routes/               # Page components (TanStack Router)
│   ├── __root.tsx        # Layout wrapper
│   ├── index.tsx         # Homepage (player search)
│   ├── downloads.tsx     # Prism app downloads
│   ├── about.tsx         # About page
│   ├── settings.tsx      # User settings
│   └── history.explore.tsx # Statistics visualization
├── components/           # Reusable UI components
├── contexts/             # React context providers
├── hooks/                # Custom React hooks
├── queries/              # TanStack Query API calls
├── charts/               # Chart components and data processing
├── helpers/              # Utility functions
└── media/                # Static assets (images, icons)
```

### Import Alias

The project uses `#` as an import alias for the `src/` directory:

```typescript
import { AppLayout } from "#components/Layouts";
import { createQueryClient } from "#queryClient.ts";
```

### Environment Configuration

```
.env.development     # Local development settings
.env.production      # Production backend URLs
.env.proxy-staging   # Staging proxy configuration
.env.proxy-production # Production proxy configuration
```

## CI/CD Pipeline

### GitHub Actions Workflow (.github/workflows/testing.yml)

```yaml
1. Install Node.js 24
2. Install dependencies (pnpm install --frozen-lockfile)
3. Run linting (pnpm run lint:check)
4. Run tests (pnpm test)
5. Build production (pnpm run build)
```

**All steps must pass for CI to succeed.**

### Pre-commit Hooks

When committing locally, these hooks run automatically:

- Oxfmt formatting
- Oxlint linting
- TypeScript type checking
- Full test suite

**Note**: Hooks may take 30-60 seconds to complete.

## Common Troubleshooting

### Build Failures

1. **"command not found" errors**: Run `pnpm install --frozen-lockfile` first
2. **TypeScript errors**: Run `pnpm run tsc` to see detailed errors
3. **Linting failures**: Run `pnpm run lint:fix` to auto-fix issues
4. **Test failures**: Check Node.js version is 24+

### Development Server Issues

1. **Port 5173 in use**: Kill existing processes or use different port
2. **Proxy errors**: Check network connectivity, use `dev:production` mode
3. **Missing routes**: Run `pnpm run build` to regenerate route tree

### Performance Notes

- Initial `pnpm install --frozen-lockfile` may take 1-2 minutes
- Build process takes 2-3 minutes (normal)
- Dev server starts in 5-10 seconds
- Hot reload is very fast (< 1 second)

## Key Dependencies

### Runtime Dependencies

- **React 19** with React Router and Query
- **Material-UI** for component library
- **TanStack Router/Query** for routing and data fetching
- **Recharts** for data visualization
- **Sentry** for error monitoring

### Development Dependencies

- **Vite** for build tooling and dev server
- **TypeScript** with strict configuration
- **Oxlint + Oxfmt** for code quality
- **Node.js built-in test runner** for testing

## Validation Steps for Changes

### After Making Code Changes (Always Do This)

1. **Type check**: `pnpm run tsc` (must pass)
2. **Lint**: `pnpm run lint:check` (must pass)
3. **Test**: `pnpm test` (all tests must pass)
4. **Build**: `pnpm run build` (should complete successfully)
5. **Manual verification**: Start dev server and test affected functionality. The player with UUID 6bc1dd0f-f351-4c3d-b6cc-262e55b6e7aa usually has good data coverage for testing functionality.
6. **Screenshot**: Take screenshots of any UI changes - inspect the screenshot to see if it contains the expected result. If the screenshot shows a loading screen, or is otherwise blank, wait until the page loads to take a new screenshot, or fix the issue preventing it from loading.

### Before Submitting PR

1. Ensure all above validation steps pass
2. Check that no new TypeScript errors are introduced
3. Verify the application runs correctly in browser
4. Confirm all tests still pass

## Trust These Instructions

These instructions are comprehensive and tested. **Only search for additional information if**:

- Commands fail unexpectedly despite following the instructions
- You encounter error messages not covered in the troubleshooting section
- The repository structure has changed significantly from what's described

**Do not** search for basic setup, build, or test information - it's all provided above.
