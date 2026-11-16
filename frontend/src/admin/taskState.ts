import type { TaskSnapshot } from '../shared/api';

const terminalStatuses = new Set(['succeeded', 'failed', 'canceled']);

export function isTerminalStatus(status: string): boolean {
  return terminalStatuses.has(status);
}

export type SnapshotMergeResult = {
  snapshot: TaskSnapshot;
  accepted: boolean;
  recovered: boolean;
};

export function mergeTaskSnapshot(
  current: TaskSnapshot | null,
  incoming: TaskSnapshot,
  retiredEpochs: ReadonlySet<string> = new Set(),
): SnapshotMergeResult {
  if (!current) return { snapshot: incoming, accepted: true, recovered: false };

  if (incoming.instance_epoch !== current.instance_epoch && !retiredEpochs.has(incoming.instance_epoch)) {
    return { snapshot: incoming, accepted: true, recovered: true };
  }

  if (incoming.instance_epoch !== current.instance_epoch) {
    return { snapshot: current, accepted: false, recovered: false };
  }

  if (incoming.state_revision > current.state_revision) {
    return { snapshot: incoming, accepted: true, recovered: false };
  }

  if (incoming.state_revision === current.state_revision
    && Date.parse(incoming.progress.observed_at) > Date.parse(current.progress.observed_at)) {
    // 临时进度可以在不递增状态版本时前进，只更新进度字段，避免旧响应回退权威状态。
    return {
      snapshot: { ...current, progress: incoming.progress },
      accepted: true,
      recovered: false,
    };
  }

  return { snapshot: current, accepted: false, recovered: false };
}

export function mergeSnapshot(current: TaskSnapshot | null, incoming: TaskSnapshot): TaskSnapshot {
  return mergeTaskSnapshot(current, incoming).snapshot;
}
