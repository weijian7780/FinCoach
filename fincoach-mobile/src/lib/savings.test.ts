import {
  addSavingsContribution,
  createSavingsGoal,
  deleteSavingsContribution,
  deleteSavingsGoal,
  fetchSavingsContributions,
  fetchSavingsGoal,
  fetchSavingsGoals,
  updateSavingsGoal,
} from '@/lib/savings';
import { beforeEach, describe, expect, test, vi } from 'vitest';

vi.mock('@/lib/supabase', () => ({ supabase: {} }));

const goalId = '89b5e0f2-9e3e-4a20-9d78-f0d5c3de4e84';

const goal = {
  id: goalId,
  user_id: 'user-1',
  name: 'Laptop',
  target_amount: 3000,
  current_amount: 500,
  deadline: '2026-12-01',
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

function createClient(result: { data?: unknown; error?: unknown } = {}) {
  const response = { data: result.data ?? null, error: result.error ?? null };
  const builder: Record<string, ReturnType<typeof vi.fn>> & {
    then?: (resolve: (value: typeof response) => unknown, reject?: (reason: unknown) => unknown) => Promise<unknown>;
  } = {
    select: vi.fn(),
    eq: vi.fn(),
    order: vi.fn(),
    insert: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    single: vi.fn(),
    maybeSingle: vi.fn(),
  };

  for (const method of ['select', 'eq', 'order', 'insert', 'update', 'delete'] as const) {
    builder[method].mockReturnValue(builder);
  }
  builder.single.mockResolvedValue(response);
  builder.maybeSingle.mockResolvedValue(response);
  builder.then = (resolve, reject) => Promise.resolve(response).then(resolve, reject);

  const client = { from: vi.fn().mockReturnValue(builder) };
  return { builder, client };
}

beforeEach(() => vi.useRealTimers());

describe('goal persistence', () => {
  test('lists goals for the signed-in owner by deadline and creation order', async () => {
    const { builder, client } = createClient({ data: [goal] });

    await expect(fetchSavingsGoals('user-1', client)).resolves.toEqual([goal]);

    expect(client.from).toHaveBeenCalledWith('savings_goals');
    expect(builder.eq).toHaveBeenCalledWith('user_id', 'user-1');
    expect(builder.order).toHaveBeenNthCalledWith(1, 'deadline', { ascending: true, nullsFirst: false });
    expect(builder.order).toHaveBeenNthCalledWith(2, 'created_at', { ascending: true });
  });

  test('fetches one goal by both goal id and owner id', async () => {
    const { builder, client } = createClient({ data: goal });

    await expect(fetchSavingsGoal(goalId, 'user-1', client)).resolves.toEqual(goal);

    expect(builder.eq).toHaveBeenNthCalledWith(1, 'id', goalId);
    expect(builder.eq).toHaveBeenNthCalledWith(2, 'user_id', 'user-1');
    expect(builder.maybeSingle).toHaveBeenCalledOnce();
  });

  test('creates goal metadata without accepting a caller-supplied current balance', async () => {
    const { builder, client } = createClient({ data: goal });

    await createSavingsGoal(
      'user-1',
      { name: 'Laptop', target_amount: 3000, deadline: '2026-12-01' },
      client,
    );

    expect(builder.insert).toHaveBeenCalledWith({
      user_id: 'user-1',
      name: 'Laptop',
      target_amount: 3000,
      deadline: '2026-12-01',
    });
  });

  test('updates only editable metadata and filters by owner', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-12T10:00:00Z'));
    const { builder, client } = createClient({ data: goal });

    await updateSavingsGoal(
      goalId,
      'user-1',
      { name: 'New laptop', target_amount: 3500, deadline: '2027-01-01' },
      client,
    );

    expect(builder.update).toHaveBeenCalledWith({
      name: 'New laptop',
      target_amount: 3500,
      deadline: '2027-01-01',
      updated_at: '2026-07-12T10:00:00.000Z',
    });
    expect(builder.eq).toHaveBeenCalledWith('user_id', 'user-1');
  });

  test('deletes a goal only by goal id and owner id', async () => {
    const { builder, client } = createClient();
    await deleteSavingsGoal(goalId, 'user-1', client);
    expect(builder.eq).toHaveBeenNthCalledWith(1, 'id', goalId);
    expect(builder.eq).toHaveBeenNthCalledWith(2, 'user_id', 'user-1');
  });
});

describe('contribution persistence', () => {
  test('lists contribution history newest first', async () => {
    const contribution = {
      id: 3,
      goal_id: goalId,
      amount: 50,
      contributed_on: '2026-07-12',
      note: null,
      created_at: '2026-07-12T10:00:00Z',
    };
    const { builder, client } = createClient({ data: [contribution] });

    await expect(fetchSavingsContributions(goalId, client)).resolves.toEqual([contribution]);

    expect(builder.eq).toHaveBeenCalledWith('goal_id', goalId);
    expect(builder.order).toHaveBeenNthCalledWith(1, 'contributed_on', { ascending: false });
    expect(builder.order).toHaveBeenNthCalledWith(2, 'created_at', { ascending: false });
  });

  test('adds normalized contribution fields without duplicating user ownership', async () => {
    const { builder, client } = createClient({ data: { id: 3 } });

    await addSavingsContribution(
      goalId,
      { amount: 50, contributed_on: '2026-07-12', note: 'Part-time pay' },
      client,
    );

    expect(builder.insert).toHaveBeenCalledWith({
      goal_id: goalId,
      amount: 50,
      contributed_on: '2026-07-12',
      note: 'Part-time pay',
    });
  });

  test('deletes a contribution by id', async () => {
    const { builder, client } = createClient();
    await deleteSavingsContribution(3, client);
    expect(builder.eq).toHaveBeenCalledWith('id', 3);
  });

  test('propagates Supabase errors instead of returning an empty success', async () => {
    const error = new Error('RLS denied');
    const { client } = createClient({ error });
    await expect(fetchSavingsGoals('user-1', client)).rejects.toBe(error);
  });
});
