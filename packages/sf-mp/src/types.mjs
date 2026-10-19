// The metadata types the lane deploys, each with a versioned contract: what its scope is, how
// it's compared and what proves it complete (CONTRACT.md §4 rule 9). The steward route (§5)
// adds an allow-list of further types, each switched on after its own live trial, with checks
// on the effects a named file can carry beyond itself. Everything else is refused.
import { CEILING } from './guard.mjs';
import { normalizeBytes } from './hash.mjs';
import { childText, hasChild, parseXml, xmlWithin } from './xml.mjs';

const PICKLISTS = new Set(['Picklist', 'MultiselectPicklist']);

export const TYPES = new Map([
  ['ApexClass', { enabled: true, policy: 'code-v1', files: 'the class body and its meta file' }],
  ['ApexTrigger', { enabled: false, policy: 'code-v1', files: 'the trigger body and its meta file', off: 'waits for its contract trial' }],
  ['LightningComponentBundle', { enabled: true, policy: 'bundle-v1', files: 'every deployable bundle file' }],
  ['CustomField', { enabled: true, policy: 'field-v1', files: 'the field file only, never the object file' }],
  ['ValidationRule', { enabled: false, policy: 'xml-v1', files: 'the rule file only', off: 'waits for its contract trial' }],
]);

// The steward route's allow-list (`--steward`). Freshness on the whole retrieved component, the
// staged named paths and a read-back that must match carry these; the policies below refuse the
// effects that reach past the file itself (page assignments, activation).
export const STEWARD_TYPES = new Map([
  ['CustomObject', { enabled: true, policy: 'object-v1', files: 'the object file only, never its children' }],
  ['PermissionSet', { enabled: true, policy: 'xml-v1', files: 'the permission set file (deployed in full)' }],
  ['CustomTab', { enabled: true, policy: 'xml-v1', files: 'the tab file' }],
  ['Layout', { enabled: true, policy: 'xml-v1', files: 'the layout file' }],
  ['Flow', { enabled: false, policy: 'flow-v1', files: 'one flow version, inactive', off: 'waits for its trial' }],
  ['CustomApplication', { enabled: false, policy: 'object-v1', files: 'the app file', off: 'waits for its trial' }],
]);

const enabledList = (map) => [...map].filter(([, s]) => s.enabled).map(([t]) => t).join(', ');

/** Parses `Type:Name` entries: { entries: [{ type, name, key, steward }], problems: [] }. */
export function parseEntries(values = [], { steward = false } = {}) {
  const problems = [];
  const entries = [];
  const seen = new Set();
  for (const raw of values) {
    const value = String(raw).trim();
    const at = value.indexOf(':');
    const type = at > 0 ? value.slice(0, at) : '';
    const name = at > 0 ? value.slice(at + 1) : '';
    if (!type || !name) {
      problems.push(`"${value}" isn't Type:Name`);
      continue;
    }
    if (value.includes('*')) {
      problems.push(`"${value}" is a wildcard; name each component`);
      continue;
    }
    const lane = TYPES.get(type);
    const stewarded = steward && !lane ? STEWARD_TYPES.get(type) : undefined;
    const spec = lane ?? stewarded;
    if (!spec) {
      problems.push(steward
        ? `${type} isn't enabled (the lane deploys ${enabledList(TYPES)}; the steward route adds ${enabledList(STEWARD_TYPES)})`
        : `${type} isn't enabled in v1 (v1 deploys ${enabledList(TYPES)}; the steward route, --steward, adds ${enabledList(STEWARD_TYPES)})`);
    } else if (!spec.enabled) problems.push(`${type} isn't switched on ${lane ? 'in v1 ' : 'on the steward route '}yet: it ${spec.off}`);
    const key = `${type}:${name}`;
    if (seen.has(key)) continue;
    seen.add(key);
    entries.push({ type, name, key, steward: Boolean(stewarded) });
  }
  if (!values.length) problems.push('name at least one component with --metadata Type:Name');
  if (entries.length > CEILING) problems.push(`${entries.length} components is over the ceiling of ${CEILING}`);
  return { entries, problems };
}

const byKey = (files) => new Map(files.map((file) => [file.key, file.bytes]));
const isXml = (key) => key.endsWith('.xml');
// Salesforce stores an Apex body without its trailing whitespace (seen live: a final newline is stripped on save), so
// an editor's final newline is no difference. Everything else in a code body still compares exactly.
const isApexBody = (key) => key.endsWith('.cls') || key.endsWith('.trigger');
const trimEnd = (bytes) => Buffer.from(normalizeBytes(bytes).toString('latin1').replace(/[ \t\n]+$/, ''), 'latin1');
const sameCode = (key, a, b) => (isApexBody(key) ? trimEnd(a).equals(trimEnd(b)) : normalizeBytes(a).equals(normalizeBytes(b)));

/** Does the org's copy carry the candidate? { matches, differences }. */
export function compareWithOrg(candidateFiles, orgFiles) {
  const candidate = byKey(candidateFiles);
  const org = byKey(orgFiles ?? []);
  const differences = [];
  for (const key of candidate.keys()) if (!org.has(key)) differences.push(`${key} is missing from the org's copy`);
  for (const key of org.keys()) if (!candidate.has(key)) differences.push(`${key} is in the org's copy but not the candidate`);
  for (const [key, bytes] of candidate) {
    if (!org.has(key)) continue;
    const same = isXml(key) ? xmlWithin(bytes.toString('utf8'), org.get(key).toString('utf8')) : sameCode(key, bytes, org.get(key));
    if (!same) differences.push(`${key} differs`);
  }
  return { matches: differences.length === 0, differences };
}

const fieldXml = (files) => files.find((file) => file.key.endsWith('.field-meta.xml'))?.bytes.toString('utf8');
const metaXml = (files) => files?.find((file) => file.key.endsWith('-meta.xml'))?.bytes.toString('utf8');

/** The non-default action overrides of an object or app file, as comparable signatures. */
export function pageAssignments(text) {
  if (!text) return [];
  const found = [];
  const walk = (nodes) => {
    for (const node of nodes) {
      if (node.leaf || node.text !== undefined) continue;
      if (node.tag === 'actionOverrides' || node.tag === 'profileActionOverrides') {
        const fields = Object.fromEntries(node.children.filter((child) => child.leaf).map((child) => [child.tag, child.value]));
        if ((fields.type ?? 'Default') !== 'Default') found.push(`${node.tag}:${JSON.stringify(Object.entries(fields).sort())}`);
        continue;
      }
      walk(node.children);
    }
  };
  walk(parseXml(text));
  return found.sort();
}

/** Problems with deploying this candidate over the org's current copy (undefined when absent). The effect bridge
 *  names the policy for a type outside both maps (scripts/effects.mjs); the lane never does. */
export function candidateProblems(entry, candidateFiles, orgFiles, policy = (TYPES.get(entry.type) ?? STEWARD_TYPES.get(entry.type))?.policy) {
  const problems = [];
  if (policy === 'field-v1') {
    const mine = fieldXml(candidateFiles);
    const theirs = orgFiles && fieldXml(orgFiles);
    const myType = mine && childText(mine, 'type');
    if (!mine) problems.push(`${entry.key} has no field file`);
    else if (PICKLISTS.has(myType) || hasChild(mine, 'valueSet')) problems.push(`${entry.key} is a picklist, which is owner-only and waits for the owner route`);
    if (theirs) {
      const orgType = childText(theirs, 'type');
      if (PICKLISTS.has(orgType) || hasChild(theirs, 'valueSet')) problems.push(`${entry.key} is a picklist in the org, which is owner-only`);
      else if (myType && orgType && myType !== orgType) problems.push(`${entry.key} would change type from ${orgType} to ${myType}; v1 leaves type changes to the steward`);
    }
  }
  if (policy === 'bundle-v1' && orgFiles) {
    const mine = new Set(candidateFiles.map((file) => file.key));
    const dropped = orgFiles.map((file) => file.key).filter((key) => !mine.has(key));
    if (dropped.length) problems.push(`${entry.key} would drop ${dropped.join(', ')} from the org's bundle; v1 doesn't delete`);
  }
  if (policy === 'object-v1') {
    const mine = pageAssignments(metaXml(candidateFiles));
    const theirs = pageAssignments(metaXml(orgFiles));
    if (mine.length !== theirs.length || mine.some((sig, i) => sig !== theirs[i])) {
      problems.push(`${entry.key} would change which pages or overrides users get (its non-default action overrides); assign pages in Setup`);
    }
  }
  if (policy === 'flow-v1') {
    const status = childText(metaXml(candidateFiles) ?? '', 'status');
    if (status === 'Active') problems.push(`${entry.key} is an active flow version; the steward route delivers inactive versions, and activation stays in Setup`);
  }
  if (policy === 'code-v1') {
    const keys = candidateFiles.map((file) => file.key);
    if (keys.length !== 2 || !keys.some((key) => key.endsWith('-meta.xml'))) problems.push(`${entry.key} needs exactly its body and its meta file`);
  }
  return problems;
}
