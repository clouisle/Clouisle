# Outbound Network Allowlist (SSRF Exemption) Design & Policy

## Background & Problem

Clouisle features outbound HTTP request capabilities across:
- Custom HTTP tools (`app.llm.tools.executors.execute_http_tool`)
- Workflow HTTP request nodes (`HTTPRequestNodeExecutor`)
- Knowledge Base URL document import and preview extraction (`fetch_url_content`)
- Database connection testing (`validate_database_config`)

To protect against Server-Side Request Forgery (SSRF), Clouisle validates destination URLs and resolved IPs against blocked hosts, private IP ranges (RFC 1918), loopback addresses, link-local addresses, and cloud provider instance metadata endpoints.

However, two legitimate enterprise use cases were hindered:
1. **Intranet Microservices**: Enterprise deployments often need agents and workflows to query internal APIs, intranets, or on-premise databases located on private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
2. **Transparent Proxy Fake-IP Range**: Development or on-premise environments using TUN mode (Clash, Surge, Mihomo) map public domains to the `198.18.0.0/15` benchmark range. Python's `ipaddress` flags this range as `is_private=True`, causing false-positive blocks on valid public websites.

## Security Model: Model Endpoints vs. Outbound Network

Clouisle maintains two distinct allowlist policies to separate concerns and threat models:

| Policy | Setting Key | Default Behavior | Target Scope | Loopback (`localhost`) Policy |
| :--- | :--- | :--- | :--- | :--- |
| **Model Endpoint Allowlist** | `model_endpoint_allowlist` | **Default Deny** (Strict Allowlist) | LLM, embedding, rerank, and media providers | **Permitted** (Admins may explicitly approve `http://localhost:11434` for Ollama/vLLM) |
| **Outbound Network Allowlist** | `ssrf_allowed_targets` | **Default Allow Public** (Denylist + Exemption Allowlist) | HTTP tools, workflow nodes, KB URL scraping, DB test | **Strictly Forbidden** (Protects host local services and Redis/Docker from agent abuse) |

## Non-Bypassable Hard Invariants (Permanently Blocked)

Regardless of allowlist entries, the following targets can **never** be allowlisted and are rejected both at configuration save and during request execution:

1. **Cloud Instance Metadata (IMDS)**:
   - `169.254.169.254` (IPv4 IMDSv1/v2)
   - `169.254.0.0/16` (IPv4 Link-Local range)
   - `fe80::/10` (IPv6 Link-Local range)
   - `metadata.google.internal` (GCP metadata hostname)
   - *Rationale*: Prevents exfiltration of host IAM/Cloud credentials.
2. **Unspecified & Multicast Addresses**:
   - `0.0.0.0`, `0.0.0.0/32`, `::`
   - `224.0.0.0/4` (Multicast)
   - *Rationale*: Prevents bypassing loopback restrictions via `0.0.0.0`.
3. **Universal Wildcards**:
   - `*`, `0.0.0.0/0`, `::/0`
   - *Rationale*: Prevents accidentally or maliciously disabling network security globally.
4. **Loopback (`127.0.0.1` / `localhost` / `::1`)**:
   - Rejected to preserve sandbox and host port isolation. To connect to companion containers, use host LAN IPs or `host.docker.internal`.

## Permitted Allowlist Target Formats

Administrators configure approved outbound targets in **Site Settings > Security**:

- **Single IP Address**: `192.168.1.50`, `10.20.1.10`
- **CIDR Subnet**: `10.10.0.0/16`, `172.20.0.0/24`, `192.168.0.0/16`
- **Exact Domain**: `oa.company.local`, `api.internal.service`
- **Wildcard Domain**: `*.corp.internal`, `*.internal.net`
- **Fake-IP Transparent Proxy Support**: `198.18.0.0/15` is built-in and automatically allowed without requiring manual configuration.
