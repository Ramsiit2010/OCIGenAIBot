# Quick Setup Script for OCIGenAIBot Development Environment
# Run this in PowerShell from the project root directory

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "  OCIGenAIBot Environment Setup  " -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# Check if running in correct directory
if (!(Test-Path "AskMeChatBot.py") -or !(Test-Path "RCOEGenAIAgents.py")) {
    Write-Host "ERROR: Please run this script from the OCIGenAIBot project root directory!" -ForegroundColor Red
    exit 1
}

# Step 1: Remove old venv if it exists and is broken
Write-Host "[1/6] Checking virtual environment..." -ForegroundColor Yellow
if (Test-Path ".venv") {
    $venvPyPath = (Get-Content ".venv\pyvenv.cfg" | Select-String "executable").ToString()
    if ($venvPyPath -notmatch [regex]::Escape($PWD.Path)) {
        Write-Host "  Old venv detected (pointing to wrong path). Removing..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force .venv
        Write-Host "  ✓ Old venv removed" -ForegroundColor Green
    } else {
        Write-Host "  ✓ Existing venv looks good" -ForegroundColor Green
    }
}

# Step 2: Create new venv
if (!(Test-Path ".venv")) {
    Write-Host "[2/6] Creating new virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: Failed to create virtual environment!" -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✓ Virtual environment created" -ForegroundColor Green
} else {
    Write-Host "[2/6] Virtual environment already exists" -ForegroundColor Green
}

# Step 3: Activate venv
Write-Host "[3/6] Activating virtual environment..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Failed to activate virtual environment!" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ Virtual environment activated" -ForegroundColor Green

# Step 4: Upgrade pip
Write-Host "[4/6] Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip --quiet
Write-Host "  ✓ Pip upgraded" -ForegroundColor Green

# Step 5: Install dependencies
Write-Host "[5/6] Installing dependencies from requirements.txt..." -ForegroundColor Yellow
python -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Failed to install dependencies!" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ Dependencies installed" -ForegroundColor Green

# Step 6: Environment configuration check
Write-Host "[6/6] Checking environment configuration..." -ForegroundColor Yellow
$missingFiles = @()

if (!(Test-Path ".env")) {
    $missingFiles += ".env (copy from .env.example)"
}
if (!(Test-Path "oci_api_key.pem")) {
    $missingFiles += "oci_api_key.pem (download from OCI Console)"
}

if ($missingFiles.Count -gt 0) {
    Write-Host "  ⚠ Missing files:" -ForegroundColor Yellow
    foreach ($file in $missingFiles) {
        Write-Host "    - $file" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ✓ All configuration files present" -ForegroundColor Green
}

# Final summary
Write-Host ""
Write-Host "==================================" -ForegroundColor Cyan
Write-Host "  Setup Complete!                 " -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Python Version: " -NoNewline
python --version
Write-Host "OCI SDK Version: " -NoNewline
python -m pip show oci | Select-String "Version"
Write-Host ""

if ($missingFiles.Count -gt 0) {
    Write-Host "⚠ Next Steps:" -ForegroundColor Yellow
    Write-Host "  1. Copy .env.example to .env and configure your credentials" -ForegroundColor Yellow
    Write-Host "  2. Place your oci_api_key.pem file in the project root" -ForegroundColor Yellow
    Write-Host "  3. Update config.properties with backend service credentials" -ForegroundColor Yellow
    Write-Host "  4. Run: python AskMeChatBot.py  OR  python RCOEGenAIAgents.py" -ForegroundColor Yellow
} else {
    Write-Host "✓ Ready to run!" -ForegroundColor Green
    Write-Host "  • AskMeChatBot (Hybrid):  python AskMeChatBot.py" -ForegroundColor Cyan
    Write-Host "  • RCOEGenAIAgents (MCP):  python RCOEGenAIAgents.py" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "For deployment guides, see: DEPLOYMENT_SETUP.md" -ForegroundColor Cyan
