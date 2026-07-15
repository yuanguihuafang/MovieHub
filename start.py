"""
一键启动前后端：
  - 后端：python backend/main.py（FastAPI, port 8000）
  - 前端：npm run dev（Vite, port 5173）

用法：
  python start.py
"""

import subprocess
import sys
import os
import signal

ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(ROOT, "frontend", "movie-app")

processes = []


def cleanup(signum=None, frame=None):
    for p in processes:
        if p.poll() is None:
            p.terminate()
    for p in processes:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

if __name__ == "__main__":
    print("=" * 50)
    print("  MovieHub 一键启动")
    print("=" * 50)

    # 启动后端
    print("\n[1/2] 启动后端 (FastAPI, port 8000) ...")
    backend = subprocess.Popen(
        [sys.executable, "backend/main.py"],
        cwd=ROOT,
    )
    processes.append(backend)

    # 启动前端
    print("[2/2] 启动前端 (Vite, port 5173) ...")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    frontend = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=FRONTEND_DIR,
    )
    processes.append(frontend)

    print("\n" + "=" * 50)
    print("  后端: http://localhost:8000/docs")
    print("  前端: http://localhost:5173")
    print("  按 Ctrl+C 停止所有服务")
    print("=" * 50 + "\n")

    # 等待任一进程退出
    while True:
        for p in processes:
            if p.poll() is not None:
                print(f"\n[!] 进程退出 (code={p.returncode})，正在停止所有服务...")
                cleanup()
        try:
            signal.pause()
        except AttributeError:
            # Windows 没有 signal.pause，用 wait 代替
            import time
            time.sleep(1)
