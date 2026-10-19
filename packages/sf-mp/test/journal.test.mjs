// The slot: one per org, taken by exactly one of several racing processes; published complete;
// unreadable slots block; settling can be repeated after an interruption.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { after, test } from 'node:test';
import { pathToFileURL } from 'node:url';
import { cleanupTemps, ORG15, temp, write } from './helpers.mjs';

const { holderState, readSlot, settle, settledRecords, slotPath, takeSlot, thisHolder, transition, updateSlot, journalDir } = await import('../src/journal.mjs');

after(cleanupTemps);

const journal = pathToFileURL(join(import.meta.dirname, '..', 'src', 'journal.mjs')).href;

function race(root, n) {
  const script = `const { takeSlot } = await import(${JSON.stringify(journal)}); const won = takeSlot(${JSON.stringify(root)}, ${JSON.stringify(ORG15)}, { schema: 1, opId: 'op-' + process.pid, state: 'intent', transitions: [] }); process.stdout.write(won ? 'won' : 'lost');`;
  return Promise.all(
    Array.from({ length: n }, () => new Promise((done, fail) => {
      const child = spawn(process.execPath, ['--input-type=module', '-e', script], { stdio: ['ignore', 'pipe', 'inherit'] });
      let out = '';
      child.stdout.on('data', (chunk) => (out += chunk));
      child.on('exit', (code) => (code === 0 ? done(out) : fail(new Error(`child exited ${code}`))));
    }))
  );
}

test('eight processes race for one org\'s slot: exactly one gets it, and it is complete', async () => {
  const root = temp();
  const results = await race(root, 8);
  assert.equal(results.filter((r) => r === 'won').length, 1, results.join());
  const slot = readSlot(root, ORG15);
  assert.match(slot.record.opId, /^op-\d+$/);
  assert.deepEqual(readdirSync(journalDir(root)).filter((name) => name.endsWith('.tmp')), [], 'no temporary files left behind');
});

test('a slot that exists but is malformed still blocks', () => {
  const root = temp();
  write(root, `.mp/journal/open-${ORG15}.json`, '');
  assert.ok(readSlot(root, ORG15).unreadable);
  assert.equal(takeSlot(root, ORG15, { opId: 'next', state: 'intent' }), false);
});

test('updates check the operation still holds the slot; settling twice is harmless', () => {
  const root = temp();
  let record = { schema: 1, opId: 'mine', state: 'intent', transitions: [] };
  assert.equal(takeSlot(root, ORG15, record), true);
  record = transition(record, 'submitting');
  updateSlot(root, ORG15, record);
  assert.throws(() => updateSlot(root, ORG15, { ...record, opId: 'someone-else' }), /no longer holds the slot/);
  const settled = transition(record, 'settled-success');
  settle(root, ORG15, settled);
  settle(root, ORG15, settled);
  assert.equal(readSlot(root, ORG15), undefined);
  assert.equal(settledRecords(root).length, 1);
  assert.throws(() => updateSlot(root, ORG15, settled), /no longer holds the slot/);
});

test('an interrupted settle (record written, slot still there) finishes on the next try', () => {
  const root = temp();
  const record = { schema: 1, opId: 'half', state: 'intent', transitions: [] };
  takeSlot(root, ORG15, record);
  write(root, '.mp/journal/half.json', JSON.stringify(transition(record, 'settled-failed')));
  settle(root, ORG15, transition(record, 'settled-failed'));
  assert.equal(readSlot(root, ORG15), undefined);
});

test('holderState: this process is running; a dead PID is stopped; another host is unknown', () => {
  assert.equal(holderState(thisHolder()), 'running');
  assert.equal(holderState({ ...thisHolder(), pid: 999999 }), 'stopped');
  assert.equal(holderState({ ...thisHolder(), host: 'another-machine' }), 'unknown');
  assert.equal(holderState(undefined), 'unknown');
  assert.equal(slotPath('/r', ORG15), `/r/.mp/journal/open-${ORG15}.json`);
});
