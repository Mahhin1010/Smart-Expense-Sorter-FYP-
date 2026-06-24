# Smart Transaction Sorter & Analytics System - Startup Orchestrator
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Starting Smart Transaction Sorter & Analytics System    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Start Metabase Node
Write-Host "[+] Locating Java 21 for Metabase..." -ForegroundColor Yellow
$javaPath = "C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot\bin\java.exe"
if (Test-Path $javaPath) {
    Write-Host "    Found JDK 21 at: $javaPath" -ForegroundColor Green
    $javaCmd = $javaPath
} else {
    Write-Host "    JDK 21 not found at target Adoptium path. Falling back to default 'java'..." -ForegroundColor Yellow
    $javaCmd = "java"
}

Write-Host "[+] Launching Metabase BI server (Port 3000)..." -ForegroundColor Yellow
if (Test-Path "metabase.jar") {
    Start-Process -FilePath $javaCmd -ArgumentList "-jar metabase.jar" -NoNewWindow
    Write-Host "    Metabase starting in background..." -ForegroundColor Green
} else {
    Write-Host "    [!] metabase.jar not found in the root directory. Skipping Metabase." -ForegroundColor Red
}

# 2. Setup Python environment and Database migrations
Write-Host "[+] Running database migrations..." -ForegroundColor Yellow
if (Test-Path "venv\Scripts\python.exe") {
    $pythonCmd = "venv\Scripts\python.exe"
} elseif (Test-Path ".venv\Scripts\python.exe") {
    $pythonCmd = ".venv\Scripts\python.exe"
} else {
    $pythonCmd = "python"
}

& $pythonCmd manage.py migrate

# 3. Launch default browser
Write-Host "[+] Launching system dashboard in browser..." -ForegroundColor Yellow
Start-Sleep -Seconds 3
Start-Process "http://127.0.0.1:8000"

# 4. Start Django Development Server
Write-Host "[+] Launching Django Development Server (Port 8000)..." -ForegroundColor Yellow
& $pythonCmd manage.py runserver
