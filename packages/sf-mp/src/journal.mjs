// The lane's journal (CONTRACT.md §2–4). One slot per org: `open-<orgId>.json` exists
// exactly while an operation on that org is open, and its existence blocks every other write
// there. Settled operations are kept one file each, written before the slot goes away.
import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { existsSync, readdirSync, rmSync } from 'node:fs';
import { hostname } from 'node:os';
import { join } from 'node:path';
import { publishJsonExclusive, readJson, writeJsonAtomic } from './fsx.mjs';

export const STATES = ['intent', 'submitting', 'dispatched', 'settled-success', 'settled-failed', 'unresolved', 'reconciled-success', 'reconciled-failed'];
export const SETTLED = new Set(['settled-success', 'settled-failed', 'reconciled-success', 'reconciled-failed']);

export const journalDir = (root) => join(root, '.mp', 'journal');
export const slotPath = (root, orgId) => join(journalDir(root), `open-${orgId}.json`);
export const recordPath = (root, opId) => join(journalDir(root), `${opId}.json`);

/** Sortable and unique: a UTC timestamp plus a random suffix. */
export const newOpId = () => `${new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z')}-${randomUUID().slice(0, 8)}`;

const processStart = new Date(Date.now() - process.uptime() * 1000).toISOString();
export const thisHolder = () => ({ pid: process.pid, host: hostname(), startedAt: processStart });

export function transition(record, state, extra = {}) {
  return { ...record, ...extra, state, transitions: [...(record.transitions ?? []), { state, at: new Date().toISOString() }] };
}

/** The org's open operation: undefined, { record }, or { unreadable } (which blocks just the same). */
export function readSlot(root, orgId) {
  const path = slotPath(root, orgId);
  if (!existsSync(path)) return undefined;
  try {
    const record = readJson(path);
    if (typeof record?.opId !== 'string' || !STATES.includes(record.state)) throw new Error('it has no operation ID or a known state');
    return { record, path };
  } catch (error) {
    return { unreadable: error.message, path };
  }
}

/** Publishes the intent record as the org's slot. False when another operation holds it. */
export const takeSlot = (root, orgId, record) => publishJsonExclusive(slotPath(root, orgId), record);

/** Replaces the slot's record, after checking that the slot still holds this operation. */
export function updateSlot(root, orgId, record) {
  const current = readSlot(root, orgId);
  if (current?.record?.opId !== record.opId) {
    throw new Error(`operation ${record.opId} no longer holds the slot for ${orgId}; it was settled or replaced elsewhere`);
  }
  writeJsonAtomic(slotPath(root, orgId), record);
  return record;
}

/**
 * Settles an operation: the settled record is written exclusively first, then the slot goes.
 * Repeating it after an interruption is harmless.
 */
export function settle(root, orgId, record) {
  const current = readSlot(root, orgId);
  if (current && current.record?.opId !== record.opId) {
    throw new Error(`operation ${record.opId} no longer holds the slot for ${orgId}`);
  }
  const path = recordPath(root, record.opId);
  if (!publishJsonExclusive(path, record)) {
    const existing = readJson(path);
    if (existing.opId !== record.opId) throw new Error(`${path} belongs to another operation`);
  }
  if (current) rmSync(slotPath(root, orgId), { force: true });
  return record;
}

/** Frees a slot that recorded no org write (a retrieve), after checking it's still this one. */
export function releaseSlot(root, orgId, opId) {
  const current = readSlot(root, orgId);
  if (current?.record?.opId === opId) rmSync(slotPath(root, orgId), { force: true });
}

/** Settled operations, newest first. */
export function settledRecords(root) {
  const dir = journalDir(root);
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((name) => name.endsWith('.json') && !name.startsWith('open-') && !name.startsWith('.'))
    .sort()
    .reverse()
    .map((name) => {
      try {
        return readJson(join(dir, name));
      } catch (error) {
        return { opId: name.replace(/\.json$/, ''), unreadable: error.message };
      }
    });
}

/** Every open slot in this journal: [{ orgId, record | unreadable }]. */
export function openSlots(root) {
  const dir = journalDir(root);
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((name) => /^open-00D[0-9A-Za-z]{12}\.json$/.test(name))
    .map((name) => ({ orgId: name.slice(5, 20), ...readSlot(root, name.slice(5, 20)) }));
}

/** 'running', 'stopped' or 'unknown' (another machine, or no way to tell). */
export function holderState(holder) {
  if (!holder?.pid || holder.host !== hostname()) return 'unknown';
  try {
    process.kill(holder.pid, 0);
  } catch (error) {
    return error.code === 'EPERM' ? 'running' : 'stopped';
  }
  if (holder.pid === process.pid) return 'running';
  // The PID is alive; make sure it's the same process and not a reused PID.
  try {
    const started = execFileSync('ps', ['-o', 'lstart=', '-p', String(holder.pid)], { encoding: 'utf8' }).trim();
    const delta = Math.abs(new Date(started).getTime() - new Date(holder.startedAt).getTime());
    return Number.isNaN(delta) ? 'unknown' : delta <= 5000 ? 'running' : 'stopped';
  } catch {
    return 'unknown';
  }
}
