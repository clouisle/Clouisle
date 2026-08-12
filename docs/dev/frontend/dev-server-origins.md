# Dev Server Allowed Origins (LAN Access)

The Next.js dev server blocks cross-origin requests by default (CSRF
protection): a page opened from a LAN origin (e.g. `http://192.168.0.31:3000`)
gets its HMR WebSocket upgrade and internal asset requests rejected, while the
page itself still loads. The dev-only `allowedDevOrigins` list in
`frontend/next.config.ts` controls which origins may reach the dev server.

## Matching rules

Next.js matches each `allowedDevOrigins` entry against the **hostname**
extracted from the request's `Origin`/`Referer` header (no scheme, no port):

- Exact match: `192.168.0.31` matches only that host.
- Wildcard domain pattern: `192.168.*.*` matches any four-octet address
  starting with `192.168.`; `*.local` matches `my-mac.local`.
- A bare `'*'` is **rejected as a pattern and never matches** — do not use it.

The default allowlist already covers `localhost` and `*.localhost`.

## Default policy

`frontend/next.config.ts` allows the private RFC1918 LAN ranges
(`192.168.0.0/16`, `10.0.0.0/8`, `172.16.0.0/12`) and `*.local` (mDNS
hostnames). These are development-only and never reach production builds.

## Adding a host

When a machine is not covered (e.g. a specific hostname, a VPN range, or a
non-private IP), set `DEV_ALLOWED_ORIGINS` to a comma-separated list of exact
hostnames or wildcard patterns and restart the dev server:

```bash
DEV_ALLOWED_ORIGINS="my-mac.local,10.20.30.40" bun run dev
```

## Notes

- The dev server must also listen on the LAN interface: `next dev -H 0.0.0.0`
  (or `HOSTNAME=0.0.0.0`).
- `next.config.ts` changes are not hot-reloaded — restart the dev server after
  editing `allowedDevOrigins`.
