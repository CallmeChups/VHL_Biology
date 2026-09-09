[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [ValidatePattern("^[A-Za-z0-9][A-Za-z0-9._-]*$")]
  [string]$Version,

  [Parameter(Mandatory = $true)]
  [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceManifestPath = Join-Path $repositoryRoot "RELEASE_MANIFEST.json"

if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
  $releaseRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
}
else {
  $releaseRoot = [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path $OutputDirectory))
}

function Convert-ToManifestPath {
  param([string]$Path)
  return ($Path -replace "\\", "/")
}

function Assert-AllowedReleasePath {
  param([string]$RelativePath)

  $normalized = Convert-ToManifestPath $RelativePath
  if ($normalized -match "(?i)(^|/)(temp\.txt|temp\.xlsx|\.env(?!\.example$)($|\.)|.*\.log$|frontend_logs|__pycache__|\.pytest_cache|\.venv($|/)|logs($|/))") {
    throw "Refusing forbidden release path: $RelativePath"
  }
}

function Copy-ReleaseFile {
  param(
    [string]$SourceRelativePath,
    [string]$DestinationRelativePath,
    [switch]$Optional
  )

  Assert-AllowedReleasePath $SourceRelativePath
  Assert-AllowedReleasePath $DestinationRelativePath
  $sourcePath = Join-Path $repositoryRoot $SourceRelativePath
  if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    if ($Optional) {
      return
    }
    throw "Required release file is missing: $SourceRelativePath"
  }

  $destinationPath = Join-Path $releaseRoot $DestinationRelativePath
  $destinationParent = Split-Path -Parent $destinationPath
  New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
  Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Force
}

if (Test-Path -LiteralPath $releaseRoot -PathType Leaf) {
  throw "OutputDirectory points to a file: $releaseRoot"
}
if (Test-Path -LiteralPath $releaseRoot -PathType Container) {
  if (@(Get-ChildItem -LiteralPath $releaseRoot -Force).Count -gt 0) {
    throw "OutputDirectory must be new or empty: $releaseRoot"
  }
}
else {
  New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
}

# Existing local files are deliberately not copied. Only these explicitly named
# files can enter the client package.
$rootFiles = @(
  @{ Source = "app.py"; Destination = "app.py" },
  @{ Source = "backend_client.py"; Destination = "backend_client.py" },
  @{ Source = "requirements.txt"; Destination = "requirements.txt" },
  @{ Source = "requirements-frontend.txt"; Destination = "requirements-frontend.txt" },
  @{ Source = "runtime.txt"; Destination = "runtime.txt" },
  @{ Source = ".env.example"; Destination = ".env.example" },
  @{ Source = ".streamlit\config.toml"; Destination = ".streamlit\config.toml" },
  @{ Source = "LICENSE"; Destination = "LICENSE" }
)

foreach ($file in $rootFiles) {
  Copy-ReleaseFile -SourceRelativePath $file.Source -DestinationRelativePath $file.Destination
}

foreach ($fileName in @("main.py", "pipeline.py", "schemas.py", "session_store.py", "__init__.py", "requirements.txt")) {
  Copy-ReleaseFile -SourceRelativePath ("backend\" + $fileName) -DestinationRelativePath ("backend\" + $fileName)
}

foreach ($fileName in @("__init__.py", "export_excel.py", "peak_extractor.py", "phase_detector.py", "phase_features.py", "utils.py")) {
  Copy-ReleaseFile -SourceRelativePath ("src\" + $fileName) -DestinationRelativePath ("src\" + $fileName)
}

foreach ($fileName in @("start_backend.ps1", "start_dashboard.ps1", "health_check.ps1", "build_release.ps1", "smoke_test.py")) {
  Copy-ReleaseFile -SourceRelativePath ("scripts\" + $fileName) -DestinationRelativePath ("scripts\" + $fileName)
}

$modelFiles = @(
  "model\catboost_model.cbm",
  "model\label_encoder_classes.npy",
  "model\phase_detector_hh.pkl",
  "model\phase_detector_metal.pkl",
  "model\RF Model\03012025\random_forest.pkl",
  "model\LSTM Model\02_12_2024\best_model_h5.keras",
  "model\LSTM Model\02_12_2024\final_model.h5",
  "model\LSTM Model\03_12_2024\best_model_h5.keras",
  "model\LSTM Model\03_12_2024\final_model.h5",
  "model\LSTM Model\11_12_2024\final_new_model.weights.h5",
  "model\LSTM Model\28_07_2025\enc-dec_lstm_model.h5",
  "model\LSTM Model\31_12_2024\final_model.h5"
)

foreach ($modelFile in $modelFiles) {
  Copy-ReleaseFile -SourceRelativePath $modelFile -DestinationRelativePath $modelFile
}

Copy-ReleaseFile -SourceRelativePath "model\catboost_training_metadata.json" `
  -DestinationRelativePath "training-artifacts\catboost_training_metadata.json"
Copy-ReleaseFile -SourceRelativePath "model\other_result_model.txt" `
  -DestinationRelativePath "training-artifacts\other_result_model.txt"
Copy-ReleaseFile -SourceRelativePath "special_points_perfect.csv" `
  -DestinationRelativePath "training-artifacts\special_points_perfect.csv"
Copy-ReleaseFile -SourceRelativePath "special_points_plateau_mean.csv" `
  -DestinationRelativePath "training-artifacts\special_points_plateau_mean.csv"

$sampleDirectory = Join-Path $repositoryRoot "data\GGA\File txt\N4-VS1-25-03-2024\10-5"
$representativeSampleItem = Get-ChildItem -LiteralPath $sampleDirectory -File |
  Where-Object { $_.Name -like "N4-10-5-01042024-Q=49.81mL*3.txt" } |
  Select-Object -First 1
if ($null -eq $representativeSampleItem) {
  throw "Required representative TXT sample is missing from $sampleDirectory"
}
$representativeSample = $representativeSampleItem.FullName.Substring($repositoryRoot.Length + 1)
Copy-ReleaseFile -SourceRelativePath $representativeSample `
  -DestinationRelativePath "sample-data\representative-sample.txt"

# These documents are produced by the documentation handoff task. They are
# optional here so the assembly script is usable before that task is complete.
foreach ($document in @(
  "README.md",
  "CLIENT_DEPLOYMENT.md",
  "OPERATIONS_RUNBOOK.md",
  "MODEL_CARD.md",
  "API_INTERNAL.md",
  "CHANGELOG.md"
)) {
  Copy-ReleaseFile -SourceRelativePath $document -DestinationRelativePath $document -Optional
}

# Do not allow a local secret to be silently hidden by the allowlist. Existing
# frontend log files and other unrelated untracked files are intentionally
# ignored; only secret-looking untracked names stop a release build.
$statusLines = @(git -C $repositoryRoot status --porcelain --untracked-files=all)
foreach ($statusLine in $statusLines) {
  if ($statusLine.Length -lt 3 -or $statusLine.Substring(0, 2) -ne "??") {
    continue
  }
  $untrackedPath = $statusLine.Substring(3).Trim().Trim('"')
  if ($untrackedPath -match "(?i)(^|[\\/])(\.env($|\.)|.*(secret|credential|password|token).*(\..*)?$|.*\.(pem|key|p12|pfx)$)") {
    throw "Refusing to build with untracked secret-looking file: $untrackedPath"
  }
}

$sourceCommit = (& git -C $repositoryRoot rev-parse HEAD 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($sourceCommit)) {
  throw "Unable to determine source commit with git rev-parse HEAD"
}

$runtimePython = (Get-Content (Join-Path $repositoryRoot "runtime.txt") -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($runtimePython)) {
  throw "runtime.txt is empty"
}

$activePython = "unavailable"
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($null -ne $pythonCommand) {
  $pythonOutput = @(& $pythonCommand.Source --version 2>&1)
  if ($LASTEXITCODE -eq 0 -and $pythonOutput.Count -gt 0) {
    $activePython = ($pythonOutput -join " ").Trim() -replace "^Python\s+", ""
  }
}

$dependencies = [ordered]@{}
foreach ($requirementsFile in @("requirements.txt", "requirements-frontend.txt", "backend\requirements.txt")) {
  $requirementsPath = Join-Path $repositoryRoot $requirementsFile
  foreach ($line in Get-Content $requirementsPath) {
    $trimmed = $line.Trim()
    if ($trimmed -eq "" -or $trimmed.StartsWith("#") -or $trimmed.StartsWith("-")) {
      continue
    }
    if ($trimmed -match "^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*([=!<>~]+)\s*([^\s;]+)") {
      $package = $matches[1].ToLowerInvariant()
      $dependencies[$package] = $matches[3]
    }
  }
}

$checksums = [ordered]@{}
$runtimeModelPaths = @()
foreach ($modelFile in $modelFiles) {
  $manifestPath = Convert-ToManifestPath $modelFile
  $packagedModel = Join-Path $releaseRoot $modelFile
  $checksums[$manifestPath] = (Get-FileHash -LiteralPath $packagedModel -Algorithm SHA256).Hash.ToLowerInvariant()
  $runtimeModelPaths += $manifestPath
}

$baseline = [ordered]@{
  sample = "sample-data/representative-sample.txt"
  status = "expected"
  expected = [ordered]@{
    peaks = 20
    classification = "GGA"
    classification_probability = 0.784
    toxicity_percent = 5.31
  }
}

$manifest = [ordered]@{
  release_version = $Version
  source_commit = $sourceCommit
  build_date_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
  python_version = [ordered]@{
    runtime = $runtimePython
    active = $activePython
  }
  dependencies = $dependencies
  runtime_models = $runtimeModelPaths
  checksums = $checksums
  baseline = $baseline
}

$manifestJson = $manifest | ConvertTo-Json -Depth 8
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $releaseRoot "RELEASE_MANIFEST.json"), $manifestJson + [Environment]::NewLine, $utf8NoBom)
[System.IO.File]::WriteAllText($sourceManifestPath, $manifestJson + [Environment]::NewLine, $utf8NoBom)

Write-Host "Release assembled: $releaseRoot"
Write-Host "Manifest: $(Join-Path $releaseRoot 'RELEASE_MANIFEST.json')"
