# Smart Transaction Sorter & Analytics System - Startup Orchestrator
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Starting Smart Transaction Sorter & Analytics System    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Start Metabase Node
Write-Host "[+] Locating Java for Metabase..." -ForegroundColor Yellow
$javaCmd = "java"
$preferredJava21 = "C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot\bin\java.exe"
if ($env:METABASE_JAVA_PATH -and (Test-Path $env:METABASE_JAVA_PATH)) {
    $javaCmd = $env:METABASE_JAVA_PATH
    Write-Host "    Using METABASE_JAVA_PATH: $javaCmd" -ForegroundColor Green
} elseif (Test-Path $preferredJava21) {
    $javaCmd = $preferredJava21
    Write-Host "    Using Java 21: $javaCmd" -ForegroundColor Green
} elseif ($env:JAVA_HOME) {
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

if (-not (Test-Path ".venv\pyvenv.cfg")) {
    Write-Host "    Local .venv not found. Creating it from requirements.txt..." -ForegroundColor Yellow
    py -3.14 -m venv .venv
    & ".venv\Scripts\python.exe" -m pip install --upgrade pip
    & ".venv\Scripts\python.exe" -m pip install -r requirements.txt
}

if (Test-Path ".venv\Scripts\python.exe") {
    $pythonCmd = ".venv\Scripts\python.exe"
} elseif (Test-Path "venv\Scripts\python.exe") {
    $pythonCmd = "venv\Scripts\python.exe"
} else {
    $pythonCmd = "py"
}

& $pythonCmd manage.py migrate

# 3. Launch default browser
Write-Host "[+] Launching system dashboard in browser..." -ForegroundColor Yellow
Start-Sleep -Seconds 3
Start-Process "http://127.0.0.1:8000"

# 4. Start Django Development Server
Write-Host "[+] Launching Django Development Server (Port 8000)..." -ForegroundColor Yellow
& $pythonCmd manage.py runserver
