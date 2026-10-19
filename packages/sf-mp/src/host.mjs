// The host CLI's own libraries. The kit has no npm dependencies of its own: it uses the
// @salesforce/core, source-deploy-retrieve and oclif copies of the `sf` that loaded it, so the
// Lifecycle singleton is the one SDR emits on and deploys behave like the CLI's.
import { realpathSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { pathToFileURL } from 'node:url';

let root;
const loaded = new Map();

/** The CLI's install folder: SF_MP_CLI_ROOT (tests), the hook's config.root, or the running bin/run.js. */
export function cliRoot() {
  root ??= process.env.SF_MP_CLI_ROOT || dirname(dirname(realpathSync(process.argv[1])));
  return root;
}

export function setCliRoot(path) {
  if (path && path !== root) {
    root = path;
    loaded.clear();
  }
}

export function host(name) {
  if (!loaded.has(name)) loaded.set(name, createRequire(join(cliRoot(), 'package.json'))(name));
  return loaded.get(name);
}

/** For the host's ES modules (sf-plugins-core uses top-level await, so require can't load it). */
export async function hostImport(name) {
  const path = createRequire(join(cliRoot(), 'package.json')).resolve(name);
  return import(pathToFileURL(path).href);
}

export const core = () => host('@salesforce/core');
export const sdr = () => host('@salesforce/source-deploy-retrieve');
export const yaml = () => host('yaml');
export const xmlParser = () => host('fast-xml-parser');
