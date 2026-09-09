param(
  [Alias("Host")]
  [string]$BindHost = "0.0.0.0",
  [int]$Port = 8000,
  [string]$EnvironmentName = "vhl"
)

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
  Write-Error "Conda was not found on PATH. Install or initialize Conda before starting the backend."
  exit 1
}

Push-Location $repositoryRoot
try {
  & conda run -n $EnvironmentName uvicorn backend.main:app --host $BindHost --port $Port
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}
finally {
  Pop-Location
}
