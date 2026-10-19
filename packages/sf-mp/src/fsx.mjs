// Durable writes. A reader sees the old file or the new one, never a torn one, so a full disk
// or a crash mid-write can't leave a half-written journal record or registry.
import { randomBytes } from 'node:crypto';
import { closeSync, fsyncSync, linkSync, mkdirSync, openSync, readFileSync, renameSync, rmSync, writeSync } from 'node:fs';
import { basename, dirname, join } from 'node:path';

function writeTemp(target, data) {
  const dir = dirname(target);
  mkdirSync(dir, { recursive: true });
  const tmp = join(dir, `.${basename(target)}.${process.pid}.${randomBytes(4).toString('hex')}.tmp`);
  const fd = openSync(tmp, 'wx');
  try {
    const buffer = Buffer.isBuffer(data) ? data : Buffer.from(data);
    let offset = 0;
    while (offset < buffer.length) offset += writeSync(fd, buffer, offset);
    fsyncSync(fd);
  } catch (error) {
    closeSync(fd);
    rmSync(tmp, { force: true });
    throw error;
  }
  closeSync(fd);
  return tmp;
}

function syncDir(dir) {
  try {
    const fd = openSync(dir, 'r');
    try {
      fsyncSync(fd);
    } finally {
      closeSync(fd);
    }
  } catch {
    // Not every platform can fsync a directory; the rename itself is still atomic.
  }
}

/** Replaces target atomically: write a flushed temporary file, then rename it over target. */
export function writeAtomic(target, data) {
  const tmp = writeTemp(target, data);
  try {
    renameSync(tmp, target);
  } catch (error) {
    rmSync(tmp, { force: true });
    throw error;
  }
  syncDir(dirname(target));
}

/**
 * Publishes target complete or not at all, and only if it doesn't exist yet: the hard link
 * fails with EEXIST when another process got there first. Returns false in that case.
 */
export function publishExclusive(target, data) {
  const tmp = writeTemp(target, data);
  try {
    linkSync(tmp, target);
    return true;
  } catch (error) {
    if (error.code === 'EEXIST') return false;
    throw error;
  } finally {
    rmSync(tmp, { force: true });
    syncDir(dirname(target));
  }
}

const json = (value) => `${JSON.stringify(value, null, 2)}\n`;
export const writeJsonAtomic = (target, value) => writeAtomic(target, json(value));
export const publishJsonExclusive = (target, value) => publishExclusive(target, json(value));

/** Parses a JSON file; throws on a missing, unreadable or malformed file. */
export const readJson = (path) => JSON.parse(readFileSync(path, 'utf8'));
