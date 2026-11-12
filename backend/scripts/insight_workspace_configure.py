"""经标准 Git 发布后配置妙搭接入；输入只从 stdin 读取，输出不包含凭据。"""
import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values, set_key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    payload = json.load(sys.stdin)
    secret = payload["key"]
    scope, owner, user_id = payload["scope"], payload["owner"], payload["userId"]
    if not isinstance(secret, str) or len(secret) < 40 or not isinstance(user_id, int) or user_id <= 0:
        raise SystemExit("接入配置格式不正确")
    if not isinstance(scope, str) or not isinstance(owner, str) or ":" not in scope or ":" in owner:
        raise SystemExit("接入身份格式不正确")
    env_file = Path(__file__).resolve().parents[1] / ".env"
    values = dotenv_values(env_file)
    existing_key = values.get("INSIGHT_WORKSPACE_KEY")
    if existing_key and existing_key != secret:
        raise SystemExit("已存在不同接入密钥；拒绝隐式轮换")
    bindings = json.loads(values.get("INSIGHT_WORKSPACE_BINDINGS_JSON") or "{}")
    if bindings.get(scope, {}).get(owner) not in {None, user_id}:
        raise SystemExit("账号已绑定不同身份；拒绝覆盖")
    bindings.setdefault(scope, {})[owner] = user_id
    readers = set(json.loads(values.get("INSIGHT_WORKSPACE_BOT_READERS_JSON") or "[]"))
    if payload.get("botReports") is True:
        readers.add(f"{scope}:{owner}")
    if args.apply:
        for key, value in {"INSIGHT_WORKSPACE_KEY": secret,
            "INSIGHT_WORKSPACE_BINDINGS_JSON": json.dumps(bindings),
            "INSIGHT_WORKSPACE_BOT_READERS_JSON": json.dumps(sorted(readers))}.items():
            set_key(env_file, key, value)
        if os.name != "nt":
            env_file.chmod(0o600)
    sys.stdout.write(json.dumps({"applied": args.apply, "scope": scope, "userId": user_id,
        "botReports": f"{scope}:{owner}" in readers}) + "\n")


if __name__ == "__main__":
    main()
