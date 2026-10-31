# Firecrawl（vendor/firecrawl）をローカルで起動/停止。要 Docker Desktop。APIキー不要・無料で無制限。
#   .\scripts\firecrawl.ps1 up | down | logs | status
param([string]$cmd = "up")
$root = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $root
if (-not (Test-Path vendor\firecrawl\docker-compose.yaml)) { git submodule update --init --depth 1 vendor/firecrawl }
$envFile = if (Test-Path .env) { @("--env-file", ".env") } else { @() }
$dc = @("compose") + $envFile + @("-f", "vendor/firecrawl/docker-compose.yaml", "-f", "docker/firecrawl.override.yaml")
switch ($cmd) {
  "up" {
    docker @dc pull --ignore-pull-failures
    docker @dc up -d --no-build
    if ($LASTEXITCODE -ne 0) { docker @dc up -d --build }
    Write-Host "Firecrawl: http://localhost:3002  （.env に FIRECRAWL_API_URL=http://localhost:3002）"
  }
  "down" { docker @dc down }
  "logs" { docker @dc logs -f api }
  default { docker @dc ps }
}
