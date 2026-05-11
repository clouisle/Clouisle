#!/usr/bin/env python
"""
Clouisle Startup Script
Run this file from the project root to start backend services.

Usage:
    python main.py server    - Start the backend API server (dev, uvicorn)
    python main.py server --no-reload        - Start production (gunicorn)
    python main.py worker    - Start the Celery worker
    python main.py sandbox-worker            - Start the sandbox worker
    python main.py beat      - Start the Celery beat scheduler
    python main.py flower    - Start the Flower monitoring (if installed)
"""
import os
import sys
import argparse
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

# Project directories
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
SANDBOX_WORKER_IMAGE_TAG = "clouisle-sandbox-worker:dev"
SANDBOX_WORKER_ENV_KEYS = (
    "API_BASE_URL",
    "DATABASE_URL",
    "POSTGRES_SERVER",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_PORT",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_PASSWORD",
    "VECTOR_BACKEND",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_COLLECTION_PREFIX",
    "QDRANT_DISTANCE",
    "SECRET_KEY",
    "SANDBOX_RUNTIME_ENABLED",
    "SANDBOX_LEGACY_FALLBACK_ENABLED",
    "SANDBOX_WORKSPACE_ROOT",
    "SANDBOX_MAX_DISK_MB",
    "SANDBOX_SESSION_TTL_HOURS",
    "SANDBOX_SESSION_CLEANUP_BATCH_SIZE",
    "SANDBOX_RESULT_TTL_SECONDS",
    "SANDBOX_ARTIFACT_UPLOAD_BASE_URL",
    "SANDBOX_ARTIFACT_UPLOAD_API_KEY",
)

# Add backend directory to Python path
sys.path.insert(0, BACKEND_DIR)


def start_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = True,
    workers: int = 0,
):
    """Start the FastAPI backend server.

    Dev mode (reload=True): single-process uvicorn with hot-reload.
    Production mode (reload=False): Gunicorn with UvicornWorker for
    multi-process, graceful shutdown, and worker management.
    """
    os.chdir(BACKEND_DIR)

    if reload:
        import uvicorn

        print(f"🚀 Starting Clouisle API server (dev) at http://{host}:{port}")
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port,
            reload=True,
            reload_dirs=[BACKEND_DIR],
        )
    else:
        if workers <= 0:
            workers = min(os.cpu_count() or 1, 4) * 2 + 1

        print(
            f"🚀 Starting Clouisle API server (production) at http://{host}:{port} "
            f"with {workers} workers"
        )
        cmd = [
            sys.executable, "-m", "gunicorn",
            "app.main:app",
            "-k", "uvicorn.workers.UvicornWorker",
            "--bind", f"{host}:{port}",
            "--workers", str(workers),
            "--graceful-timeout", "30",
            "--timeout", "120",
            "--keep-alive", "5",
            "--access-logfile", "-",
            "--error-logfile", "-",
            "--forwarded-allow-ips", "*",
        ]
        subprocess.run(cmd)


def start_worker(
    concurrency: int = 4,
    queues: str = "default,workflow",
    *,
    pool: str | None = None,
):
    """Start the Celery worker."""
    os.chdir(BACKEND_DIR)

    print(
        f"🔧 Starting Celery worker (concurrency={concurrency}, queues={queues}, pool={pool or 'prefork'})"
    )
    cmd = [
        sys.executable, "-m", "celery",
        "-A", "app.core.celery:celery_app",
        "worker",
        "--loglevel=info",
        f"--concurrency={concurrency}",
        f"--queues={queues}",
    ]
    if pool:
        cmd.append(f"--pool={pool}")
    subprocess.run(cmd)


def start_sandbox_worker(concurrency: int = 1):
    """Start the dedicated sandbox worker."""
    os.chdir(BACKEND_DIR)
    pool = "solo" if concurrency == 1 else None

    print(
        f"🔧 Starting Celery worker (concurrency={concurrency}, queues=sandbox, pool={pool or 'prefork'})"
    )
    cmd = [
        os.path.join(BACKEND_DIR, ".venv", "bin", "python"), "-m", "celery",
        "-A", "app.core.celery:celery_app",
        "worker",
        "--loglevel=info",
        f"--concurrency={concurrency}",
        "--queues=sandbox",
    ]
    if pool:
        cmd.append(f"--pool={pool}")
    subprocess.run(cmd)


def build_sandbox_worker_image(
    *,
    no_cache: bool = False,
    image_tag: str = SANDBOX_WORKER_IMAGE_TAG,
):
    """Build the sandbox worker image from the repository root."""
    cmd = [
        "docker", "build",
        "-f", "deploy/dockerfiles/sandbox-worker.Dockerfile",
        "-t", image_tag,
    ]
    if no_cache:
        cmd.append("--no-cache")
    cmd.append(".")
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)


def _load_root_env_file() -> dict[str, str]:
    env_path = Path(PROJECT_ROOT) / ".env"
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _map_local_url_to_host_gateway(url: str | None) -> str | None:
    if not url:
        return url
    parts = urlsplit(url)
    if parts.hostname not in {"localhost", "127.0.0.1"}:
        return url
    host = "host.docker.internal"
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


def _sandbox_worker_container_env() -> dict[str, str]:
    root_env = _load_root_env_file()
    env = {key: value for key in SANDBOX_WORKER_ENV_KEYS if (value := root_env.get(key))}
    env.update({key: value for key in SANDBOX_WORKER_ENV_KEYS if (value := os.environ.get(key))})
    if env.get("REDIS_HOST") in {None, "localhost", "127.0.0.1"}:
        env["REDIS_HOST"] = "host.docker.internal"
    if env.get("POSTGRES_SERVER") in {None, "localhost", "127.0.0.1"}:
        env["POSTGRES_SERVER"] = "host.docker.internal"
    qdrant_url = env.get("QDRANT_URL")
    if not qdrant_url:
        env["QDRANT_URL"] = "http://host.docker.internal:6333"
    else:
        env["QDRANT_URL"] = _map_local_url_to_host_gateway(qdrant_url)

    api_base_url = env.get("API_BASE_URL")
    if api_base_url:
        env["API_BASE_URL"] = _map_local_url_to_host_gateway(api_base_url)

    artifact_upload_base_url = env.get("SANDBOX_ARTIFACT_UPLOAD_BASE_URL")
    if artifact_upload_base_url:
        env["SANDBOX_ARTIFACT_UPLOAD_BASE_URL"] = _map_local_url_to_host_gateway(
            artifact_upload_base_url
        )
    elif api_base_url:
        env["SANDBOX_ARTIFACT_UPLOAD_BASE_URL"] = env["API_BASE_URL"]

    return env


def start_sandbox_worker_container(
    concurrency: int = 1,
    *,
    no_cache: bool = False,
    image_tag: str = SANDBOX_WORKER_IMAGE_TAG,
):
    """Build and run a temporary local-dev sandbox worker container."""
    build_sandbox_worker_image(no_cache=no_cache, image_tag=image_tag)
    cmd = [
        "docker", "run", "--rm",
        "--name", f"clouisle-sandbox-worker-dev-{os.getpid()}",
    ]
    for key, value in _sandbox_worker_container_env().items():
        cmd.extend(["-e", f"{key}={value}"])
    cmd.extend([
        image_tag,
        "python", "main.py", "sandbox-worker",
        "-c", str(concurrency),
    ])
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)


def start_beat():
    """Start the Celery beat scheduler."""
    os.chdir(BACKEND_DIR)
    
    print("⏰ Starting Celery beat scheduler")
    cmd = [
        sys.executable, "-m", "celery",
        "-A", "app.core.celery:celery_app",
        "beat",
        "--loglevel=info",
    ]
    subprocess.run(cmd)


def start_flower(port: int = 5555):
    """Start the Flower monitoring dashboard."""
    os.chdir(BACKEND_DIR)
    
    print(f"🌸 Starting Flower at http://localhost:{port}")
    cmd = [
        sys.executable, "-m", "celery",
        "-A", "app.core.celery:celery_app",
        "flower",
        f"--port={port}",
    ]
    subprocess.run(cmd)


def main():
    parser = argparse.ArgumentParser(
        description="Clouisle - Start backend services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py server                    Start API server (dev mode, uvicorn)
  python main.py server --no-reload        Start API server (production, gunicorn)
  python main.py server --no-reload -w 8   Start production with 8 workers
  python main.py server -p 8080            Start API server on port 8080
  python main.py worker                    Start Celery worker
  python main.py worker -c 8               Start worker with 8 processes
  python main.py sandbox-worker            Start sandbox worker (solo pool by default)
  python main.py sandbox-worker -c 2       Start sandbox worker with 2 prefork processes
  python main.py sandbox-worker --local-dev -c 1
                                             Build and run sandbox worker dev container
  python main.py beat                      Start Celery beat scheduler
  python main.py flower                    Start Flower monitoring
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Server command
    server_parser = subparsers.add_parser("server", help="Start the API server")
    server_parser.add_argument("-H", "--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    server_parser.add_argument("-p", "--port", type=int, default=8000, help="Port to bind (default: 8000)")
    server_parser.add_argument("-w", "--workers", type=int, default=0, help="Number of Gunicorn workers (default: auto, production only)")
    server_parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload (use Gunicorn for production)")
    
    # Worker command
    worker_parser = subparsers.add_parser("worker", help="Start the Celery worker")
    worker_parser.add_argument("-c", "--concurrency", type=int, default=4, help="Number of worker processes (default: 4)")
    worker_parser.add_argument("-Q", "--queues", default="default,workflow", help="Queues to consume (default: default,workflow)")
    
    # Sandbox worker command
    sandbox_worker_parser = subparsers.add_parser("sandbox-worker", help="Start the sandbox worker")
    sandbox_worker_parser.add_argument("-c", "--concurrency", type=int, default=1, help="Number of sandbox worker processes (default: 1)")
    sandbox_worker_parser.add_argument("--local-dev", action="store_true", help="Build and run the sandbox worker in a temporary local dev container")
    sandbox_worker_parser.add_argument("--no-cache", action="store_true", help="Build the local dev sandbox image without Docker cache")
    sandbox_worker_parser.add_argument("--image-tag", default=SANDBOX_WORKER_IMAGE_TAG, help=f"Local dev sandbox image tag (default: {SANDBOX_WORKER_IMAGE_TAG})")

    # Beat command
    subparsers.add_parser("beat", help="Start the Celery beat scheduler")
    
    # Flower command
    flower_parser = subparsers.add_parser("flower", help="Start Flower monitoring")
    flower_parser.add_argument("-p", "--port", type=int, default=5555, help="Flower port (default: 5555)")
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    if args.command == "server":
        start_server(host=args.host, port=args.port, reload=not args.no_reload, workers=args.workers)
    elif args.command == "worker":
        start_worker(concurrency=args.concurrency, queues=args.queues)
    elif args.command == "sandbox-worker":
        if args.local_dev:
            start_sandbox_worker_container(
                concurrency=args.concurrency,
                no_cache=args.no_cache,
                image_tag=args.image_tag,
            )
        else:
            start_sandbox_worker(concurrency=args.concurrency)
    elif args.command == "beat":
        start_beat()
    elif args.command == "flower":
        start_flower(port=args.port)


if __name__ == "__main__":
    main()
