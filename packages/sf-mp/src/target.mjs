// Which org a command targets, worked out offline the way the CLI does: the explicit flag,
// otherwise the configured default (SF_TARGET_ORG and the legacy variables, then the project's
// and the global config), then alias to username to the org ID in the local login file.
// Nothing is decrypted and no connection is made.
import { org15 } from './ids.mjs';

import { findSfProject } from './kit.mjs';

// The host's own token shapes (@salesforce/core util/sfdc): an opaque token starts with its
// org ID (15 to 18 characters); a JWT carries no org ID we can read without trusting it.
const OPAQUE_TOKEN = /^(00D\w{12,15})![.\w]*$/;
const JWT_TOKEN = /^eyJ[A-Za-z0-9+=_-]+\.[A-Za-z0-9+=_-]+\.[A-Za-z0-9+=_-]+$/;
const looksSecret = (value) => value.includes('!') || value.startsWith('eyJ');

export async function resolveTarget({ value, cwd, core }) {
  let source = 'flag';
  if (value === undefined) {
    source = 'default';
    // The project's own config lives at its root, wherever in the project the command runs.
    const aggregator = await core.ConfigAggregator.create({ projectPath: findSfProject(cwd) ?? cwd });
    value = aggregator.getPropertyValue('target-org');
  }
  if (typeof value !== 'string' || !value.trim()) {
    return { unresolved: source === 'flag' ? '--target-org has no value' : 'no --target-org and no default org is set' };
  }
  const token = OPAQUE_TOKEN.exec(value);
  if (token) return { orgId: org15(token[1]), label: 'an access token', source };
  if (JWT_TOKEN.test(value)) return { unresolved: 'the target is a JWT access token, whose org the guard can\'t tell', token: true };
  const state = await core.StateAggregator.getInstance();
  const username = state.aliases.resolveUsername(value);
  const auth = await state.orgs.read(username, false, false);
  const orgId = org15(auth?.orgId);
  if (!orgId) return { unresolved: looksSecret(value) ? 'the target looks like a token the guard can\'t read' : `there's no local login for ${value}`, token: looksSecret(value) };
  return { orgId, username, label: value === username ? username : `${value} (${username})`, source };
}
