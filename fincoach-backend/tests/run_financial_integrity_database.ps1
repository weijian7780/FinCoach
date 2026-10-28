# Requires Docker Desktop. Creates an offline throwaway database; never reads app credentials.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$containerName = 'fincoach-integrity-' + [guid]::NewGuid().ToString('N').Substring(0, 10)
$temporarySql = Join-Path $projectRoot ('fincoach-mobile/.test-tmp/' + $containerName + '.sql')
$created = $false
function Invoke-TestDocker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw "Docker test command failed with exit code $LASTEXITCODE" }
}
try {
    $schema = Get-Content -Raw -LiteralPath (Join-Path $projectRoot 'fincoach-mobile/supabase/schema.sql')
    # These hosted services are unrelated to the tested database operations.
    $schema = ($schema -split "`n" | Where-Object { $_ -notmatch '^create extension if not exists (pg_net|pg_cron|supabase_vault) ' }) -join "`n"
    $parts = @((Get-Content -Raw -LiteralPath (Join-Path $projectRoot 'fincoach-backend/docs/admin/full-schema-fixture.sql')), $schema,
      (Get-Content -Raw -LiteralPath (Join-Path $projectRoot 'fincoach-backend/sql/knowledge.sql')))
    foreach ($name in @('20261001100105_admin_panel.sql','20261010151101_complete_financial_backup_v2.sql','20261015091221_repair_financial_integrity_and_admin_sync.sql','20261015092100_recover_coaching_processing_leases.sql','20261015114924_atomic_coach_action_transitions.sql','20261016120000_report_attempt_protocol.sql','20261017120000_report_claim_and_artifact_verification.sql')) {
        $parts += Get-Content -Raw -LiteralPath (Join-Path $projectRoot "fincoach-mobile/supabase/migrations/$name")
    }
    New-Item -ItemType Directory -Force (Split-Path $temporarySql -Parent) | Out-Null
    Set-Content -LiteralPath $temporarySql -Value ($parts -join "`n") -Encoding utf8
    Invoke-TestDocker run --name $containerName --network none -e POSTGRES_PASSWORD=local-disposable-test -d pgvector/pgvector:pg17 | Out-Null
    $created = $true
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        & docker exec $containerName pg_isready -U postgres *> $null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 1
    }
    # pg_isready can answer while the postmaster is still finishing startup.
    Start-Sleep -Seconds 3
    Invoke-TestDocker cp $temporarySql "${containerName}:/tmp/schema.sql"
    Invoke-TestDocker exec -e PGOPTIONS='-c client_min_messages=warning' $containerName psql -U postgres -v ON_ERROR_STOP=1 -q -f /tmp/schema.sql
    foreach ($name in @('financial_integrity_assertions.sql','receipt_restore_assertions.sql','backup_report_category_assertions.sql','coaching_action_assertions.sql','report_attempt_assertions.sql')) {
        Invoke-TestDocker cp (Join-Path $PSScriptRoot $name) "${containerName}:/tmp/assertions.sql"
        Invoke-TestDocker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 -q -f /tmp/assertions.sql | Out-Null
        Write-Output "$name passed"
    }
    Invoke-TestDocker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 -q -c 'create table public.test_concurrent_claims(message_id uuid); grant insert on public.test_concurrent_claims to service_role;'
    Invoke-TestDocker cp (Join-Path $PSScriptRoot 'coaching_claim_concurrency.sql') "${containerName}:/tmp/concurrent.sql"
    Invoke-TestDocker exec $containerName pgbench -U postgres -d postgres -n -c 8 -j 8 -t 1 -f /tmp/concurrent.sql
    Invoke-TestDocker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 -q -c 'select public.test_assert((select count(*)=1 from public.test_concurrent_claims), $$eight concurrent attempts yield one claim$$);' | Out-Null
    Invoke-TestDocker cp (Join-Path $PSScriptRoot 'coaching_action_concurrency.sql') "${containerName}:/tmp/actions.sql"
    Invoke-TestDocker exec $containerName pgbench -U postgres -d postgres -n -c 8 -j 8 -t 3 -f /tmp/actions.sql
    Invoke-TestDocker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 -q -c 'select public.test_assert((select (ui_payload->>$$status$$=$$executed$$ and (select count(*)=1 from public.reminders where id=$$00000000-0000-0000-0000-000000002004$$)) or (ui_payload->>$$status$$=$$cancelled$$ and not exists(select 1 from public.reminders where id=$$00000000-0000-0000-0000-000000002004$$)) from public.coaching_messages where id=$$00000000-0000-0000-0000-000000001004$$), $$race outcome and reminder agree$$);' | Out-Null
    Invoke-TestDocker cp (Join-Path $PSScriptRoot 'report_attempt_concurrency.sql') "${containerName}:/tmp/report_race.sql"
    Invoke-TestDocker exec $containerName pgbench -U postgres -d postgres -n -c 8 -j 8 -t 1 -f /tmp/report_race.sql
    Invoke-TestDocker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 -q -c 'select public.test_assert(((select ui_payload->>$$status$$=$$executed$$ from public.coaching_messages where id=$$00000000-0000-0000-0000-000000001111$$) and (select count(*)=1 from public.report_attempts a join public.reports r on r.id=a.report_id and r.report_key=$$coach:$$||a.attempt_id::text and r.storage_path=a.storage_path where a.action_id=$$00000000-0000-0000-0000-000000002111$$ and a.status=$$completed$$)) or ((select ui_payload->>$$status$$=$$cancelled$$ from public.coaching_messages where id=$$00000000-0000-0000-0000-000000001111$$) and not exists(select 1 from public.report_attempts where action_id=$$00000000-0000-0000-0000-000000002111$$ and status in ($$active$$,$$completed$$)) and not exists(select 1 from public.report_attempts a join public.reports r on r.id=a.report_id where a.action_id=$$00000000-0000-0000-0000-000000002111$$)), $$random race outcome and report history agree$$);' | Out-Null
    Invoke-TestDocker cp (Join-Path $PSScriptRoot 'report_attempt_confirmation_concurrency.sql') "${containerName}:/tmp/report_confirm.sql"
    Invoke-TestDocker exec $containerName pgbench -U postgres -d postgres -n -c 8 -j 8 -t 1 -f /tmp/report_confirm.sql
    Invoke-TestDocker exec $containerName psql -U postgres -v ON_ERROR_STOP=1 -q -c 'select public.test_assert((select ui_payload->>$$status$$=$$executed$$ from public.coaching_messages where id=$$00000000-0000-0000-0000-000000001112$$) and (select count(*)=1 from public.report_attempts where action_id=$$00000000-0000-0000-0000-000000002112$$ and status=$$completed$$) and (select count(*)=1 from public.report_attempts a join public.reports r on r.id=a.report_id and r.report_key=$$coach:$$||a.attempt_id::text and r.storage_path=a.storage_path where a.action_id=$$00000000-0000-0000-0000-000000002112$$), $$eight concurrent confirmations yield one attempt and one history row$$);' | Out-Null
    Write-Output 'Eight concurrent claims: one winner. Concurrent action decisions and persisted effects agree. Concurrent report confirmations and cancellations keep one attempt and one history row. All database checks passed.' 
} finally {
    if ($created) { Invoke-TestDocker rm -f -v $containerName | Out-Null }
    if (Test-Path -LiteralPath $temporarySql) { Remove-Item -LiteralPath $temporarySql }
}
