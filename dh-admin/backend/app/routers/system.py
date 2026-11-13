"""系统操作：重启目标设置、把默认角色的 DSH 大脑配置推送到展示端并重启（只重启 8000）。

两个目标：
- dsw：展示端在 DSW 上以独立进程跑 uvicorn，通过 SSH（Tailscale）改写其 .env 的
  DSH 四行配置，再按原命令行重启 8000 进程。
- local：展示端在本机（Mac）跑，后端直接改写本机展示端 .env 并重启本机 8000 进程。
引擎（8010）都不在此列。
"""

import os
import re
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import AppSetting, Brain, Persona
from app.schemas import RestartDisplayIn, SystemSettingsIn
from app.services.personas import decrypted_brain_key

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(get_current_user)])

DEFAULT_DSW_HOST = "colab-livetalking-1.YOUR-HOST.ts.net"
_HOST_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_STEP_NAMES = {
    "push": "推送大脑配置",
    "stop": "停止旧展示端",
    "start": "启动展示端（8000）",
    "health": "健康检查",
}
_DSH_KEYS = ("DSH_BASE_URL", "DSH_APP_ID", "DSH_APP_SECRET", "DSH_AGENT_ID")

_REPO_ROOT = Path(__file__).resolve().parents[4]
LOCAL_DISPLAY_DIR = _REPO_ROOT / "fine-digital-human"
LOCAL_PYTHON = _REPO_ROOT / "dh-admin" / "backend" / ".venv" / "bin" / "python"
LOCAL_LOG = LOCAL_DISPLAY_DIR / "local-8000.log"
LOCAL_PID_FILE = LOCAL_DISPLAY_DIR / "local-8000.pid"

REMOTE_SCRIPT = r"""
set -u
DIR=/content/livetalking/fine-digital-human
cd "$DIR" || { echo "STEP_FAIL:push"; echo "STEP_FAIL:stop"; echo "STEP_FAIL:start"; echo "STEP_FAIL:health"; exit 1; }
if [ -f /tmp/dsh-push.env ]; then
  keys=$(cut -d= -f1 /tmp/dsh-push.env | grep -E '^[A-Za-z_][A-Za-z0-9_]*$' | paste -sd'|' -)
  if [ -n "$keys" ]; then
    grep -vE "^[[:space:]]*#?[[:space:]]*(${keys})[[:space:]]*=" .env > .env.tmp || true
  else
    cp .env .env.tmp
  fi
  cat /tmp/dsh-push.env >> .env.tmp
  mv .env.tmp .env
  rm -f /tmp/dsh-push.env
  echo "STEP_OK:push"
else
  echo "STEP_SKIP:push"
fi
pid=$(ss -tlnp 2>/dev/null | grep ':8000 ' | grep -oE 'pid=[0-9]+' | head -n1 | cut -d= -f2)
if [ -n "${pid:-}" ]; then kill "$pid" 2>/dev/null || true; fi
for i in $(seq 1 20); do
  ss -tln 2>/dev/null | grep -q ':8000 ' || break
  sleep 0.5
done
if ss -tln 2>/dev/null | grep -q ':8000 '; then
  if [ -n "${pid:-}" ]; then kill -9 "$pid" 2>/dev/null || true; fi
  sleep 1
fi
if ss -tln 2>/dev/null | grep -q ':8000 '; then echo "STEP_FAIL:stop"; else echo "STEP_OK:stop"; fi
cd "$DIR"
setsid nohup python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 --ssl-certfile /content/livetalking/certs/page.crt --ssl-keyfile /content/livetalking/certs/page.key >> /tmp/fine-digital-human.log 2>&1 < /dev/null &
echo "STEP_OK:start"
ok=0
for i in $(seq 1 45); do
  code=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8000/ 2>/dev/null || true)
  if [ -n "$code" ] && [ "$code" != "000" ]; then ok=1; echo "HEALTH_HTTP:$code"; break; fi
  sleep 1
done
if [ "$ok" = "1" ]; then echo "STEP_OK:health"; else echo "STEP_FAIL:health"; fi
"""


def _get_setting(db: Session, key: str) -> str:
    row = db.get(AppSetting, key)
    return (row.value or "") if row else ""


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key)
        db.add(row)
    row.value = value
    db.commit()


def _check_host(host: str) -> str:
    host = (host or "").strip()
    if not _HOST_RE.fullmatch(host):
        raise HTTPException(status_code=400, detail="DSW 主机名不合法")
    return host


def _ssh(host: str, command: str, stdin_text: str, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"root@{host}",
            command,
        ],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _push_values(db: Session) -> tuple[dict, str, str]:
    """默认角色所绑大脑要推送到展示端 .env 的值；返回 (values, problem, mode)。

    DSH 专家大脑：写 DSH 四行。
    其他（OpenAI 兼容，如百灵）：写 DEEPSEEK 三行（展示端的大脑调用读这组变量），
    同时把 DSH 三行清空——展示端只要 DSH_APP_ID/SECRET 非空就优先用 DSH，不清掉切不过去。
    """
    persona = (
        db.query(Persona).filter(Persona.is_default.is_(True)).order_by(Persona.id.asc()).first()
        or db.query(Persona).filter(Persona.enabled.is_(True)).order_by(Persona.id.asc()).first()
    )
    brain = db.get(Brain, persona.brain_id) if persona else None
    if brain is None:
        return {}, "还没有默认角色，跳过配置推送", ""

    def one(value: str) -> str:
        return (value or "").replace("\n", " ").strip()

    secret = decrypted_brain_key(brain)
    if (brain.preset or "") == "dsh":
        if not (brain.app_id or "").strip() or not secret:
            return {}, "DSH 大脑缺 App ID 或 App Secret，跳过配置推送", ""
        values = {
            "DSH_BASE_URL": one(brain.base_url),
            "DSH_APP_ID": one(brain.app_id),
            "DSH_APP_SECRET": one(secret),
            "DSH_AGENT_ID": one(brain.agent_id),
        }
        return values, "", "DSH 专家"
    if not one(brain.base_url):
        return {}, "大脑缺接口地址，跳过配置推送", ""
    values = {
        "DEEPSEEK_BASE_URL": one(brain.base_url),
        "DEEPSEEK_API_KEY": one(secret),
        "DEEPSEEK_MODEL": one(brain.model_name),
        "DSH_APP_ID": "",
        "DSH_APP_SECRET": "",
        "DSH_AGENT_ID": "",
    }
    return values, "", f"OpenAI 兼容 · {brain.name}"


@router.get("/settings")
def get_system_settings(db: Session = Depends(get_db)):
    return {"dsw_host": _get_setting(db, "dsw_host") or DEFAULT_DSW_HOST}


@router.put("/settings")
def put_system_settings(body: SystemSettingsIn, db: Session = Depends(get_db)):
    host = _check_host(body.dsw_host) if body.dsw_host.strip() else ""
    _set_setting(db, "dsw_host", host)
    return {"dsw_host": host or DEFAULT_DSW_HOST}


# ---------- 本机（localhost）展示端 ----------


def _rewrite_local_env(values: dict) -> None:
    path = LOCAL_DISPLAY_DIR / ".env"
    kept: list[str] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            if match and match.group(1) in values:
                continue
            kept.append(line)
    for key, value in values.items():
        kept.append(f"{key}={value}")
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def _local_pid_on_8000() -> int | None:
    try:
        out = subprocess.run(["lsof", "-ti:8000"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return None


def _restart_local(values: dict, problem: str, mode: str = "") -> dict:
    steps: list[dict] = []
    if not LOCAL_DISPLAY_DIR.is_dir():
        return {"ok": False, "host": "localhost", "steps": [{"name": _STEP_NAMES["push"], "ok": False, "detail": f"找不到本机展示端目录 {LOCAL_DISPLAY_DIR}"}]}

    if values:
        try:
            _rewrite_local_env(values)
            steps.append({"name": _STEP_NAMES["push"], "ok": True, "detail": f"已写入本机展示端 .env（{mode}）" if mode else "已写入本机展示端 .env"})
        except OSError as exc:
            steps.append({"name": _STEP_NAMES["push"], "ok": False, "detail": f"写 .env 失败：{exc}"})
            return {"ok": False, "host": "localhost", "steps": steps}
    else:
        steps.append({"name": _STEP_NAMES["push"], "ok": False, "detail": problem or "无可推送的配置"})

    pid = _local_pid_on_8000()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(20):
            if _local_pid_on_8000() is None:
                break
            time.sleep(0.5)
        if _local_pid_on_8000() is not None:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            time.sleep(1)
    stopped = _local_pid_on_8000() is None
    steps.append({"name": _STEP_NAMES["stop"], "ok": stopped, "detail": "" if stopped else "8000 端口仍被占用"})
    if not stopped:
        return {"ok": False, "host": "localhost", "steps": steps}

    if not LOCAL_PYTHON.is_file():
        steps.append({"name": _STEP_NAMES["start"], "ok": False, "detail": f"找不到解释器 {LOCAL_PYTHON}"})
        return {"ok": False, "host": "localhost", "steps": steps}
    try:
        log_file = open(LOCAL_LOG, "ab")
        proc = subprocess.Popen(
            [str(LOCAL_PYTHON), "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=str(LOCAL_DISPLAY_DIR),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        LOCAL_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
        steps.append({"name": _STEP_NAMES["start"], "ok": True, "detail": f"新进程 pid {proc.pid}"})
    except OSError as exc:
        steps.append({"name": _STEP_NAMES["start"], "ok": False, "detail": f"启动失败：{exc}"})
        return {"ok": False, "host": "localhost", "steps": steps}

    health_ok = False
    health_code = ""
    for _ in range(30):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/", timeout=2) as response:
                health_code = str(response.status)
            health_ok = True
            break
        except urllib.error.HTTPError as exc:
            health_code = str(exc.code)
            health_ok = True
            break
        except OSError:
            time.sleep(1)
    if health_ok:
        detail = f"页面返回 HTTP {health_code}"
    else:
        tail = ""
        try:
            tail = LOCAL_LOG.read_text(encoding="utf-8", errors="replace")[-300:]
        except OSError:
            pass
        detail = f"30 秒内没起来。日志尾部：{tail}" if tail else "30 秒内没起来"
    steps.append({"name": _STEP_NAMES["health"], "ok": health_ok, "detail": detail})
    return {"ok": all(step["ok"] for step in steps), "host": "localhost", "steps": steps}


# ---------- DSW 展示端 ----------


def _restart_dsw(host: str, values: dict, problem: str, mode: str = "") -> dict:
    steps: list[dict] = []
    push_text = ""
    if values:
        push_text = "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"

    if push_text:
        try:
            sent = _ssh(host, "cat > /tmp/dsh-push.env && chmod 600 /tmp/dsh-push.env", push_text, timeout=60)
            if sent.returncode != 0:
                detail = (sent.stderr or "").strip()[-300:] or "SSH 写入配置失败"
                return {"ok": False, "host": host, "steps": [{"name": "连接 DSW 并推送配置", "ok": False, "detail": detail}]}
        except subprocess.TimeoutExpired:
            return {"ok": False, "host": host, "steps": [{"name": "连接 DSW 并推送配置", "ok": False, "detail": "SSH 超时，检查 DSW 是否在线、主机名是否正确"}]}
        except OSError as exc:
            return {"ok": False, "host": host, "steps": [{"name": "连接 DSW 并推送配置", "ok": False, "detail": f"无法执行 ssh：{exc}"}]}

    try:
        result = _ssh(host, "bash -s", REMOTE_SCRIPT, timeout=180)
    except subprocess.TimeoutExpired:
        return {"ok": False, "host": host, "steps": steps + [{"name": "执行重启", "ok": False, "detail": "远端执行超时（180 秒）"}]}
    except OSError as exc:
        return {"ok": False, "host": host, "steps": steps + [{"name": "执行重启", "ok": False, "detail": f"无法执行 ssh：{exc}"}]}

    markers: dict[str, str] = {}
    health_http = ""
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("STEP_OK:"):
            markers[line[8:]] = "ok"
        elif line.startswith("STEP_FAIL:"):
            markers[line[10:]] = "fail"
        elif line.startswith("STEP_SKIP:"):
            markers[line[10:]] = "skip"
        elif line.startswith("HEALTH_HTTP:"):
            health_http = line[12:]

    if not markers:
        detail = ((result.stderr or "") or (result.stdout or "")).strip()[-300:] or "远端没有返回结果"
        return {"ok": False, "host": host, "steps": [{"name": "连接 DSW", "ok": False, "detail": detail}]}

    for key in ("push", "stop", "start", "health"):
        state = markers.get(key, "fail")
        detail = ""
        if key == "push":
            if problem:
                detail = problem
            elif state == "skip":
                detail = "未推送"
            elif mode:
                detail = f"已推送：{mode}"
        if key == "health" and health_http:
            detail = f"页面返回 HTTP {health_http}"
        steps.append({"name": _STEP_NAMES[key], "ok": state != "fail", "detail": detail})

    ok = all(step["ok"] for step in steps) and not problem
    return {"ok": ok, "host": host, "steps": steps}


@router.post("/restart-display")
def restart_display(body: RestartDisplayIn, db: Session = Depends(get_db)):
    values, problem, mode = _push_values(db)
    if (body.target or "dsw").strip() == "local":
        return _restart_local(values, problem, mode)
    host = _check_host(body.dsw_host) if body.dsw_host.strip() else (_get_setting(db, "dsw_host") or DEFAULT_DSW_HOST)
    if body.dsw_host.strip():
        _set_setting(db, "dsw_host", host)
    return _restart_dsw(host, values, problem, mode)
