param(
    [switch]$Smoke,
    [switch]$SkipInstall,
    [switch]$SkipBackend,
    [switch]$SkipE2E,
    [switch]$SkipBrowserInstall,
    [switch]$Ui,
    [int]$E2EPort = 0,
    [int]$E2EWorkers = 1
)

$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    & $Command
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "Step failed with exit code ${LASTEXITCODE}: $Name"
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$e2eDir = Join-Path $repoRoot "frontend\e2e"
$npmCache = Join-Path $repoRoot ".tmp\npm-cache"

Set-Location $repoRoot

function Test-PortAvailable {
    param([int]$Port)

    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), $Port)
    try {
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        $listener.Stop()
    }
}

function Get-AvailablePort {
    for ($attempt = 0; $attempt -lt 50; $attempt++) {
        $candidate = Get-Random -Minimum 18000 -Maximum 29999
        if (Test-PortAvailable -Port $candidate) {
            return $candidate
        }
    }
    throw "Unable to find an available E2E port."
}

function Wait-HttpReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$TimeoutSec = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    } while ((Get-Date) -lt $deadline)

    throw "Timed out waiting for E2E server: $Url"
}

if (-not $SkipInstall) {
    Invoke-Step "Install Python runtime and test dependencies" {
        python -X utf8 -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt
    }
}

if (-not $SkipBackend) {
    Invoke-Step "Run backend unit and API tests" {
        python -X utf8 -m pytest -c backend\pytest.ini backend\tests -q
    }

    Invoke-Step "Run Python lint" {
        ruff check .
    }
}

if (-not $SkipE2E) {
    if (-not (Test-Path $e2eDir)) {
        throw "E2E directory not found: $e2eDir"
    }

    if (-not $env:npm_config_cache) {
        New-Item -ItemType Directory -Force -Path $npmCache | Out-Null
        $env:npm_config_cache = $npmCache
    }

    if ($E2EPort -le 0) {
        $E2EPort = Get-AvailablePort
    } elseif (-not (Test-PortAvailable -Port $E2EPort)) {
        throw "Requested E2E port is already in use: $E2EPort"
    }

    $env:YOU2MUSIC_E2E_PORT = [string]$E2EPort
    $env:YOU2MUSIC_E2E_REUSE_SERVER = "0"
    $env:YOU2MUSIC_E2E_WORKERS = [string]$E2EWorkers
    $env:YOU2MUSIC_E2E_EXTERNAL_SERVER = "1"
    $env:AI_MUSIC_DATA_DIR = Join-Path $repoRoot (".tmp\you2music_e2e_{0}" -f ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()))
    $env:AI_MUSIC_JWT_SECRET = "e2e-test-secret"
    $env:AI_MUSIC_ADMIN_USERNAME = "admin"
    $env:AI_MUSIC_ADMIN_PASSWORD = "adminpw"
    $env:AI_MUSIC_DEFAULT_DAILY_QUOTA = "999"
    $env:AI_MUSIC_HOST = "127.0.0.1"
    $env:AI_MUSIC_PORT = [string]$E2EPort
    $env:ACESTEP_API_KEY = "fake-key"
    $env:ACESTEP_BASE_URL = "http://localhost:0"
    $env:AI_MUSIC_TEST_MODE = "1"
    Write-Host "Using isolated E2E server on http://127.0.0.1:$E2EPort with $E2EWorkers worker(s)" -ForegroundColor Cyan

    $serverProcess = $null
    Push-Location $e2eDir
    try {
        if (-not $SkipInstall) {
            Invoke-Step "Install E2E npm dependencies" {
                npm install
            }
        }

        if (-not $SkipBrowserInstall) {
            Invoke-Step "Install Playwright browsers" {
                npx playwright install chromium webkit
            }
        }

        Invoke-Step "Start isolated E2E backend" {
            $script:serverProcess = Start-Process -FilePath "python" -ArgumentList "backend/main.py" -WorkingDirectory $repoRoot -PassThru -WindowStyle Hidden
            Wait-HttpReady -Url "http://127.0.0.1:$E2EPort/" -TimeoutSec 30
        }

        if ($Ui) {
            Invoke-Step "Run Playwright UI mode" {
                npm run test:ui
            }
        } elseif ($Smoke) {
            Invoke-Step "Run Playwright smoke tests" {
                npx playwright test --grep "@smoke" --reporter=line
            }
        } else {
            Invoke-Step "Run Playwright full E2E suite" {
                npx playwright test --reporter=line
            }
        }
    } finally {
        if ($serverProcess -and -not $serverProcess.HasExited) {
            Stop-Process -Id $serverProcess.Id -Force
            $serverProcess.WaitForExit()
        }
        Pop-Location
    }
}

Write-Host ""
Write-Host "All requested checks passed." -ForegroundColor Green
