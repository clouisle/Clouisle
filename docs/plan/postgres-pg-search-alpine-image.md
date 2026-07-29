# PostgreSQL pg_search Alpine Image Design Document

## Background & Goals

The first pg_search image uses `postgres:17` and ParadeDB's checksum-verified Trixie package. Its ARM64 unpacked size is `638,971,051` bytes: the PostgreSQL base is about 476 MB and the pg_search layer is about 163 MB. Switching Debian variants and stripping the extension cannot meet the required limit.

This follow-up builds pg_search 0.24.3 natively on Alpine/musl. ParadeDB does not publish or release-test Alpine artifacts, so Clouisle owns this platform port and must block publication unless both supported architectures pass the same runtime tests.

Success criteria:

- `docker image inspect .Size` is strictly below `500000000` bytes on both amd64 and arm64.
- PostgreSQL 17 preloads pg_search 0.24.3 and pg_stat_statements.
- Chinese and mixed-language `pdb.jieba` BM25, field boosts, exact identifiers, tenant scope, updates, deletes, restart, and crash recovery pass.
- Build inputs are immutable and the runtime contains no compiler, Rust toolchain, builder source tree, builder-only headers, or build cache.
- No deployment default changes until both native architectures pass.

## High-Level Design

The Dockerfile downloads the exact ParadeDB source commit, verifies its archive checksum, and compiles it with the upstream Rust and pgrx versions against the same Alpine PostgreSQL family used at runtime. BuildKit caches Cargo inputs by architecture. The final image retains the official PostgreSQL entrypoint and receives only pg_search runtime artifacts and ELF-proven runtime libraries.

The build uses `RUSTFLAGS="-C target-feature=-crt-static"` because PostgreSQL must dynamically load the musl `cdylib`. It does not copy ParadeDB's glibc packages into Alpine, remove tokenizer dictionaries, alter pg_search features, or compress the shared library with UPX.

A standalone image test script enforces the byte limit and exercises the production preload, extension, BM25, lifecycle, and recovery behavior. Release CI builds and tests each architecture natively, publishes architecture digests only after validation, then assembles the multi-platform manifest.

## Implementation Plan

### Stage 1: Reproducible Alpine source build

- **Files modified**: `deploy/postgres/Dockerfile`
- **Specific logic**:
  - Pin the PostgreSQL Alpine builder/runtime family and digest.
  - Pin pg_search `0.24.3`, source commit, source archive SHA-256, Rust `1.96.0`, cargo-pgrx `0.18.1`, and upstream `Cargo.lock`.
  - Verify source integrity before extraction and build only PG17 with the runtime image's `pg_config`.
  - Audit the packaged `.so` with `scanelf` and `readelf`; fail on glibc references, build RPATHs, or build-only runtime dependencies. Validate PostgreSQL-provided symbols by loading the extension in PostgreSQL rather than running standalone `ldd`.
  - Copy only the shared library, control file, and SQL files into the final image.
- **Validation**: Build on the native host architecture, inspect layers/files, verify the extension loads, and confirm the runtime contains no build tools.

### Stage 2: Runtime and size acceptance harness

- **Files modified**: `deploy/postgres/test-image.sh`
- **Specific logic**:
  - Require `.Size < 500000000` and print exact image/artifact measurements.
  - Start PostgreSQL with the same preload arguments as production.
  - Create and validate pg_search 0.24.3 and pg_stat_statements.
  - Run the application's real lexical table/index/query shape against Chinese, mixed text, field boosts, exact identifiers, and isolated scopes.
  - Exercise update/delete, clean restart, and committed-write crash recovery using one persistent test volume.
  - Use traps for cleanup and print server logs on failure.
- **Validation**: Run the script against both native architecture artifacts; any failed assertion blocks publication.

### Stage 3: Native multi-architecture CI and publication

- **Files modified**: `.github/workflows/postgres-image.yml`
- **Specific logic**:
  - Run affected pull-request builds without pushing images.
  - Build/test amd64 and arm64 on native Linux runners with architecture-specific caches.
  - Export tested artifacts per architecture, then push both immutable architecture tags only after the complete matrix passes.
  - Assemble a manifest containing exactly linux/amd64 and linux/arm64; publish a revision tag such as `0.24.3-pg17-alpine1`, not `latest`.
  - Keep database image publication separate from application release tags so ordinary application releases do not rebuild this pinned database artifact.
- **Validation**: Inspect manifest platforms and record both digests and unpacked sizes in workflow evidence.

### Stage 4: Deployment adoption and operations

- **Files modified**: `deploy/docker-compose.yml`, `deploy/docker-compose.dev.yml`, `deploy/k8s/clouisle.yaml`, `deploy/helm/clouisle/values.yaml`, `deploy/README.md`, `deploy/helm/clouisle/README.md`, `docs/plan/postgresql-pg-search-lexical.md`
- **Specific logic**:
  - Atomically switch built-in deployment defaults only after both native builds pass.
  - Preserve preload arguments, ports, environment variables, volumes, service names, and PostgreSQL 16-to-17 migration requirements.
  - Document that the Alpine/musl artifact is internally maintained and that every Alpine, PostgreSQL, Rust, pgrx, or pg_search update requires full dual-architecture qualification.
  - Retain the checksum-verified Debian image as a rollback asset; it does not satisfy the new size criterion.
- **Validation**: Render both Compose files, Helm defaults/production/external-database modes, and Kubernetes client dry-run; run a complete development deployment smoke test.

## Current Validation Evidence

- Native ARM64 build completed on 2026-07-29: image `426,942,814` bytes, pg_search shared library `136,636,872` bytes.
- ARM64 ELF audit reported only `libgcc_s.so.1` and `libc.musl-aarch64.so.1`, with no RPATH/RUNPATH or LLVM/libclang dependency.
- ARM64 runtime acceptance passed preload, extension version, Chinese/mixed BM25, exact identifier and tenant checks, update/delete, clean restart, and forced-termination recovery.
- Native amd64 build, registry publication, and final two-platform manifest remain unverified. Deployment defaults must not change yet.

## Testing Strategy

### Happy paths

- Both native architectures build from pinned inputs and are below 500 MB unpacked.
- Preload and extension initialization work on a fresh database.
- Chinese, mixed-language, boosted-title, identifier, and scope queries return deterministic expected chunks.
- Updates/deletes remain reflected after restart and committed rows survive crash recovery.
- Application startup auto-initializes the lexical schema and fulltext/hybrid retrieval works.

### Error paths

- Wrong source checksum, source version, PostgreSQL major, architecture, or missing runtime library fails the build.
- Image size at or above the limit fails the test before publication.
- Missing preload, wrong extension version, failed BM25 query, recovery error, or incomplete manifest blocks deployment adoption.
- A single successful architecture never produces the shared release tag.

### Regression scope

- Backend lexical initialization, lexical adapter, and retrieval tests.
- Compose, Kubernetes, and Helm PostgreSQL configuration.
- PostgreSQL data-directory persistence and PG16-to-PG17 migration guidance.

## Risks & Mitigation

- **Unsupported upstream platform**: Alpine/musl is an internal port. Pin every input, test both architectures natively, and retain the Debian rollback image.
- **Long, resource-intensive Rust build**: use architecture-separated BuildKit caches without weakening integrity or runtime checks.
- **musl/CDylib linkage defects**: force dynamic CRT behavior and reject unresolved, glibc, RPATH, LLVM, or libclang dependencies.
- **Functional loss from size pressure**: never remove tokenizer data, pg_search features, or required PostgreSQL behavior to meet the gate.
- **Partial release**: publication and deployment adoption require both architecture digests and the exact two-platform manifest.

Rollback is an atomic return to the existing `0.24.3-pg17` Debian image. PostgreSQL 17 data remains compatible at the database-major level, but rollback must still be rehearsed against the actual extension/index state before production deployment.