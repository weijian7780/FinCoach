import { describe, expect, test } from 'vitest';

import {
  appDialogReducer,
  canDismissAppDialog,
  initialAppDialogState,
  type AppDialogRequest,
} from './app-dialog-state';

const first: AppDialogRequest = {
  id: 1,
  kind: 'alert',
  options: { title: 'Saved', tone: 'success' },
  resolve: () => undefined,
};

const second: AppDialogRequest = {
  id: 2,
  kind: 'confirm',
  options: { title: 'Delete?', tone: 'destructive', confirmLabel: 'Delete' },
  resolve: () => undefined,
};

describe('app dialog queue', () => {
  test('shows the first enqueued request', () => {
    const state = appDialogReducer(initialAppDialogState, { type: 'enqueue', request: first });
    expect(state.active).toBe(first);
    expect(state.pending).toEqual([]);
  });

  test('keeps later requests in FIFO order', () => {
    let state = appDialogReducer(initialAppDialogState, { type: 'enqueue', request: first });
    state = appDialogReducer(state, { type: 'enqueue', request: second });
    expect(state.active).toBe(first);
    expect(state.pending).toEqual([second]);
  });

  test('advances to the next request after resolving the active request', () => {
    let state = appDialogReducer(initialAppDialogState, { type: 'enqueue', request: first });
    state = appDialogReducer(state, { type: 'enqueue', request: second });
    state = appDialogReducer(state, { type: 'advance' });
    expect(state.active).toBe(second);
    expect(state.pending).toEqual([]);
  });

  test('returns to an empty state after the final request', () => {
    let state = appDialogReducer(initialAppDialogState, { type: 'enqueue', request: first });
    state = appDialogReducer(state, { type: 'advance' });
    expect(state).toEqual(initialAppDialogState);
  });

  test('allows dismissing alerts but treats confirmation dismissal as cancellation', () => {
    expect(canDismissAppDialog({ ...first, options: { title: 'Information' } })).toBe(true);
    expect(canDismissAppDialog(second)).toBe(true);
  });
});
