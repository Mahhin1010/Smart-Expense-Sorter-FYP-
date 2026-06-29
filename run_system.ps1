# Smart Transaction Sorter & Analytics System - Startup Orchestrator
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Starting Smart Transaction Sorter & Analytics System    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Start Metabase Node
Write-Host "[+] Locating Java for Metabase..." -ForegroundColor Yellow
$javaCmd = "java"
if ($env:JAVA_HOME) {
    $javaFromHome = Join-Path $env:JAVA_HOME "bin\java.exe"
    if (Test-Path $javaFromHome) {
        $javaCmd = $javaFromHome
        Write-Host "    Using JAVA_HOME: $javaCmd" -ForegroundColor Green
    }
}

Write-Host "[+] Launching Metabase BI server (Port 3000)..." -ForegroundColor Yellow
$metabaseJar = if ($env:METABASE_JAR_PATH) { $env:METABASE_JAR_PATH } else { "metabase.jar" }
if (Test-Path $metabaseJar) {
    Start-Process -FilePath $javaCmd -ArgumentList "-jar `"$metabaseJar`"" -NoNewWindow
    Write-Host "    Metabase starting in background..." -ForegroundColor Green
} else {
    Write-Host "    [!] Metabase jar not found. Set METABASE_JAR_PATH or place metabase.jar in the project root." -ForegroundColor Yellow
    Write-Host "        The jar and local Metabase database are intentionally not committed to Git." -ForegroundColor Yellow
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
