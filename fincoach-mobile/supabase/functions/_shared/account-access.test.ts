import { afterEach, describe, expect, it, vi } from 'vitest';
import { isAccountActive } from './account-access';
import { deliverAlert } from './deliver-alerts';

afterEach(() => vi.unstubAllGlobals());
const enforcement = (enabled: boolean) => vi.stubGlobal('Deno', { env: { get: () => enabled ? 'true' : undefined } });
const clientFor = (data: unknown, error: unknown = null) => ({ from: vi.fn(() => ({ select: () => ({ eq: () => ({ maybeSingle: async () => ({ data, error }) }) }) })) });

describe('service-side account enforcement', () => {
  it('leaves legacy deployments unchanged until enforcement is enabled', async () => {
    enforcement(false);const client = clientFor(null);
    expect(await isAccountActive(client as never, 'student')).toBe(true);
    expect(client.from).not.toHaveBeenCalled();
  });
  it('blocks suspended or missing accounts and fails closed on database errors', async () => {
    enforcement(true);
    expect(await isAccountActive(clientFor({ status: 'suspended' }) as never, 'student')).toBe(false);
    expect(await isAccountActive(clientFor(null) as never, 'student')).toBe(false);
    await expect(isAccountActive(clientFor(null, new Error('database unavailable')) as never, 'student')).rejects.toThrow();
  });
  it('does not claim or consume an attempt for an already suspended owner', async () => {
    enforcement(true);
    const client = { from: (table: string) => ({ select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: table === 'alerts' ? { user_id: 'student' } : { status: 'suspended' }, error: null }) }) }) }), rpc: vi.fn() };
    expect(await deliverAlert(client as never, 'alert')).toEqual({ status: 'skipped', attemptedDevices: 0 });
    expect(client.rpc).not.toHaveBeenCalled();
  });
  it('releases a claim if suspension races the claim', async () => {
    enforcement(true);let checks = 0;const update = vi.fn(() => ({ eq: () => ({ eq: async () => ({ error: null }) }) }));
    const client = { from: (table: string) => ({ select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: table === 'alerts' ? { user_id: 'student' } : { status: ++checks === 1 ? 'active' : 'suspended' }, error: null }) }) }), update }), rpc: async () => ({ data: { id: 'alert', user_id: 'student', delivery_attempt_count: 1 }, error: null }) };
    expect(await deliverAlert(client as never, 'alert')).toEqual({ status: 'skipped', attemptedDevices: 0 });
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ delivery_status: 'retryable', delivery_attempt_count: 0 }));
  });
});
