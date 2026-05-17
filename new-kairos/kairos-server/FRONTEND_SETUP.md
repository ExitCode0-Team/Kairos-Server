# Frontend Setup Guide

This document explains how to wire a Next.js 14 App Router frontend to the Kairos FastAPI backend.

---

## Architecture overview

```
Browser
  ↓  Supabase Auth SDK  (login / magic link)
  ↓  cookie session (managed by @supabase/ssr + middleware)
Next.js (SSR)
  ↓  serverFetch()  →  Authorization: Bearer <supabase_jwt>
FastAPI  (/v1/*)
  ↓  get_current_user dep  →  decodes JWT, extracts user UUID
Supabase Postgres  (via service_role key)
```

- The browser **never** calls the FastAPI directly — all calls go through Next.js API routes (`/api/*`) which attach the session token and proxy to FastAPI.
- The Next.js server reads `KAIROS_API_URL` (server-only env var) to know where FastAPI lives.
- If `KAIROS_API_URL` is unset (local dev without backend), each proxy route falls back to a static fixture so the UI renders without errors.

---

## 1. Required packages

```bash
# in apps/web/
npx create-next-app@14 . --typescript --tailwind --app --src-dir=false
npm install @supabase/supabase-js @supabase/ssr
```

---

## 2. Environment variables

### `apps/web/.env.local`  (never commit)

```env
# Supabase — get from Project Settings → API
NEXT_PUBLIC_SUPABASE_URL=https://your-project-ref.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key

# FastAPI backend URL — server-only (no NEXT_PUBLIC_ prefix)
KAIROS_API_URL=http://localhost:8000
```

### `apps/web/next.config.ts`

```ts
import type { NextConfig } from "next";

const config: NextConfig = {
  // Fail the build if server-only vars are accidentally used on the client
  serverExternalPackages: [],
};

export default config;
```

---

## 3. Supabase clients

### `lib/supabase/server.ts`  (RSC / Route Handler safe)

```ts
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export function createClient() {
  const cookieStore = cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => cookieStore.getAll(),
        setAll: (cookiesToSet) =>
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          ),
      },
    }
  );
}
```

### `lib/supabase/browser.ts`  (Client Components)

```ts
import { createBrowserClient } from "@supabase/ssr";

export const supabase = createBrowserClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);
```

---

## 4. Middleware — session refresh + auth guard

### `middleware.ts`  (project root, same level as `app/`)

```ts
import { createServerClient } from "@supabase/ssr";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/auth/callback"];

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (cookiesToSet) =>
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options)
          ),
      },
    }
  );

  // Refresh session (updates cookie on response)
  const { data: { user } } = await supabase.auth.getUser();

  const isPublic = PUBLIC_PATHS.some((p) =>
    request.nextUrl.pathname.startsWith(p)
  );

  if (!user && !isPublic) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
```

---

## 5. API layer

### `lib/api/server.ts`  — proxy helper for RSC / Route Handlers

```ts
import { createClient } from "@/lib/supabase/server";

export class ApiUnavailable extends Error {}

export async function serverFetch(
  path: string,
  init: RequestInit = {}
): Promise<{ status: number; json: unknown }> {
  const apiUrl = process.env.KAIROS_API_URL;
  if (!apiUrl) throw new ApiUnavailable("KAIROS_API_URL not set");

  const supabase = createClient();
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;

  const res = await fetch(`${apiUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });

  const json = await res.json();
  return { status: res.status, json };
}
```

### `lib/api/client.ts`  — browser fetch helper for Client Components

```ts
export async function apiFetch(
  path: string,
  init: RequestInit = {}
): Promise<unknown> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: "Unknown error" }));
    throw Object.assign(new Error(body.error ?? "Request failed"), { status: res.status, body });
  }

  return res.json();
}
```

### `lib/api/fallback.ts`  — fixtures for when FastAPI is unavailable

```ts
// Keep your existing hardcoded fixture values here, one export per resource.
// Example:

export const profileFallback = {
  name: "",
  role: "",
  skills: [],
  experience: "",
  projects: [],
  references: [],
};

export const matchesFallback = { items: [], total: 0, page: 1, pageSize: 20 };
export const dashboardFallback = {
  stats: { matchesToday: 0, newThisWeek: 0, avgMatchScore: 0, savedRoles: 0, deltas: {} },
  recentMatches: [],
  activities: [],
};
// … add more as needed
```

---

## 6. API proxy routes

Every Next.js route in `app/api/` is a thin proxy that forwards to FastAPI and falls
back to the fixture if `KAIROS_API_URL` is unset.

**Pattern** (copy for each resource):

```ts
// app/api/profile/route.ts
import { ApiUnavailable, serverFetch } from "@/lib/api/server";
import { profileFallback } from "@/lib/api/fallback";

export async function GET() {
  try {
    const r = await serverFetch("/v1/profile");
    return Response.json(r.json, { status: r.status });
  } catch (e) {
    if (e instanceof ApiUnavailable)
      return Response.json(profileFallback, { status: 200 });
    throw e;
  }
}

export async function PUT(req: Request) {
  try {
    const body = await req.json();
    const r = await serverFetch("/v1/profile", {
      method: "PUT",
      body: JSON.stringify(body),
    });
    return Response.json(r.json, { status: r.status });
  } catch (e) {
    if (e instanceof ApiUnavailable)
      return Response.json({ ok: true }, { status: 200 });
    throw e;
  }
}

export async function PATCH(req: Request) {
  try {
    const body = await req.json();
    const r = await serverFetch("/v1/profile", {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    return Response.json(r.json, { status: r.status });
  } catch (e) {
    if (e instanceof ApiUnavailable)
      return Response.json(profileFallback, { status: 200 });
    throw e;
  }
}
```

**Routes to create** (one file each):

| File | Methods | FastAPI target |
|---|---|---|
| `app/api/profile/route.ts` | GET, PUT, PATCH | `/v1/profile` |
| `app/api/profile/cv/route.ts` | POST (multipart) | `/v1/profile/cv` |
| `app/api/matches/route.ts` | GET | `/v1/matches` |
| `app/api/matches/[id]/bookmark/route.ts` | POST | `/v1/matches/{id}/bookmark` |
| `app/api/matches/[id]/apply/route.ts` | POST | `/v1/matches/{id}/apply` |
| `app/api/connectors/route.ts` | GET | `/v1/connectors` |
| `app/api/connectors/status/route.ts` | GET | `/v1/connectors/status` |
| `app/api/connectors/[id]/connect/route.ts` | POST | `/v1/connectors/{id}/connect` |
| `app/api/connectors/[id]/disconnect/route.ts` | POST | `/v1/connectors/{id}/disconnect` |
| `app/api/connectors/channel/route.ts` | PUT | `/v1/connectors/channel` |
| `app/api/dashboard/summary/route.ts` | GET | `/v1/dashboard/summary` |
| `app/api/cvs/route.ts` | GET, POST | `/v1/cvs` |
| `app/api/cvs/[id]/route.ts` | DELETE | `/v1/cvs/{id}` |
| `app/api/cvs/[id]/default/route.ts` | POST | `/v1/cvs/{id}/set-default` |
| `app/api/settings/route.ts` | GET, PUT | `/v1/settings` |
| `app/api/preferences/jobs/route.ts` | GET, PUT | `/v1/preferences/jobs` |
| `app/api/preferences/jobs/pool/route.ts` | GET | `/v1/preferences/jobs/pool` |
| `app/api/health/route.ts` | GET | `/v1/health` |

For multipart CV upload, pipe the request body without parsing it:

```ts
// app/api/profile/cv/route.ts
export async function POST(req: Request) {
  try {
    const r = await serverFetch("/v1/profile/cv", {
      method: "POST",
      body: await req.blob(),
      headers: { "Content-Type": req.headers.get("content-type") ?? "application/pdf" },
    });
    return Response.json(r.json, { status: r.status });
  } catch (e) {
    if (e instanceof ApiUnavailable)
      return Response.json(profileFallback, { status: 200 });
    throw e;
  }
}
```

---

## 7. Auth pages

### `app/(auth)/login/page.tsx`

```tsx
"use client";
import { supabase } from "@/lib/supabase/browser";
import { useState } from "react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${location.origin}/auth/callback` },
    });
    setSent(true);
  }

  if (sent)
    return <p>Check your email for a magic link.</p>;

  return (
    <form onSubmit={handleSubmit}>
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@example.com"
        required
      />
      <button type="submit">Send magic link</button>
    </form>
  );
}
```

### `app/auth/callback/route.ts`

```ts
import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");

  if (code) {
    const supabase = createClient();
    await supabase.auth.exchangeCodeForSession(code);
  }

  return NextResponse.redirect(`${origin}/dashboard`);
}
```

---

## 8. Page wiring

All `(app)` pages are `async` server components that call `serverFetch` directly (no API
route hop needed for the initial render):

```tsx
// app/(app)/dashboard/page.tsx
import { ApiUnavailable, serverFetch } from "@/lib/api/server";
import { dashboardFallback } from "@/lib/api/fallback";

export default async function DashboardPage() {
  let summary = dashboardFallback;
  try {
    const r = await serverFetch("/v1/dashboard/summary");
    summary = r.json as typeof dashboardFallback;
  } catch (e) {
    if (!(e instanceof ApiUnavailable)) throw e;
  }

  return (
    <div>
      <h1>Dashboard</h1>
      <pre>{JSON.stringify(summary.stats, null, 2)}</pre>
      {/* … your actual components … */}
    </div>
  );
}
```

Client-side mutations (bookmark, apply, settings save) use `apiFetch` from
`lib/api/client.ts` and call `router.refresh()` afterwards to trigger a server
re-render.

---

## 9. Shared TypeScript types

Create `lib/api/types.ts` with the types that mirror the FastAPI schemas:

```ts
export type UserProfile = {
  name: string;
  role: string;
  skills: string[];
  experience: string;
  projects: string[];
  references: string[];
};

export type Match = {
  id: string;
  company: string;
  role: string;
  location: string;
  postedAt: string;   // ISO 8601
  score: number;      // 0-100
  skills: string[];
  saved?: boolean;
  applied?: boolean;
};

export type Cv = {
  id: string;
  name: string;
  uploadedAt: string;
  isDefault: boolean;
  sizeBytes: number;
};

export type Settings = {
  displayName: string;
  email: string;
  notificationChannel: "whatsapp" | "telegram" | "slack" | "discord" | "email";
};

export type Connector = {
  id: string;
  name: string;
  description: string;
  category: "data" | "channel" | "coming_soon";
};

export type Activity = {
  id: string;
  iconKey: "match" | "apply" | "save" | "cv" | "agent";
  label: string;
  at: string;
};

export type DashboardSummary = {
  stats: {
    matchesToday: number;
    newThisWeek: number;
    avgMatchScore: number;
    savedRoles: number;
    deltas: Record<string, number>;
  };
  recentMatches: Match[];
  activities: Activity[];
};

export type ApiError = {
  error: string;
  message?: string;
  fieldErrors?: Record<string, string[]>;
};
```

---

## 10. Verification checklist

| Check | How |
|---|---|
| **Auth works** | Open `/login`, enter email, click magic link, land on `/dashboard` |
| **No KAIROS_API_URL** | Unset the env var, reload every page — all should render with fixture data |
| **With backend** | Set `KAIROS_API_URL=http://localhost:8000`, start FastAPI (`uvicorn app.main:app --reload`), check Network tab shows `/v1/…` responses |
| **Token forwarded** | In FastAPI logs you should see `INFO` for each authenticated request (no 401s) |
| **CV upload** | Use the CVs page upload button, confirm a new row appears in the `cvs` table in Supabase Studio |
