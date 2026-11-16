import { describe, expect, it } from 'vitest';
import type { TaskSnapshot } from '../shared/api';
import { mergeTaskSnapshot } from './taskState';

function snapshot(overrides: Partial<TaskSnapshot> = {}): TaskSnapshot {
  return {
    id: 'task-1', kind: 'video', intent: 'new', status: 'queued', stage: null,
    state_revision: 1, event_seq: 1, cursor: 'cursor', instance_epoch: '00000000-0000-4000-8000-000000000003',
    attempt_no: 0, progress: { stage: null, observed_at: '2026-11-16T00:00:00Z' },
    deadline_at: '2026-11-16T02:00:00Z', cancel_requested_at: null, result: null,
    error: null, draft_summary: null, allowed_actions: ['cancel'], unknown_call_count: 0,
    ...overrides,
  };
}

describe('task snapshot monotonic merge', () => {
  it('accepts a higher revision in the same epoch', () => {
    const result = mergeTaskSnapshot(snapshot(), snapshot({ state_revision: 2, status: 'running' }));
    expect(result.accepted).toBe(true);
    expect(result.snapshot.status).toBe('running');
    expect(result.recovered).toBe(false);
  });

  it('drops an older revision and duplicate revision', () => {
    const current = snapshot({ state_revision: 4, status: 'running' });
    expect(mergeTaskSnapshot(current, snapshot({ state_revision: 3 })).snapshot).toBe(current);
    expect(mergeTaskSnapshot(current, snapshot({ state_revision: 4, status: 'queued' })).snapshot).toBe(current);
  });

  it('accepts later non-critical progress at the same revision without regressing task state', () => {
    const current = snapshot({
      state_revision: 4,
      status: 'running',
      stage: 'acquire',
      progress: { stage: 'acquire', observed_at: '2026-11-16T00:00:00Z' },
    });
    const incoming = snapshot({
      state_revision: 4,
      status: 'queued',
      stage: null,
      progress: { stage: 'download', observed_at: '2026-11-16T00:00:01Z' },
    });

    const result = mergeTaskSnapshot(current, incoming);

    expect(result.accepted).toBe(true);
    expect(result.snapshot.status).toBe('running');
    expect(result.snapshot.stage).toBe('acquire');
    expect(result.snapshot.progress).toEqual(incoming.progress);
  });

  it('ignores same-revision progress that is not newer', () => {
    const current = snapshot({
      state_revision: 4,
      progress: { stage: 'download', observed_at: '2026-11-16T00:00:01Z' },
    });
    const incoming = snapshot({
      state_revision: 4,
      progress: { stage: 'acquire', observed_at: '2026-11-16T00:00:00Z' },
    });

    const result = mergeTaskSnapshot(current, incoming);

    expect(result.accepted).toBe(false);
    expect(result.snapshot).toBe(current);
  });

  it('accepts a newer epoch and marks recovery', () => {
    const result = mergeTaskSnapshot(snapshot({ state_revision: 8 }), snapshot({ instance_epoch: '00000000-0000-4000-8000-000000000004', state_revision: 1 }));
    expect(result.snapshot.instance_epoch).toBe('00000000-0000-4000-8000-000000000004');
    expect(result.recovered).toBe(true);
  });

  it('drops an older epoch even if its revision is higher', () => {
    const current = snapshot({ instance_epoch: '00000000-0000-4000-8000-000000000004', state_revision: 1 });
    const result = mergeTaskSnapshot(current, snapshot({ instance_epoch: '00000000-0000-4000-8000-000000000003', state_revision: 99 }), new Set(['00000000-0000-4000-8000-000000000003']));
    expect(result.snapshot).toBe(current);
    expect(result.accepted).toBe(false);
  });
});
