import React from 'react';
import { act, create } from 'react-test-renderer';
import { CoachActionCard } from '@/components/coach/coach-interaction-card';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const fixture = vi.hoisted(() => ({ sign: vi.fn(), lookup: vi.fn(), open: vi.fn() }));
vi.mock('@expo/vector-icons', () => ({ MaterialCommunityIcons: 'Icon' }));
vi.mock('react-native', () => ({ Linking: { openURL: fixture.open }, TextInput: 'Input', View: 'View' }));
vi.mock('@/components/ui/animated-pressable', () => ({ AnimatedPressable: 'Button' }));
vi.mock('@/components/ui/app-text', () => ({ AppText: 'Text' }));
vi.mock('@/lib/reports', () => ({ createReportSignedUrl: fixture.sign, fetchReportStoragePath: fixture.lookup }));


describe('stored report access', () => {
  beforeEach(() => { vi.resetAllMocks(); });
  it('opens the current restored history path instead of the embedded obsolete path', async () => {
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    const oldPath = 'owner/coach/attempt.pdf';
    const restoredPath = 'owner/restored/backup/new-run/report.pdf';
    fixture.sign.mockImplementation(async (path: string) => {
      if (path === oldPath) throw new Error('Object not found');
      return 'https://example.invalid/restored-report.pdf';
    });
    fixture.lookup.mockResolvedValue(restoredPath);
    let renderer!: ReturnType<typeof create>;
    await act(async () => { renderer = create(<CoachActionCard busy={false} onCancel={() => {}} onChange={() => {}} onConfirm={() => {}} payload={{
      type: 'action', action_id: 'action', action_type: 'generate_report', status: 'executed',
      title: 'Saved report', description: '', arguments: {}, fields: [], confirm_label: 'Generate',
      result: { report_id: 77, storage_path: oldPath },
    }} />); });
    await act(async () => { await renderer.root.findByProps({ accessibilityLabel: 'Open the generated report PDF' }).props.onPress(); });
    expect(fixture.sign).toHaveBeenCalledWith(restoredPath);
    expect(fixture.lookup).toHaveBeenCalledWith(77);
    expect(fixture.open).toHaveBeenCalledWith('https://example.invalid/restored-report.pdf');
    expect(JSON.stringify(renderer.toJSON())).not.toContain('Object not found');
    await act(async () => renderer.unmount());
  });
});


it.each([false, true])('uses only the legacy path without an id; lookup failure with id=%s stays an error', async (hasId) => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  fixture.lookup.mockRejectedValue(new Error('Report no longer in history'));
  fixture.sign.mockResolvedValue('https://example.invalid/legacy.pdf');
  let renderer!: ReturnType<typeof create>;
  await act(async () => { renderer = create(<CoachActionCard busy={false} onCancel={() => {}} onChange={() => {}} onConfirm={() => {}} payload={{
    type: 'action', action_id: 'action', action_type: 'generate_report', status: 'executed',
    title: 'Saved report', description: '', arguments: {}, fields: [], confirm_label: 'Generate',
    result: { ...(hasId ? { report_id: 77 } : {}), storage_path: 'owner/legacy.pdf' },
  }} />); });
  fixture.sign.mockClear(); fixture.lookup.mockClear(); fixture.open.mockClear();
  await act(async () => renderer.root.findByProps({ accessibilityLabel: 'Open the generated report PDF' }).props.onPress());
  if (hasId) {
    expect(fixture.lookup).toHaveBeenCalledWith(77);
    expect(fixture.sign).not.toHaveBeenCalled();
    expect(fixture.open).not.toHaveBeenCalled();
    expect(JSON.stringify(renderer.toJSON())).toContain('Report no longer in history');
  } else {
    expect(fixture.lookup).not.toHaveBeenCalled();
    expect(fixture.sign).toHaveBeenCalledWith('owner/legacy.pdf');
    expect(fixture.open).toHaveBeenCalledWith('https://example.invalid/legacy.pdf');
  }
  await act(async () => renderer.unmount());
});
