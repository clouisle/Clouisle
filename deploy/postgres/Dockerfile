# syntax=docker/dockerfile:1.7

ARG ALPINE_IMAGE=alpine:3.23@sha256:fd791d74b68913cbb027c6546007b3f0d3bc45125f797758156952bc2d6daf40
ARG POSTGRES_IMAGE=postgres:17-alpine3.23@sha256:8189a1f6e40904781fc9e2612687877791d21679866db58b1de996b31fc312e4
ARG RUST_IMAGE=rust:1.96.0-alpine3.23@sha256:5dc2af9dd547c33f64d5fc1d299ab93b51f39eaa16c426c476b990ce6caf5b3e

FROM ${RUST_IMAGE} AS rust-toolchain

FROM ${ALPINE_IMAGE} AS pg-search-source

ARG PG_SEARCH_VERSION=0.24.3
ARG PG_SEARCH_REVISION=5fa2690053c905d06e8b55d43f3df7aa40ee43a2
ARG PG_SEARCH_SOURCE_SHA256=bde33cc1958735c4d5311f45be2ae901b6a4cadbc5ce6dcc9da57987acfb8582

RUN apk add --no-cache ca-certificates curl tar \
    && curl -fsSL \
        "https://github.com/paradedb/paradedb/archive/${PG_SEARCH_REVISION}.tar.gz" \
        -o /tmp/pg_search.tar.gz \
    && echo "${PG_SEARCH_SOURCE_SHA256}  /tmp/pg_search.tar.gz" | sha256sum -c - \
    && mkdir /source \
    && tar -xzf /tmp/pg_search.tar.gz --strip-components=1 -C /source \
    && test "$(sed -n 's/^version = "\([^"]*\)"/\1/p' /source/Cargo.toml | head -n 1)" = "${PG_SEARCH_VERSION}" \
    && rm /tmp/pg_search.tar.gz

FROM ${POSTGRES_IMAGE} AS pg-search-builder

ARG TARGETARCH
ARG CARGO_PGRX_VERSION=0.18.1

ENV CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
    PATH=/usr/local/cargo/bin:/usr/local/rustup/bin:$PATH \
    RUSTFLAGS="-C target-feature=-crt-static"

COPY --from=rust-toolchain /usr/local/cargo /usr/local/cargo
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup
COPY --from=pg-search-source /source /source

RUN --mount=type=cache,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,target=/usr/local/cargo/git,sharing=locked \
    apk add --no-cache \
        bash \
        build-base \
        clang \
        clang-dev \
        clang-libs \
        coreutils \
        git \
        llvm-dev \
        musl-dev \
        openssl-dev \
        pax-utils \
        pkgconf \
        util-linux-dev \
    && case "$TARGETARCH" in amd64|arm64) ;; *) exit 1 ;; esac \
    && test "$(pg_config --version | cut -d ' ' -f 2 | cut -d . -f 1)" = "17" \
    && cargo install --locked cargo-pgrx --version "$CARGO_PGRX_VERSION" --debug \
    && cargo pgrx init --pg17="$(command -v pg_config)"

RUN --mount=type=cache,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,target=/usr/local/cargo/git,sharing=locked \
    --mount=type=cache,target=/source/target,sharing=locked \
    cd /source/pg_search \
    && cargo pgrx package --pg-config "$(command -v pg_config)" \
    && package_root="$(find /source/target/release -type d -path '*/pg_search-pg17' -print -quit)" \
    && test -n "$package_root" \
    && install -d /package/usr/local/lib/postgresql /package/usr/local/share/postgresql/extension \
    && install -m 755 "$package_root/usr/local/lib/postgresql/pg_search.so" /package/usr/local/lib/postgresql/pg_search.so \
    && install -m 644 "$package_root"/usr/local/share/postgresql/extension/pg_search* /package/usr/local/share/postgresql/extension/ \
    && strip --strip-unneeded /package/usr/local/lib/postgresql/pg_search.so \
    && scanelf --needed --nobanner /package/usr/local/lib/postgresql/pg_search.so \
    && ! readelf -d /package/usr/local/lib/postgresql/pg_search.so | grep -E 'RPATH|RUNPATH' \
    && ! scanelf --needed --nobanner /package/usr/local/lib/postgresql/pg_search.so | grep -E 'libclang|libLLVM|ld-linux'

FROM ${POSTGRES_IMAGE}

ARG PG_SEARCH_VERSION=0.24.3
ARG PG_SEARCH_REVISION=5fa2690053c905d06e8b55d43f3df7aa40ee43a2

LABEL org.opencontainers.image.source="https://github.com/paradedb/paradedb" \
      org.opencontainers.image.version="${PG_SEARCH_VERSION}" \
      io.clouisle.pg-search.revision="${PG_SEARCH_REVISION}" \
      io.clouisle.pg-search.platform="alpine-musl"

COPY --from=pg-search-builder /package/ /

RUN test -s /usr/local/lib/postgresql/pg_search.so \
    && test -f "/usr/local/share/postgresql/extension/pg_search--${PG_SEARCH_VERSION}.sql"
