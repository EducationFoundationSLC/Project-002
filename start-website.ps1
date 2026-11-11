# Starts the Project 002 property website and opens it in your browser.
#
#   Double-click start-website.cmd, or run in PowerShell:  .\start-website.ps1
#   Stop the website by pressing Ctrl+C in this window (or just close it).
#
# What it does:
#   1. Stops a copy of the website that's already running on the same port.
#   2. Swaps in a newly built database if build_db.py left one waiting (property.db.tmp).
#   3. Finds your Anthropic API key for "Ask AI" (or asks for it once).
#   4. Starts the server and opens http://localhost:8000.

param([int]$Port = 8000)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$url = "http://localhost:$Port"
$db = "website\data\property.db"

# --- Python ---------------------------------------------------------------
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) {
    Write-Host "Python isn't installed (or isn't on the PATH). Install it from https://www.python.org/" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# --- 1. Stop a copy of the website that's already running --------------------
# Find it two ways: by its command (python ... website\server.py) and by the port it uses.
$running = @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -match 'website[\\/]server\.py' } |
    ForEach-Object { $_.ProcessId })
foreach ($conn in @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) {
    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    if (-not $proc -or $conn.OwningProcess -eq 0) { continue }
    if ($proc.ProcessName -like "python*") {
        $running += $proc.Id
    } else {
        Write-Host "Port $Port is being used by another program ($($proc.ProcessName)). Try: .\start-website.ps1 -Port 8001" -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }
}
foreach ($id in ($running | Sort-Object -Unique)) {
    Write-Host "Stopping the copy of the website that's already running (process $id)..."
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
}
if ($running.Count) { Start-Sleep -Seconds 1 }

# --- 2. Use a newly built database if one is waiting -------------------------
$tmp = "$db.tmp"
if (Test-Path $tmp) {
    $age = (Get-Date) - (Get-Item $tmp).LastWriteTime
    $newer = -not (Test-Path $db) -or (Get-Item $tmp).LastWriteTime -gt (Get-Item $db).LastWriteTime
    if ($newer -and $age.TotalSeconds -gt 60) {  # not still being written by build_db.py
        Write-Host "Using the newly built database..."
        try {
            Move-Item -Force $tmp $db
        } catch {
            Write-Host "Couldn't replace the database (another program has it open), so the old one will be used." -ForegroundColor Yellow
        }
    }
}
if (-not (Test-Path $db)) {
    Write-Host "The database hasn't been built yet. Run:  python website\build_db.py" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# --- 3. Anthropic API key for Ask AI -----------------------------------------
if (-not $env:ANTHROPIC_API_KEY) {
    # Saved with setx (or below) but this window was opened before it was saved.
    $env:ANTHROPIC_API_KEY = [Environment]::GetEnvironmentVariable("ANTHROPIC_API_KEY", "User")
}
if (-not $env:ANTHROPIC_API_KEY) {
    Write-Host ""
    Write-Host "No Anthropic API key found, so Ask AI will be turned off." -ForegroundColor Yellow
    $secure = Read-Host "Paste your API key to turn it on (or just press Enter to skip)" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim()
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    if ($key) {
        $env:ANTHROPIC_API_KEY = $key
        $save = Read-Host "Save the key on this computer so you aren't asked again? (y/N)"
        if ($save -match "^[Yy]") {
            [Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", $key, "User")
            Write-Host "Saved in your Windows account settings (Environment Variables)."
        }
    }
}
if ($env:ANTHROPIC_API_KEY) { Write-Host "Ask AI: on" -ForegroundColor Green }
else { Write-Host "Ask AI: off (the rest of the website works normally)" }

# --- 4. Start the server and open the browser -------------------------------
$env:PORT = "$Port"
Write-Host ""
Write-Host "Starting the website at $url  (press Ctrl+C to stop)"
$server = Start-Process -FilePath $python.Source -ArgumentList "website\server.py" -NoNewWindow -PassThru

# Wait until the server answers (the first start can take a few seconds), then open the browser.
$ready = $false
for ($i = 0; $i -lt 60 -and -not $ready -and -not $server.HasExited; $i++) {
    try {
        Invoke-WebRequest -Uri "$url/api/filters" -UseBasicParsing -TimeoutSec 2 | Out-Null
        $ready = $true
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
if ($ready) {
    Start-Process $url
} elseif ($server.HasExited) {
    Write-Host "The website stopped with an error (see the message above)." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
} else {
    Write-Host "The website is taking a long time to start. Try opening $url yourself." -ForegroundColor Yellow
}

try {
    Wait-Process -Id $server.Id
} finally {
    # Runs when you press Ctrl+C: make sure the server stops too.
    if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
}
