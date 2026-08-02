param(
    [string]$Server = "192.168.14.44",
    [string]$User = "xinxi",
    [string]$RemotePath = "/home/xinxi/ai_platform",
    [string]$Branch = "main",
    [string]$DeployRemoteUrl = "http://192.168.14.111:9055/zhangjide/ai_platform.git",
    [string]$ExpectedCommit = "",
    [string]$SshKey = "$HOME/.ssh/ai_platform_deploy_ed25519",
    [string]$RemoteUvPath = "/home/xinxi/.local/bin/uv",
    [string]$RemoteNodeBin = "/home/xinxi/.nvm/nvm-0.40.2/versions/node/v22.18.0/bin",
    [switch]$BackendOnly,
    [switch]$SkipDependencies
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
chcp 65001 > $null

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "命令执行失败：$FilePath $($Arguments -join ' ')"
    }
}

if (-not (Test-Path -LiteralPath $SshKey)) {
    throw "SSH 密钥不存在：$SshKey"
}

$gitExecutable = (Get-Command git -CommandType Application -ErrorAction Stop).Source

$repositoryRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repositoryRoot
try {
    $gitBranch = (& $gitExecutable branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $gitBranch -ne $Branch) {
        throw "本地必须位于 $Branch 分支，当前为：$gitBranch"
    }

    if (-not $ExpectedCommit) {
        $ExpectedCommit = (& $gitExecutable rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0) {
            throw "无法读取本地提交。"
        }
    }

    Invoke-CheckedCommand -FilePath $gitExecutable -Arguments @("fetch", $DeployRemoteUrl, $Branch)
    & $gitExecutable merge-base --is-ancestor $ExpectedCommit "FETCH_HEAD"
    if ($LASTEXITCODE -ne 0) {
        throw "提交 $ExpectedCommit 尚未推送到发布仓库 $DeployRemoteUrl 的 $Branch 分支，请先提交并推送。"
    }
}
finally {
    Pop-Location
}

$installBackend = if ($SkipDependencies) { "false" } else { "true" }
$installFrontend = if ($SkipDependencies -or $BackendOnly) { "false" } else { "true" }
$buildFrontend = if ($BackendOnly) { "false" } else { "true" }
$restartFrontend = if ($BackendOnly) { "false" } else { "true" }
$remoteScript = @"
set -euo pipefail

cd '$RemotePath'
export PATH='${RemoteNodeBin}:/home/xinxi/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'

if [ ! -x '$RemoteUvPath' ]; then
  echo '服务器 uv 不存在或不可执行：$RemoteUvPath' >&2
  exit 20
fi

if $buildFrontend && [ ! -x '$RemoteNodeBin/corepack' ]; then
  echo '服务器 Node/corepack 不存在或不可执行：$RemoteNodeBin/corepack' >&2
  exit 20
fi

if [ "`$(git branch --show-current)" != '$Branch' ]; then
  echo '服务器仓库不在 $Branch 分支，已中止。' >&2
  exit 21
fi

if [ -n "`$(git status --porcelain --untracked-files=no)" ]; then
  echo '服务器仓库存在受 Git 管理的未提交改动，已中止：' >&2
  git status --short --untracked-files=no >&2
  exit 22
fi

old_commit="`$(git rev-parse HEAD)"
git fetch '$DeployRemoteUrl' '$Branch'
git merge-base --is-ancestor '$ExpectedCommit' FETCH_HEAD
git merge --ff-only FETCH_HEAD

new_commit="`$(git rev-parse HEAD)"
if [ "`$new_commit" != '$ExpectedCommit' ]; then
  echo "服务器 HEAD (`$new_commit) 与期望提交 ($ExpectedCommit) 不一致，已中止重启。" >&2
  exit 23
fi

if $installBackend; then
  cd '$RemotePath/backend'
  '$RemoteUvPath' sync --frozen
fi

if $installFrontend; then
  cd '$RemotePath/frontend'
  '$RemoteNodeBin/corepack' pnpm install --frozen-lockfile
fi

if $buildFrontend; then
  cd '$RemotePath/frontend'
  '$RemoteNodeBin/corepack' pnpm build
fi

systemctl --user restart ai-platform-backend.service
if $restartFrontend; then
  systemctl --user restart ai-platform-frontend.service
fi

for attempt in `$(seq 1 30); do
  if curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8000/ >/dev/null; then
    break
  fi
  if [ "`$attempt" -eq 30 ]; then
    systemctl --user status ai-platform-backend.service --no-pager >&2 || true
    echo '后端健康检查失败。' >&2
    exit 24
  fi
  sleep 2
done

if $restartFrontend; then
  for attempt in `$(seq 1 30); do
    if curl --fail --silent --show-error --max-time 3 http://127.0.0.1:5173/ >/dev/null; then
      break
    fi
    if [ "`$attempt" -eq 30 ]; then
      systemctl --user status ai-platform-frontend.service --no-pager >&2 || true
      echo '前端健康检查失败。' >&2
      exit 25
    fi
    sleep 2
  done
fi

echo "部署完成：`$old_commit -> `$new_commit"
systemctl --user is-active ai-platform-backend.service
if $restartFrontend; then
  systemctl --user is-active ai-platform-frontend.service
fi
"@

$encodedScript = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($remoteScript))
$sshArguments = @(
    "-i", $SshKey,
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=15",
    "$User@$Server",
    "echo $encodedScript | base64 -d | bash"
)
Invoke-CheckedCommand -FilePath "ssh" -Arguments $sshArguments
