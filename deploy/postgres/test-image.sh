#!/bin/sh
set -eu

IMAGE=${1:?usage: test-image.sh IMAGE}
MAX_SIZE=500000000
NAME="clouisle-pg-search-test-$$"
VOLUME="${NAME}-data"
LOG_FILE=$(mktemp)

cleanup() {
    status=$?
    if [ "$status" -ne 0 ] && docker container inspect "$NAME" >/dev/null 2>&1; then
        docker logs "$NAME" >"$LOG_FILE" 2>&1 || true
        printf '%s\n' '--- PostgreSQL logs ---' >&2
        cat "$LOG_FILE" >&2
    fi
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    docker volume rm -f "$VOLUME" >/dev/null 2>&1 || true
    rm -f "$LOG_FILE"
    exit "$status"
}
trap cleanup EXIT INT TERM

size=$(docker image inspect --format '{{.Size}}' "$IMAGE")
architecture=$(docker image inspect --format '{{.Architecture}}' "$IMAGE")
image_id=$(docker image inspect --format '{{.Id}}' "$IMAGE")
[ "$size" -lt "$MAX_SIZE" ] || {
    echo "image is $size bytes; required size is below $MAX_SIZE" >&2
    exit 1
}

extension_size=$(docker run --rm --entrypoint stat "$IMAGE" \
    -c '%s' /usr/local/lib/postgresql/pg_search.so)
printf 'image=%s architecture=%s id=%s size=%s pg_search_so=%s\n' \
    "$IMAGE" "$architecture" "$image_id" "$size" "$extension_size"

docker volume create "$VOLUME" >/dev/null
start_postgres() {
    docker run -d --name "$NAME" \
        -e POSTGRES_PASSWORD=test-password \
        -v "$VOLUME:/var/lib/postgresql/data" \
        "$IMAGE" postgres \
        -c shared_preload_libraries=pg_search,pg_stat_statements \
        -c pg_stat_statements.track=all >/dev/null
    attempts=0
    consecutive_ready=0
    while [ "$consecutive_ready" -lt 2 ]; do
        if docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1; then
            consecutive_ready=$((consecutive_ready + 1))
        else
            consecutive_ready=0
        fi
        attempts=$((attempts + 1))
        [ "$attempts" -lt 60 ] || return 1
        sleep 1
    done
}

psql() {
    docker exec -i "$NAME" psql -v ON_ERROR_STOP=1 -U postgres "$@"
}

start_postgres
psql <<'SQL'
CREATE EXTENSION IF NOT EXISTS pg_search CASCADE;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

DO $$
BEGIN
    IF current_setting('server_version_num')::integer / 10000 <> 17 THEN
        RAISE EXCEPTION 'PostgreSQL 17 required';
    END IF;
    IF (SELECT extversion FROM pg_extension WHERE extname = 'pg_search') <> '0.24.3' THEN
        RAISE EXCEPTION 'pg_search 0.24.3 required';
    END IF;
    IF current_setting('shared_preload_libraries') <> 'pg_search,pg_stat_statements' THEN
        RAISE EXCEPTION 'unexpected preload libraries';
    END IF;
    IF current_setting('pg_stat_statements.track') <> 'all' THEN
        RAISE EXCEPTION 'pg_stat_statements.track must be all';
    END IF;
END $$;

CREATE TABLE knowledge_lexical_chunks (
    chunk_id UUID PRIMARY KEY,
    document_id UUID NOT NULL,
    kb_id UUID NOT NULL,
    team_id UUID NOT NULL,
    status TEXT NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    chunk_index INTEGER NOT NULL,
    update_version BIGINT NOT NULL,
    language TEXT,
    section TEXT,
    title TEXT NOT NULL,
    identifiers TEXT[] NOT NULL DEFAULT ARRAY[]::text[]
);
CREATE INDEX knowledge_lexical_chunks_bm25_idx
ON knowledge_lexical_chunks
USING bm25 (
    chunk_id, team_id, kb_id, document_id, status,
    (content::pdb.jieba), (title::pdb.jieba), (name::pdb.jieba),
    (section::pdb.jieba), identifiers, chunk_index, update_version
)
WITH (key_field = 'chunk_id');
CREATE INDEX knowledge_lexical_chunks_team_kb_idx
ON knowledge_lexical_chunks (team_id, kb_id);
CREATE INDEX knowledge_lexical_chunks_team_document_idx
ON knowledge_lexical_chunks (team_id, document_id);

INSERT INTO knowledge_lexical_chunks (
    chunk_id, document_id, kb_id, team_id, status, name, content,
    chunk_index, update_version, language, section, title, identifiers
) VALUES
('00000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', 'embedded', '数据库手册', '数据库连接超时 ERR-42', 0, 1, 'zh', '故障处理', '连接故障', ARRAY['ERR-42']),
('00000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', 'embedded', 'Clouisle Guide', 'Clouisle 数据库 BM25 检索 config.key/v2', 0, 1, 'mixed', 'Search', 'Hybrid search', ARRAY['config.key/v2', 'pg_search-0.24.3']),
('00000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000003', '20000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000002', 'embedded', 'Other tenant', '数据库连接超时 ERR-42', 0, 1, 'zh', '隔离', '连接故障', ARRAY['ERR-42']);

DO $$
DECLARE
    found_id UUID;
    found_score REAL;
    match_count INTEGER;
BEGIN
    SELECT chunk_id, pdb.score(chunk_id)
    INTO found_id, found_score
    FROM knowledge_lexical_chunks
    WHERE team_id = '30000000-0000-0000-0000-000000000001'
      AND kb_id = '20000000-0000-0000-0000-000000000001'
      AND content ||| '连接超时'::pdb.jieba
    ORDER BY pdb.score(chunk_id) DESC
    LIMIT 1;
    IF found_id <> '00000000-0000-0000-0000-000000000001' OR found_score <= 0 THEN
        RAISE EXCEPTION 'Chinese BM25 query failed';
    END IF;

    SELECT chunk_id INTO found_id
    FROM knowledge_lexical_chunks
    WHERE team_id = '30000000-0000-0000-0000-000000000001'
      AND content ||| 'Clouisle 数据库 BM25'::pdb.jieba
    ORDER BY pdb.score(chunk_id) DESC
    LIMIT 1;
    IF found_id <> '00000000-0000-0000-0000-000000000002' THEN
        RAISE EXCEPTION 'mixed-language BM25 query failed';
    END IF;

    SELECT chunk_id INTO found_id
    FROM knowledge_lexical_chunks
    WHERE team_id = '30000000-0000-0000-0000-000000000001'
      AND title ||| ('Hybrid search'::pdb.jieba)::pdb.boost(2)
    ORDER BY pdb.score(chunk_id) DESC
    LIMIT 1;
    IF found_id <> '00000000-0000-0000-0000-000000000002' THEN
        RAISE EXCEPTION 'boosted title query failed';
    END IF;

    SELECT chunk_id INTO found_id
    FROM knowledge_lexical_chunks
    WHERE team_id = '30000000-0000-0000-0000-000000000001'
      AND (
          content ||| 'no lexical match'::pdb.jieba
          OR identifiers && ARRAY['ERR-42']::text[]
      )
    ORDER BY (identifiers && ARRAY['ERR-42']::text[]) DESC,
             pdb.score(chunk_id) DESC
    LIMIT 1;
    IF found_id <> '00000000-0000-0000-0000-000000000001' THEN
        RAISE EXCEPTION 'production identifier query failed';
    END IF;

    SELECT count(*) INTO match_count
    FROM knowledge_lexical_chunks
    WHERE team_id = '30000000-0000-0000-0000-000000000001'
      AND document_id = '10000000-0000-0000-0000-000000000002'
      AND identifiers && ARRAY['config.key/v2', 'pg_search-0.24.3']::text[];
    IF match_count <> 1 THEN
        RAISE EXCEPTION 'path and version identifier query failed';
    END IF;

    SELECT count(*) INTO match_count
    FROM knowledge_lexical_chunks
    WHERE team_id = '30000000-0000-0000-0000-000000000001'
      AND document_id = '10000000-0000-0000-0000-000000000099'
      AND content ||| '数据库'::pdb.jieba;
    IF match_count <> 0 THEN
        RAISE EXCEPTION 'document isolation failed';
    END IF;
END $$;

SELECT count(*) FROM pg_stat_statements;
SQL

plan=$(psql -Atc "EXPLAIN SELECT chunk_id FROM knowledge_lexical_chunks WHERE content ||| '连接超时'::pdb.jieba ORDER BY pdb.score(chunk_id) DESC LIMIT 1")
printf '%s\n' "$plan"
printf '%s\n' "$plan" | grep -Eiq 'bm25|knowledge_lexical_chunks_bm25_idx|custom scan'

psql <<'SQL'
UPDATE knowledge_lexical_chunks
SET content = '数据库连接已经恢复', identifiers = ARRAY['RECOVERED-43'], update_version = 2
WHERE chunk_id = '00000000-0000-0000-0000-000000000001';
DELETE FROM knowledge_lexical_chunks
WHERE chunk_id = '00000000-0000-0000-0000-000000000002';
CHECKPOINT;
SQL

docker stop "$NAME" >/dev/null
docker rm "$NAME" >/dev/null
start_postgres
psql -Atc "SELECT extversion FROM pg_extension WHERE extname = 'pg_search'" | grep -qx '0.24.3'
psql -Atc "SELECT chunk_id FROM knowledge_lexical_chunks WHERE content ||| '已经恢复'::pdb.jieba" | grep -qx '00000000-0000-0000-0000-000000000001'
[ "$(psql -Atc "SELECT count(*) FROM knowledge_lexical_chunks WHERE content ||| 'Clouisle'::pdb.jieba")" = '0' ]

psql -c "INSERT INTO knowledge_lexical_chunks (chunk_id, document_id, kb_id, team_id, status, name, content, chunk_index, update_version, title) VALUES ('00000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000004', '20000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', 'embedded', 'Recovery', '崩溃恢复检索', 1, 1, 'Recovery')"
docker kill -s KILL "$NAME" >/dev/null
docker rm "$NAME" >/dev/null
start_postgres
psql -Atc "SELECT chunk_id FROM knowledge_lexical_chunks WHERE content ||| '崩溃恢复'::pdb.jieba" | grep -qx '00000000-0000-0000-0000-000000000004'

if docker logs "$NAME" 2>&1 | grep -Eiq 'panic|segmentation fault|relocation error'; then
    echo 'fatal PostgreSQL error found in logs' >&2
    exit 1
fi

echo 'PostgreSQL pg_search image checks passed.'
