"""Colab 一次性初始化：NVIDIA 动态库、Tailscale、SSH 和 LiveTalking 8010。

在 Colab GPU Runtime 中以 root 执行；Tailscale 登录需要在输出的授权链接完成一次授权。
"""
import json
import os
import subprocess
import time
from pathlib import Path

def run(*args):
    shown = ["tskey-auth-***" if arg.startswith("tskey-") else arg for arg in args]
    print("$", " ".join(shown))
    result = subprocess.run(args, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise RuntimeError(f"命令失败 ({result.returncode}): {' '.join(shown)}\n{detail}")

print("=== 1. 配置全局动态链接库路径 ===")
nvidia_ld_path = "/etc/ld.so.conf.d/nvidia.conf"
Path(nvidia_ld_path).write_text(
    "/usr/lib64-nvidia\n/usr/local/nvidia/lib\n/usr/local/nvidia/lib64\n"
)
run("ldconfig")
print("✅ 动态链接库路径加载完毕。")

print("\n=== 2. 注入全局 PATH 环境变量 ===")
profile_path = "/etc/profile.d/nvidia.sh"
Path(profile_path).write_text(
    'export PATH="/usr/local/nvidia/bin:/usr/local/cuda/bin:$PATH"\n'
    'export LD_LIBRARY_PATH="/usr/lib64-nvidia:/usr/local/nvidia/lib:/usr/local/nvidia/lib64:$LD_LIBRARY_PATH"\n'
)
os.environ["PATH"] = "/usr/local/nvidia/bin:/usr/local/cuda/bin:" + os.environ.get("PATH", "")
os.environ["LD_LIBRARY_PATH"] = "/usr/lib64-nvidia:/usr/local/nvidia/lib:/usr/local/nvidia/lib64:" + os.environ.get("LD_LIBRARY_PATH", "")
print("✅ 全局环境配置完成。")

print("\n=== 3. 安装 Tailscale 与 SSH ===")
run("bash", "-lc", "curl -fsSL https://tailscale.com/install.sh | sh")
run("apt-get", "update")
run("apt-get", "install", "-y", "openssh-server")
run("mkdir", "-p", "/run/sshd")
run("service", "ssh", "start")
print("✅ SSH 服务已启动。")

print("\n=== 4. 登录 Tailscale ===")
tailscale_authkey = os.getenv("TS_AUTHKEY", "tskey-auth-REPLACE_ME")
if tailscale_authkey == "tskey-auth-REPLACE_ME":
    raise RuntimeError("请先设置 TS_AUTHKEY，再运行脚本。")
# Colab 不允许创建内核 TUN。先停掉安装脚本拉起的内核模式守护进程，再用用户态网络启动。
subprocess.run(["systemctl", "disable", "--now", "tailscaled"], check=False)
subprocess.run(["pkill", "-9", "tailscaled"], check=False)
time.sleep(0.5)
for path in ("/var/run/tailscale", "/var/lib/tailscale", "/dev/net"):
    Path(path).mkdir(parents=True, exist_ok=True)
if not Path("/dev/net/tun").exists():
    subprocess.run(["mknod", "/dev/net/tun", "c", "10", "200"], check=False)
log_file = open("/tmp/tailscaled.log", "w")
subprocess.Popen(
    ["tailscaled", "--tun=userspace-networking"],
    stdout=log_file,
    stderr=subprocess.STDOUT,
)
ready = False
for _ in range(20):
    status = subprocess.run(["tailscale", "status"], capture_output=True, text=True)
    output = f"{status.stdout}\n{status.stderr}"
    # 未登录时 status 也是退出码 1，输出 "Logged out."，这表示守护进程已经在听。
    if status.returncode == 0 or "Logged out" in output:
        ready = True
        break
    time.sleep(0.5)
if not ready:
    log_file.flush()
    log_text = Path("/tmp/tailscaled.log").read_text(errors="replace")[-2000:]
    raise RuntimeError(f"tailscaled 没有在超时内启动。\n{log_text}")
run(
    "tailscale", "up",
    "--reset",
    "--authkey", tailscale_authkey,
    "--accept-dns=false",
    "--hostname=colab-livetalking",
    "--ssh",
    "--ephemeral",
)
print("\n=== 5. 检查 GPU 与 Tailscale 地址 ===")
subprocess.run(["nvidia-smi"], check=False)
tailscale_ip = subprocess.check_output(["tailscale", "ip", "-4"], text=True).strip()
status = json.loads(subprocess.check_output(["tailscale", "status", "--json"], text=True))
dns_name = status["Self"]["DNSName"].rstrip(".")
print(f"Tailscale IPv4: {tailscale_ip}")
print(f"固定地址: {dns_name}:8010")
print("✅ 节点初始化完成。IP 会变，客户端请用上面的固定地址。")

