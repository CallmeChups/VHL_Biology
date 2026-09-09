param(
  [Alias("Host")]
  [string]$BindHost = "0.0.0.0",
  [int]$Port = 8501,
  [string]$BackendUrl = "http://127.0.0.1:8000",
  [string]$EnvironmentName = "vhl"
)

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
  Write-Error "Conda was not found on PATH. Install or initialize Conda before starting the dashboard."
  exit 1
}

$env:BACKEND_URL = $BackendUrl

Push-Location $repositoryRoot
try {
  & conda run -n $EnvironmentName streamlit run app.py `
    --server.address $BindHost `
    --server.port $Port `
    --server.headless true
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}
finally {
  Pop-Location
}
