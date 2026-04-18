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

# Project directories
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

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
    pool = "solo" if concurrency == 1 else None
    start_worker(concurrency=concurrency, queues="sandbox", pool=pool)


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
        start_sandbox_worker(concurrency=args.concurrency)
    elif args.command == "beat":
        start_beat()
    elif args.command == "flower":
        start_flower(port=args.port)


if __name__ == "__main__":
    main()
