$ErrorActionPreference = "Continue"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$summaryScript = Join-Path $root "script\news_data\eval\regime_news_summary.py"
$loadScript = Join-Path $root "script\load_regime_to_db.py"
$targetEnd = "2026-06-14"

$jobs = @(
    @{ DbTicker = "005930"; AnalysisTicker = "005930"; Start = "2026-06-10" },
    @{ DbTicker = "000660"; AnalysisTicker = "000660"; Start = "2026-06-09" },
    @{ DbTicker = "005380"; AnalysisTicker = "005380"; Start = "2026-06-02" },
    @{ DbTicker = "000270"; AnalysisTicker = "000270"; Start = "2026-06-10" },
    @{ DbTicker = "079550"; AnalysisTicker = "079550"; Start = "2026-06-09" },
    @{ DbTicker = "012450"; AnalysisTicker = "012450"; Start = "2026-05-26" },
    @{ DbTicker = "105560"; AnalysisTicker = "105560"; Start = "2026-06-08" },
    @{ DbTicker = "055550"; AnalysisTicker = "055550"; Start = "2026-06-10" },
    @{ DbTicker = "051910"; AnalysisTicker = "051910"; Start = "2026-06-10" },
    @{ DbTicker = "096770"; AnalysisTicker = "096770"; Start = "2026-06-05" },
    @{ DbTicker = "USD"; AnalysisTicker = "USD_KRW"; Start = "2026-06-10" },
    @{ DbTicker = "000000"; AnalysisTicker = "KOSPI200"; Start = "2026-06-09" }
)

Set-Location $root
foreach ($job in $jobs) {
    $dbTicker = $job.DbTicker
    $analysisTicker = $job.AnalysisTicker
    $start = $job.Start
    Write-Output "[$(Get-Date -Format s)] START $dbTicker ($analysisTicker): $start ~ $targetEnd"

    & $python $summaryScript --provider openrouter --ticker $analysisTicker --start $start --end $targetEnd
    if ($LASTEXITCODE -ne 0) {
        Write-Output "[$(Get-Date -Format s)] SUMMARY FAILED $dbTicker (exit=$LASTEXITCODE)"
        continue
    }

    if ($analysisTicker -ne $dbTicker) {
        $source = Join-Path $root "data\$analysisTicker\regime_news_summary_$analysisTicker.json"
        $targetDir = Join-Path $root "data\$dbTicker"
        $target = Join-Path $targetDir "regime_news_summary_$dbTicker.json"
        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -Force
    }

    & $python $loadScript --ticker $dbTicker --since $start
    if ($LASTEXITCODE -ne 0) {
        Write-Output "[$(Get-Date -Format s)] DB LOAD FAILED $dbTicker (exit=$LASTEXITCODE)"
        continue
    }

    Write-Output "[$(Get-Date -Format s)] DONE $dbTicker"
}

Write-Output "[$(Get-Date -Format s)] BACKFILL FINISHED"
