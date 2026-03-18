# Check status of all services
Write-Host "Industrial Tag Processor - Service Status" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

docker-compose ps

Write-Host "`nContainer Details:" -ForegroundColor Yellow
docker ps --filter "name=tag_processor" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

Write-Host "`nHealth Check:" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8000/system/health" -Method Get -TimeoutSec 5
    Write-Host "API Status: " -NoNewline -ForegroundColor Green
    Write-Host $response.status -ForegroundColor White
} catch {
    Write-Host "API Status: Unavailable" -ForegroundColor Red
}

try {
    $stats = Invoke-RestMethod -Uri "http://localhost:8000/system/stats" -Method Get -TimeoutSec 5
    Write-Host "`nSystem Statistics:" -ForegroundColor Yellow
    Write-Host "  Total Tags:        $($stats.total_tags)" -ForegroundColor White
    Write-Host "  Last Processed ID: $($stats.last_processed_id)" -ForegroundColor White
    Write-Host "  DB Lag:            $($stats.db_lag)" -ForegroundColor White
    Write-Host "  Batches Processed: $($stats.batches_processed)" -ForegroundColor White
    Write-Host "  Tags/Second:       $($stats.tags_per_second)" -ForegroundColor White
    Write-Host "  Avg Batch Time:    $($stats.avg_batch_time_ms) ms" -ForegroundColor White
    Write-Host "  Uptime:            $($stats.uptime_seconds) seconds" -ForegroundColor White
} catch {
    Write-Host "Unable to fetch system statistics." -ForegroundColor Red
}
