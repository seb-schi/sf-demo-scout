// A component's files and their hash. Files are keyed by their path relative to the folder of
// the component's metadata file, so the same component hashes the same in the project, in a
// staging copy and in a retrieve's output, wherever each keeps its package folder.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, relative, sep } from 'node:path';

export const HASH_POLICY = 'files-v1: sha256 over sorted relative paths and bytes, CRLF read as LF';

const toPosix = (path) => path.split(sep).join('/');

export const normalizeBytes = (bytes) => Buffer.from(Buffer.from(bytes).toString('latin1').replace(/\r\n/g, '\n'), 'latin1');

/** [{ key, path }] for a SourceComponent: its metadata file plus every content file. */
export function componentFiles(component) {
  const anchor = component.xml ?? component.content;
  const base = dirname(anchor);
  const paths = new Set([component.xml, ...(component.content ? component.walkContent() : [])].filter(Boolean));
  return [...paths]
    .map((path) => ({ key: toPosix(relative(base, path)), path }))
    .sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
}

export const readFiles = (files) => files.map(({ key, path }) => ({ key, path, bytes: readFileSync(path) }));

export function hashFiles(entries) {
  const hash = createHash('sha256');
  for (const { key, bytes } of [...entries].sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0))) {
    const body = normalizeBytes(bytes);
    hash.update(`${key}\n${body.length}\n`);
    hash.update(body);
    hash.update('\n');
  }
  return hash.digest('hex');
}
