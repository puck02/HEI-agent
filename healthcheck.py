#!/usr/bin/env python3
"""HEI-agent 服务健康检查脚本 — 每8小时由 cron 调用"""
import subprocess, sys, time

WORKDIR = "/home/admin/workspace/HEI-agent"
VENV_PYTHON = f"{WORKDIR}/.venv/bin/python3"
FRONTEND_DIR = f"{WORKDIR}/demo-frontend"

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def check_port(port):
    """检查端口是否可访问"""
    r = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"http://localhost:{port}/"],
        capture_output=True, text=True, timeout=10
    )
    return r.stdout.strip() == "200"

def check_health():
    r = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:8000/health"],
        capture_output=True, text=True, timeout=10
    )
    return r.stdout.strip() == "200"

def ensure_backend():
    """确保后端运行"""
    pid = subprocess.run(
        ["pgrep", "-f", "uvicorn app.main"],
        capture_output=True, text=True
    ).stdout.strip()
    if pid:
        log(f"后端运行中 (PID: {pid})")
        return True

    log("⚠️ 后端离线，正在重启...")
    r = subprocess.Popen(
        [VENV_PYTHON, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=WORKDIR,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    # 等它启动（LiteLLM 导入需要约20秒）
    for i in range(30):
        time.sleep(2)
        if check_health():
            log(f"✅ 后端已启动 (PID: {r.pid})")
            return True
    log("❌ 后端启动失败")
    return False

def ensure_frontend():
    """确保前端运行"""
    pid = subprocess.run(
        ["pgrep", "-f", "vite"],
        capture_output=True, text=True
    ).stdout.strip()
    if pid:
        log(f"前端运行中 (PID: {pid})")
        return True

    log("⚠️ 前端离线，正在重启...")
    r = subprocess.Popen(
        ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"],
        cwd=FRONTEND_DIR,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    for i in range(15):
        time.sleep(2)
        if check_port(5173):
            log(f"✅ 前端已启动 (PID: {r.pid})")
            return True
    log("❌ 前端启动失败")
    return False

def ensure_qdrant():
    """确保 Qdrant 容器运行"""
    r = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}", "--filter", "name=hel-qdrant"],
        capture_output=True, text=True, timeout=10
    )
    if "hel-qdrant" in r.stdout:
        log("✅ Qdrant 容器运行中")
        return True
    log("⚠️ Qdrant 容器离线，正在重启...")
    r = subprocess.run(
        ["docker", "start", "hel-qdrant"],
        capture_output=True, text=True, timeout=15
    )
    if r.returncode == 0:
        log("✅ Qdrant 已启动")
        return True
    log("❌ Qdrant 启动失败")
    return False

if __name__ == "__main__":
    log("=== HEI-agent 服务巡检 ===")
    results = []
    results.append(("Qdrant",   ensure_qdrant()))
    results.append(("Backend",  ensure_backend()))
    results.append(("Frontend", ensure_frontend()))

    log("---")
    all_ok = all(r for _, r in results)
    for name, ok in results:
        status = "✅" if ok else "❌"
        log(f"{status} {name}")
    log(f"{'✅ 全部正常' if all_ok else '❌ 存在异常'}")
    sys.exit(0 if all_ok else 1)
