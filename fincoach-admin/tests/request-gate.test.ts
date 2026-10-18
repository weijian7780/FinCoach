import assert from 'node:assert/strict';
import { test } from 'node:test';
import { LatestRequestGate } from '../src/request-gate.ts';

test('a slow previous search cannot replace the latest results', async () => {
  const gate = new LatestRequestGate();
  let finishOld!: (value: string) => void;
  let displayed = '';
  const old = gate.begin();
  const pending = new Promise<string>(resolve => { finishOld = resolve; }).then(value => { if (old.isCurrent()) displayed = value; });
  const latest = gate.begin();
  if (latest.isCurrent()) displayed = 'new search';
  finishOld('old search');
  await pending;
  assert.equal(displayed, 'new search');
});

test('tab cleanup or sign-out invalidates pending requests', () => {
  const gate = new LatestRequestGate();
  const pending = gate.begin();
  gate.invalidate();
  assert.equal(pending.isCurrent(), false);
  assert.equal(gate.begin().isCurrent(), true);
});
