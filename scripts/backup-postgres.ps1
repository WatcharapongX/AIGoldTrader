# Automated PostgreSQL backup (Phase 5 UAT readiness).
# Usage: .\scripts\backup-postgres.ps1 [-RetentionDays 14] [-OutputDir .\backups]
# Requires: pg_dump on PATH or -PgDumpPath, and DATABASE_URL or POSTGRES_* env.
param(
    [int]$RetentionDays = 14,
    [string]$OutputDir = ".\backups",
    [string]$PgDumpPath = "pg_dump"
)

$ErrorActionPreference = "Stop"

if (-not $env:DATABASE_URL -and -not $env:POSTGRES_HOST) {
    throw "Set DATABASE_URL or POSTGRES_* before backing up."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $OutputDir "aigold-$stamp.dump"

if ($env:DATABASE_URL) {
    & $PgDumpPath --format=custom --no-owner --file=$target $env:DATABASE_URL
} else {
    $env:PGPASSWORD = $env:POSTGRES_PASSWORD
    & $PgDumpPath --format=custom --no-owner --host=$env:POSTGRES_HOST --port=$($env:POSTGRES_PORT ?? 5432) --username=$env:POSTGRES_USER --dbname=$env:POSTGRES_DB --file=$target
}
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }

$hash = (Get-FileHash -Algorithm SHA256 $target).Hash
"$hash  $(Split-Path $target -Leaf)" | Set-Content "$target.sha256"
Write-Host "Backup written: $target (sha256 $hash)"

$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem $OutputDir -Filter "aigold-*.dump*" | Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Force
Write-Host "Pruned backups older than $RetentionDays days."
