param(
  [Parameter(Mandatory=$true)][string]$Task,
  [Parameter(Mandatory=$true)][string]$Result
)

$ErrorActionPreference = 'Stop'
$log = @()
$status = 'FAILED'
$errorText = ''
$exports = @()
$opju = ''
$reopen = 'NOT_RUN'
$app = $null
$app2 = $null

function Write-Log([string]$message) {
  $script:log += ('{0} {1}' -f (Get-Date -Format 'o'), $message)
}

try {
  $taskData = Get-Content -LiteralPath $Task -Raw -Encoding UTF8 | ConvertFrom-Json
  $app = New-Object -ComObject Origin.Application
  Write-Log ('COM version=' + $app.Evaluate('system.version'))
  $app.NewProject() | Out-Null
  $sanitized = @()

  foreach ($figure in $taskData.figures) {
    $csvPath = $figure.csv
    if (-not (Test-Path -LiteralPath $csvPath)) { throw ('CSV missing: ' + $csvPath) }
    $rows = Import-Csv -LiteralPath $csvPath -Encoding UTF8
    if ($rows.Count -eq 0) { Write-Log ('SKIP empty figure ' + $figure.figure_id); continue }
    $columns = @($rows[0].PSObject.Properties.Name)
    $data = New-Object 'object[,]' $rows.Count, $columns.Count
    $lastNumeric = 1
    for ($r = 0; $r -lt $rows.Count; $r++) {
      for ($c = 0; $c -lt $columns.Count; $c++) {
        $raw = [string]$rows[$r].($columns[$c])
        $number = 0.0
        if ([double]::TryParse($raw, [ref]$number)) {
          $data[$r, $c] = $number
          $lastNumeric = $c + 1
        } else {
          $data[$r, $c] = $raw
        }
      }
    }
    $book = ($figure.figure_id -replace '-', '_')
    $sanitized += $book
    $app.Execute('newbook name:=' + $book + ';') | Out-Null
    $wks = $app.FindWorksheet('')
    if (-not $wks) { throw ('Worksheet not found for ' + $book) }
    if (-not $wks.SetData($data, 0, 0)) { throw ('SetData failed for ' + $book) }
    $app.Execute('plotxy iy:=[' + $book + ']Sheet1!(' + $lastNumeric + ') plot:=200;') | Out-Null
    $app.Execute('set %c -c color(#0271AC);') | Out-Null
    $app.Execute('xaxis.title$="source_value"; yaxis.title$="' + $figure.y + '";') | Out-Null
    foreach ($fmt in $taskData.formats) {
      $name = $figure.figure_id + '.' + $fmt
      $target = Join-Path $taskData.output_dir $name
      if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force }
      $ok = $app.Execute('expGraph type:=' + $fmt + ' path:="' + $taskData.output_dir + '" filename:="' + $name + '";')
      if ($ok) { $exports += @{ figure_id = $figure.figure_id; format = $fmt; file = (Join-Path $taskData.output_dir $name) } }
      Write-Log ('export ' + $name + '=' + $ok)
    }
  }
  $opju = Join-Path $taskData.output_dir 'origin_project.opju'
  if (Test-Path -LiteralPath $opju) { Remove-Item -LiteralPath $opju -Force }
  if (-not $app.Save($opju)) { throw 'OPJU save failed' }
  $app.Exit() | Out-Null
  $app = $null
  Start-Sleep -Seconds 2

  $app2 = New-Object -ComObject Origin.Application
  if (-not $app2.Load($opju)) { throw 'OPJU reopen failed' }
  if ($sanitized.Count -gt 0) {
    $checkName = '[' + $sanitized[0] + ']Sheet1'
    $reopen = if ($app2.FindWorksheet($checkName)) { 'PASS:' + $checkName } else { 'FAIL:' + $checkName }
  }
  $app2.Exit() | Out-Null
  $app2 = $null
  $status = 'OK'
} catch {
  $errorText = $_.Exception.Message
  Write-Log ('ERROR ' + $errorText)
} finally {
  foreach ($o in @($app, $app2)) {
    if ($o) { try { $o.Exit() | Out-Null } catch {} ; try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($o) | Out-Null } catch {} }
  }
  $payload = @{
    task_id = $taskData.task_id
    status = $status
    error = $errorText
    opju_path = $opju
    reopen_check = $reopen
    exports = $exports
    log = $log
    completed_at = (Get-Date -Format 'o')
  } | ConvertTo-Json -Depth 6
  [System.IO.File]::WriteAllText($Result, $payload, [System.Text.Encoding]::UTF8)
  Write-Output $payload
}
