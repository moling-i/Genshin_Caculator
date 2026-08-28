# -*- coding: utf-8 -*-
"""
原神伤害计算器 - 一键启动脚本

功能：
    1. 自动启动 FastAPI 后端服务 (backend.py)
    2. 自动启动 Streamlit 前端应用 (frontend.py)
    3. 自动打开浏览器访问前端页面
    4. 按 Ctrl+C 可优雅停止所有服务

用法：
    python run.py
"""

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

# Windows 控制台默认 GBK 编码，无法输出 emoji 等字符，强制使用 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_HOST = "localhost"
FRONTEND_PORT = 8501

BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
FRONTEND_URL = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"

HEALTH_URL = f"{BACKEND_URL}/health"

# Windows 下隐藏子进程黑色窗口的标志（若不需要隐藏请改为 0）
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def print_banner():
    """打印启动横幅"""
    print("=" * 56)
    print("   原神伤害计算器 - 一键启动  ")
    print("=" * 56)
    print(f"  后端: FastAPI    -> {BACKEND_URL}")
    print(f"  前端: Streamlit  -> {FRONTEND_URL}")
    print("=" * 56)
    print()


def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    """检测指定端口是否已被监听"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def wait_for_port(port: int, timeout: int = 60, name: str = "服务") -> bool:
    """等待端口开放，超时返回 False"""
    print(f"[*] 等待 {name} 启动 (最多 {timeout} 秒)...")
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(port):
            print(f"[✓] {name} 已就绪 (端口 {port})")
            return True
        time.sleep(1)
    print(f"[✗] {name} 启动超时 (端口 {port})")
    return False


def start_backend() -> subprocess.Popen | None:
    """启动后端服务；若端口已被占用则复用现有服务"""
    if is_port_open(BACKEND_PORT):
        print(f"[*] 端口 {BACKEND_PORT} 已有服务在运行，将复用现有后端")
        return None

    print("[*] 正在启动后端服务 (backend.py)...")
    try:
        proc = subprocess.Popen(
            [sys.executable, "backend.py"],
            cwd=BASE_DIR,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as exc:
        print(f"[✗] 后端启动失败: {exc}")
        return None

    if not wait_for_port(BACKEND_PORT, timeout=60, name="后端"):
        proc.terminate()
        print("[✗] 后端未能正常启动，已终止进程")
        return None

    return proc


def start_frontend(backend_proc: subprocess.Popen | None) -> subprocess.Popen | None:
    """启动前端服务；若端口已被占用则复用现有服务"""
    if is_port_open(FRONTEND_PORT):
        print(f"[*] 端口 {FRONTEND_PORT} 已有服务在运行，将复用现有前端")
        return None

    print("[*] 正在启动前端应用 (frontend.py)...")
    # --server.headless true: 无头模式，避免交互式提示，不自动打开浏览器
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "frontend.py",
        "--server.headless",
        "true",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as exc:
        print(f"[✗] 前端启动失败: {exc}")
        return None

    if not wait_for_port(FRONTEND_PORT, timeout=60, name="前端"):
        proc.terminate()
        print("[✗] 前端未能正常启动，已终止进程")
        return None

    return proc


def stop_process(proc: subprocess.Popen | None, name: str) -> None:
    """优雅停止子进程，必要时强制终止"""
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except (subprocess.TimeoutExpired, Exception):
        try:
            proc.kill()
        except Exception:
            pass
    print(f"[✓] 已停止 {name}")


def main() -> int:
    """主流程"""
    print_banner()

    # 依赖预检
    print("[*] 检查依赖...")
    try:
        import streamlit  # noqa: F401
        import fastapi     # noqa: F401
    except ImportError as exc:
        print(f"[✗] 缺少依赖: {exc}")
        print("    请先执行: pip install -r requirements.txt")
        return 1
    print("[✓] 依赖检查通过")

    backend_proc = None
    frontend_proc = None

    try:
        # 1. 启动后端
        backend_proc = start_backend()
        if backend_proc is None and not is_port_open(BACKEND_PORT):
            return 1

        # 2. 验证后端健康状态
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=3) as resp:
                print(f"[✓] 后端健康检查通过: {resp.status}")
        except Exception as exc:
            print(f"[✗] 后端健康检查失败: {exc}")
            return 1

        # 3. 启动前端
        frontend_proc = start_frontend(backend_proc)
        if frontend_proc is None and not is_port_open(FRONTEND_PORT):
            return 1

        # 4. 打开浏览器
        print(f"[*] 正在打开浏览器: {FRONTEND_URL}")
        webbrowser.open(FRONTEND_URL)

        # 5. 保持运行，直到用户按 Ctrl+C
        print()
        print("=" * 56)
        print("  所有服务已启动！")
        print(f"  前端页面: {FRONTEND_URL}")
        print(f"  后端文档: {BACKEND_URL}/docs")
        print(f"  API测试 : {BACKEND_URL}/health")
        print()
        print("  按 Ctrl+C 停止所有服务")
        print("=" * 56)
        print()

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print()
        print("[*] 收到退出信号，正在停止服务...")

    finally:
        stop_process(frontend_proc, "前端 (Streamlit)")
        stop_process(backend_proc, "后端 (FastAPI)")
        print("[✓] 所有服务已停止，感谢使用！")

    return 0


if __name__ == "__main__":
    sys.exit(main())