# Copies the project to the server and (re)starts it with Docker Compose.
#
#   .\scripts\deploy.ps1 -Server 95.217.1.2                 # Hetzner (root)
#   .\scripts\deploy.ps1 -Server 158.180.1.2 -User ubuntu   # Oracle Cloud (Ubuntu image)
#
# Never touches data/ or .env on the server, so users and saved samples are kept.
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [string]$User = "root",
    [string]$Dir = "/opt/rakenne"
)
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$archive = Join-Path $env:TEMP "rakenne-deploy.tgz"
$target = "$User@$Server"

Write-Host "Pakataan projekti..."
tar -czf $archive -C $root `
    --exclude=./.venv --exclude=./.git --exclude=./data --exclude=./.env `
    --exclude=./samples --exclude=./reference --exclude=./spike --exclude=./.pytest_cache --exclude=__pycache__ .
if ($LASTEXITCODE -ne 0) { throw "Pakkaus epäonnistui" }

Write-Host "Kopioidaan palvelimelle $Server..."
scp $archive "${target}:/tmp/rakenne-deploy.tgz"
if ($LASTEXITCODE -ne 0) { throw "Kopiointi epäonnistui" }
Remove-Item $archive

Write-Host "Puretaan ja käynnistetään (ensimmäinen kerta kestää 5-15 min)..."
$remote = @"
set -e
mkdir -p $Dir/data
tar -xzf /tmp/rakenne-deploy.tgz -C $Dir
rm /tmp/rakenne-deploy.tgz
cd $Dir
chown 1000:1000 data
if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo 'Tiedosto .env puuttui. Aseta DOMAIN komennolla:  sudo nano $Dir/.env'
  echo 'ja aja tämä skripti uudelleen.'
  exit 1
fi
docker compose up -d --build
docker image prune -f > /dev/null
docker compose ps
"@
# Send the script base64-encoded: keeps Unix line endings and UTF-8 intact, and lets a
# non-root user (Oracle's "ubuntu") run it with sudo.
$sudo = if ($User -eq "root") { "" } else { "sudo " }
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($remote -replace "`r", "")))
ssh $target "echo $b64 | base64 -d | ${sudo}bash"
if ($LASTEXITCODE -ne 0) { throw "Käynnistys palvelimella epäonnistui" }

$domain = (ssh $target "grep '^DOMAIN=' $Dir/.env | cut -d= -f2").Trim()
Write-Host ""
Write-Host "Valmis: https://$domain"
