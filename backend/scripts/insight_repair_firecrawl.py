"""修复既有 Firecrawl worker 守护；只允许由统一发布流程显式调用。"""

import argparse
import json
import os
import subprocess
import sys
import time
from hashlib import sha256
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
    source = command("docker", "exec", "firecrawl-api-1", "cat", "/app/dist/src/services/queue-worker.js")
    needle = "        const job = await worker.getNextJob(token);"
    if source.count(needle) != 1 or "runningJobs.delete(job.id)" not in source:
        raise RuntimeError("Firecrawl worker 版本与已核查结构不一致，停止修复")
    # 该旧镜像忽略 NUM_WORKERS_PER_QUEUE，循环会无限派发，需在真实取任务处限制。
    patched = source.replace(needle, """        if (runningJobs.size >= Number(process.env.MAX_CONCURRENT_JOBS || 3)) {
            await sleep(250);
            continue;
        }
""" + needle)
    subprocess.run(["docker", "exec", "-i", "firecrawl-api-1", "node", "--check"],
                   input=patched, text=True, capture_output=True, check=True)
    runtime = directory / ".ai-platform-runtime"
    runtime.mkdir(exist_ok=True, mode=0o700)
    original = runtime / f"queue-worker-original-{sha256(source.encode()).hexdigest()[:16]}.js"
    if not original.exists():
        original.write_text(source)
    worker_file = runtime / f"queue-worker-{sha256(patched.encode()).hexdigest()[:16]}.js"
    worker_file.write_text(patched)
    script = Path(__file__).with_name("firecrawl_expired_jobs.cjs").read_text()
    raw = command("docker", "exec", "firecrawl-api-1", "node", "-e", script)
    snapshot = json.loads(raw.splitlines()[-1])
    if snapshot["jobs"]:
        archive = Path(__file__).resolve().parents[1] / "logs" / f"firecrawl-expired-{datetime.now():%Y%m%d%H%M%S}.json"
        archive.parent.mkdir(exist_ok=True)
        with os.fdopen(os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            json.dump(snapshot, stream, ensure_ascii=False)
        completed = subprocess.run(["docker", "exec", "-i", "firecrawl-api-1", "node", "-e", script, "--", "--apply"],
                                   input=json.dumps(snapshot), capture_output=True, text=True, check=True)
        cleanup = json.loads(completed.stdout.splitlines()[-1])
        sys.stdout.write(json.dumps({"archive": str(archive), "expired": len(snapshot["jobs"]), **cleanup}) + "\n")
    # JSON 是合法的 Compose YAML；不改原安装文件，不重新构建或拉取未知镜像。
    content = json.dumps({"services": {
        "api": {"restart": "unless-stopped"},
        "worker": {"image": container["Config"]["Image"], "restart": "unless-stopped",
                   "environment": {"MAX_CONCURRENT_JOBS": "3"},
                   "volumes": [f"{worker_file}:/app/dist/src/services/queue-worker.js:ro"]},
        "playwright-service": {"restart": "unless-stopped"},
    }}, indent=2) + "\n"
    if override.exists() and override.read_text() != content:
        backup = override.with_suffix(f".backup-{datetime.now():%Y%m%d%H%M%S}.json")
        backup.write_bytes(override.read_bytes())
    override.write_text(content)
    command("docker", "compose", "-f", str(base), "-f", str(override), "up", "-d", "--no-build", "--no-deps", "playwright-service", "worker")
    command("docker", "update", "--restart=unless-stopped", "firecrawl-api-1")
    restarts = json.loads(command("docker", "inspect", "firecrawl-worker-1"))[0]["RestartCount"]
    for _ in range(6):
        time.sleep(5)
        state = json.loads(command("docker", "inspect", "firecrawl-worker-1"))[0]
        if not state["State"]["Running"] or state["RestartCount"] != restarts:
            raise RuntimeError("Firecrawl worker 启动不稳定，请检查容器日志，未清空任何队列")
    sys.stdout.write("Firecrawl worker 连续运行30秒；仍须通过真实正文批次验收。\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    run(parser.parse_args().apply)
