$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "=== [USD] 환율 국면 분석  2026-03-31 ~ 2026-06-02 ===" -ForegroundColor Cyan
python script/news_data/regime_news_summary.py `
    --provider openrouter `
    --ticker-code USD --ticker-name "USD/KRW" --sector "환율" `
    --s3-ticker USD_KRW --fdr-ticker "USD/KRW" `
    --start 2026-03-31 --end 2026-06-02
if ($LASTEXITCODE -ne 0) { Write-Host "[USD] 분석 실패" -ForegroundColor Red; exit 1 }

Write-Host "`n=== [USD] DB 업로드  --since 2026-03-31 ===" -ForegroundColor Cyan
python script/load_regime_to_db.py --ticker USD --since 2026-03-31
if ($LASTEXITCODE -ne 0) { Write-Host "[USD] DB 업로드 실패" -ForegroundColor Red; exit 1 }
Write-Host "[USD] 완료" -ForegroundColor Green

Write-Host "`n=== [000000] KOSPI 국면 분석  2026-05-12 ~ 2026-06-02 ===" -ForegroundColor Cyan
python script/news_data/regime_news_summary.py `
    --provider openrouter `
    --ticker-code 000000 --ticker-name "KOSPI" --sector "지수" `
    --s3-ticker KOSPI200 --fdr-ticker KS11 `
    --start 2026-05-12 --end 2026-06-02
if ($LASTEXITCODE -ne 0) { Write-Host "[000000] 분석 실패" -ForegroundColor Red; exit 1 }

Write-Host "`n=== [000000] DB 업로드  --since 2026-05-12 ===" -ForegroundColor Cyan
python script/load_regime_to_db.py --ticker 000000 --since 2026-05-12
if ($LASTEXITCODE -ne 0) { Write-Host "[000000] DB 업로드 실패" -ForegroundColor Red; exit 1 }
Write-Host "[000000] 완료" -ForegroundColor Green

Write-Host "`n=== 전체 완료 ===" -ForegroundColor Green
