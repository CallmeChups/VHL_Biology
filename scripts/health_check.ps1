param(
  [string]$BackendUrl = "http://127.0.0.1:8000",
  [string]$DashboardUrl = "http://127.0.0.1:8501"
)

function Test-HttpEndpoint {
  param(
    [string]$Name,
    [string]$Uri
  )

  try {
    $response = Invoke-WebRequest -Uri $Uri -Method Get -UseBasicParsing -TimeoutSec 10
    $statusCode = [int]$response.StatusCode
    Write-Host "$Name $Uri -> HTTP $statusCode"
    return ($statusCode -ge 200 -and $statusCode -lt 300)
  }
  catch {
    $errorResponse = $_.Exception.Response
    if ($null -ne $errorResponse) {
      $statusCode = [int]$errorResponse.StatusCode
      Write-Host "$Name $Uri -> HTTP $statusCode"
    }
    else {
      Write-Host "$Name $Uri -> connection failed: $($_.Exception.Message)"
    }
    return $false
  }
}

$backendHealthUrl = "$($BackendUrl.TrimEnd('/'))/health"
$backendOk = Test-HttpEndpoint -Name "Backend" -Uri $backendHealthUrl
$dashboardOk = Test-HttpEndpoint -Name "Dashboard" -Uri $DashboardUrl.TrimEnd('/')

if (-not $backendOk -or -not $dashboardOk) {
  exit 1
}
