import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const stageArgument = process.argv.find((argument) => argument.startsWith('--stage='));
const stage = stageArgument?.split('=')[1] ?? 'all';
assert.ok(['register', 'send', 'all'].includes(stage), 'Stage must be register, send, or all.');

let failed = false;

function verifyFile(relativePath, requiredFragments, forbiddenFragments = []) {
  const path = join(root, relativePath);
  if (!existsSync(path)) {
    failed = true;
    console.error(`Missing ${relativePath}`);
    return;
  }

  const source = readFileSync(path, 'utf8').toLowerCase().replace(/\s+/g, ' ');
  for (const fragment of requiredFragments) {
    if (!source.includes(fragment.toLowerCase().replace(/\s+/g, ' '))) {
      failed = true;
      console.error(`${relativePath} is missing: ${fragment}`);
    }
  }
  for (const fragment of forbiddenFragments) {
    if (source.includes(fragment.toLowerCase().replace(/\s+/g, ' '))) {
      failed = true;
      console.error(`${relativePath} contains forbidden fragment: ${fragment}`);
    }
  }
}

verifyFile('supabase/functions/_shared/http.ts', [
  'access-control-allow-origin',
  'access-control-allow-headers',
  'authorization',
  'x-fincoach-webhook-secret',
  'x-fincoach-cron-secret',
  'jsonresponse',
  'errorresponse',
]);

verifyFile(
  'supabase/functions/_shared/supabase.ts',
  [
    'npm:@supabase/supabase-js@2.108.1',
    'supabase_url',
    'supabase_anon_key',
    'supabase_service_role_key',
    'auth: { persistSession: false, autoRefreshToken: false }',
  ],
  ['console.log'],
);

verifyFile(
  'supabase/functions/register-device/index.ts',
  [
    "action === 'register'",
    "action === 'refresh'",
    "action === 'deactivate'",
    "authorization?.replace('bearer ', '')",
    'auth.getuser(token)',
    "rpc('reassign_user_device'",
    "rpc('deactivate_user_device'",
    'expopushtoken',
    'deviceName',
    "platform !== 'android' && platform !== 'ios'",
    'request.method === \'options\'',
  ],
  ['body.userid', 'body.user_id', 'console.log(expo', 'console.log(token'],
);

verifyFile('supabase/config.toml', [
  '[functions.register-device]',
  'verify_jwt = true',
]);

if (stage === 'send' || stage === 'all') {
  verifyFile('supabase/functions/_shared/push-domain.ts', [
    'chunkexpomessages',
    'classifyexpoerror',
    'nextretrydelaymilliseconds',
    'aggregatedeliverystatus',
  ]);
  verifyFile('supabase/functions/_shared/deliver-alerts.ts', [
    "rpc('claim_alert_delivery'",
    'https://exp.host/--/api/v2/push/send',
    'delivery_receipts',
    'deviceid',
    'devicenotregistered',
  ]);
  verifyFile(
    'supabase/functions/send-alert/index.ts',
    ['x-fincoach-webhook-secret', 'alertid', 'deliveralert', 'timingsafeequal'],
    ['console.log(token', 'console.log(message'],
  );
  verifyFile('supabase/config.toml', ['[functions.send-alert]', 'verify_jwt = false']);
}

if (stage === 'all') {
  verifyFile('supabase/functions/_shared/due-domain.ts', [
    'spendingperiod',
    'advancerecurrence',
    'pending_alert_recovery_delay_ms',
    'shouldattemptalertdelivery',
    'summarizereceipts',
  ]);
  verifyFile(
    'supabase/functions/process-alerts/index.ts',
    [
      'x-fincoach-cron-secret',
      'processbillreminders',
      'processsavingsdeadlines',
      'processspendingreminders',
      'processrecoverabledeliveries',
      'processpushreceipts',
      "eq('delivery_status', 'pending')",
      "lte('created_at', pendingbefore)",
      "eq('delivery_status', 'retryable')",
      "lte('next_delivery_attempt_at', now.toisostring())",
      'recoverable_delivery_batch_size = 100',
      '.slice(0, recoverable_delivery_batch_size)',
      'shouldattemptalertdelivery',
      'deliveralert',
    ],
    ['functions.invoke(', '/functions/v1/send-alert'],
  );
  verifyFile('supabase/config.toml', ['[functions.process-alerts]', 'verify_jwt = false']);
}

if (failed) process.exit(1);
console.log(`Alert Edge Function verification passed for stage: ${stage}.`);
