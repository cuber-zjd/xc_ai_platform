param(
    [switch]$Json,
    [switch]$Strict,
    [switch]$SkipNetwork,
    [switch]$SkipPlaywright,
    [switch]$ProbePaid,
    [double]$Timeout = 8
)

[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
chcp 65001 > $null

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $backendDir

$argsList = @("scripts/insight_env_check.py", "--timeout", "$Timeout")

if ($Json) {
    $argsList += "--json"
}
if ($Strict) {
    $argsList += "--strict"
}
if ($SkipNetwork) {
    $argsList += "--skip-network"
}
if ($SkipPlaywright) {
    $argsList += "--skip-playwright"
}
if ($ProbePaid) {
    $argsList += "--probe-paid"
}

uv run python @argsList
exit $LASTEXITCODE
