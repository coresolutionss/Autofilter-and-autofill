param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8504
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$intakePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $intakePython)) {
    throw 'Project Python environment is missing. Create .venv and install requirements.txt first.'
}
Write-Host "Starting AMB Document Intake at http://127.0.0.1:$Port"
Write-Host 'For cloud extraction, run this launcher in a normal PowerShell window with internet access.'
& $intakePython -m streamlit run app.py --server.address 127.0.0.1 --server.port $Port --server.headless true
