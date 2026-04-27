param(
    [ValidateSet(
        "help",
        "test",
        "lint",
        "typecheck",
        "fix",
        "migrate",
        "release-check",
        "run",
        "compose-up",
        "compose-up-pg",
        "compose-down",
        "compose-config"
    )]
    [string]$Task = "help"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Run-RepoCommand([string]$Command) {
    Push-Location $repoRoot
    try {
        Invoke-Expression $Command
    }
    finally {
        Pop-Location
    }
}

switch ($Task) {
    "help" {
        Write-Host "Available tasks:"
        Write-Host "  test           Run pytest backend/tests -q"
        Write-Host "  lint           Run Ruff lint and format checks"
        Write-Host "  typecheck      Run mypy on config, schemas, and services"
        Write-Host "  fix            Auto-fix Ruff issues and format code"
        Write-Host "  migrate        Run alembic upgrade head"
        Write-Host "  release-check  Run lint, typecheck, migrations, and tests"
        Write-Host "  run            Start uvicorn in reload mode"
        Write-Host "  compose-up     Build image, run migrations, and start services"
        Write-Host "  compose-up-pg  Start PostgreSQL profile plus app container"
        Write-Host "  compose-down   Stop compose services"
        Write-Host "  compose-config Validate docker compose configuration"
        exit 0
    }
    "test" {
        Assert-Command "pytest"
        Run-RepoCommand "pytest backend/tests -q"
    }
    "lint" {
        Assert-Command "ruff"
        Run-RepoCommand "ruff check backend alembic"
        Run-RepoCommand "ruff format --check backend alembic"
    }
    "fix" {
        Assert-Command "ruff"
        Run-RepoCommand "ruff check backend alembic --fix"
        Run-RepoCommand "ruff format backend alembic"
    }
    "typecheck" {
        Assert-Command "mypy"
        Run-RepoCommand "mypy"
    }
    "migrate" {
        Assert-Command "alembic"
        Run-RepoCommand "alembic upgrade head"
    }
    "release-check" {
        Assert-Command "ruff"
        Assert-Command "mypy"
        Assert-Command "alembic"
        Assert-Command "pytest"
        Run-RepoCommand "ruff check backend alembic frontend"
        Run-RepoCommand "ruff format --check backend alembic frontend"
        Run-RepoCommand "mypy"
        Run-RepoCommand "alembic upgrade head"
        Run-RepoCommand "pytest backend/tests -q"
    }
    "run" {
        Assert-Command "uvicorn"
        Run-RepoCommand "uvicorn app.main:app --reload --app-dir backend"
    }
    "compose-up" {
        Assert-Command "docker"
        Run-RepoCommand "docker compose up --build"
    }
    "compose-up-pg" {
        Assert-Command "docker"
        Run-RepoCommand "docker compose --profile postgres up --build"
    }
    "compose-down" {
        Assert-Command "docker"
        Run-RepoCommand "docker compose down"
    }
    "compose-config" {
        Assert-Command "docker"
        Run-RepoCommand "docker compose config"
    }
}
