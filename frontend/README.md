# Clouisle Frontend

Clouisle frontend is built with **Next.js 16 (App Router)**, **React 19**, **TypeScript**, **Tailwind CSS**, and **shadcn/ui**.

---

## 🛠️ Tech Stack & Architecture

- **Framework**: Next.js 16 (App Router, Standalone output)
- **Runtime & Package Manager**: Bun
- **UI Components & Styling**: Tailwind CSS, Radix UI primitives, Lucide Icons, Lucide React
- **Flow & Canvas Editor**: React Flow / `@xyflow/react` (Workflow Graph Builder)
- **Internationalization**: `next-intl` with lexical-scope linting (`bun run i18n:lint`, `bun run i18n:check`)
- **State & Data Fetching**: Axios with unified response/toast error interceptor, SWR / React Hooks
- **Testing**: Bun test with isolated DOM mocking and strict LCOV code coverage gate

---

## 🚀 Getting Started

### 1. Install Dependencies

```bash
bun install
```

### 2. Configure Environment

Copy `.env.example` or create `.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

### 3. Start Development Server

```bash
bun dev
```

The application will be available at [http://localhost:3000](http://localhost:3000).

---

## 📦 Directory Structure

```
frontend/
├── app/                  # Next.js App Router route groups
│   ├── (auth)/           # Authentication: login, register, reset-password, totp-setup, sso-callback
│   ├── (chat)/           # Real-time streaming chat & run execution views
│   ├── (dashboard)/      # Admin dashboard: users, roles, permissions, audit-logs, site-settings, observability
│   ├── (platform)/       # Workspace member views: apps, knowledge bases, capabilities, memories
│   └── (embed)/          # Iframe embed widgets for Agent and Workflow chat
├── components/           # Reusable UI primitives and domain widgets
├── contexts/             # Global React contexts (Auth, Team, Theme)
├── hooks/                # Custom React hooks
├── i18n/                 # Bilingual dictionary catalogs (en, zh)
├── lib/                  # Utilities, API client interceptors, and workflow helpers
└── scripts/              # i18n check and linting automation scripts
```

---

## 🧪 Quality & Verification Gates

```bash
# Type check
bun x tsc --noEmit

# Lint & Format
bun run lint
bun run format:check

# Internationalization validation
bun run i18n:lint
bun run i18n:check

# Run unit tests and verify coverage
bun run test:coverage
bun run coverage:check
```
