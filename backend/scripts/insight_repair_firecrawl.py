"""修复既有 Firecrawl worker 守护；只允许由统一发布流程显式调用。"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def run(apply):
    container = json.loads(command("docker", "inspect", "firecrawl-worker-1"))[0]
    labels = container["Config"]["Labels"]
    directory = Path(labels["com.docker.compose.project.working_dir"]).resolve()
    if str(directory) != "/home/xinxi/ai/app/firecrawl":
        raise RuntimeError("Firecrawl 工作目录不符，停止操作")
    if labels.get("com.docker.compose.service") != "worker":
        raise RuntimeError("目标不是 Firecrawl worker")
    base = directory / "docker-compose.yaml"
    override = directory / "compose.ai-platform-recovery.json"
    sys.stdout.write(json.dumps({"directory": str(directory), "worker_status": container["State"]["Status"],
                                 "restart_policy": container["HostConfig"]["RestartPolicy"]}) + "\n")
    if not apply:
        return
    # JSON 是合法的 Compose YAML；不改原安装文件，不重新构建或拉取未知镜像。
    content = json.dumps({"services": {
        "api": {"restart": "unless-stopped"},
        "worker": {"image": container["Config"]["Image"], "restart": "unless-stopped"},
    }}, indent=2) + "\n"
    if override.exists() and override.read_text() != content:
        backup = override.with_suffix(f".backup-{datetime.now():%Y%m%d%H%M%S}.json")
        backup.write_bytes(override.read_bytes())
    override.write_text(content)
    command("docker", "compose", "-f", str(base), "-f", str(override), "up", "-d", "--no-build", "--no-deps", "worker")
    command("docker", "update", "--restart=unless-stopped", "firecrawl-api-1")
    for _ in range(6):
        time.sleep(5)
        state = json.loads(command("docker", "inspect", "firecrawl-worker-1"))[0]
        if not state["State"]["Running"] or state["RestartCount"]:
            raise RuntimeError("Firecrawl worker 启动不稳定，请检查容器日志，未清空任何队列")
    sys.stdout.write("Firecrawl worker 连续运行30秒；仍须通过真实正文批次验收。\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    run(parser.parse_args().apply)
