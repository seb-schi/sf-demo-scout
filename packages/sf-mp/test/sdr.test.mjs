// The host's real source-deploy-retrieve, offline: what each v1 type resolves to and what its
// converted deploy payload holds (a fake transport is fine; a fake conversion isn't).
// Plus the comparison policies and the retrieve-result mapping.
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { after, test } from 'node:test';
import { addApex, addField, addLwc, cleanupTemps, entry, makeKit, temp, write, APEX_META } from './helpers.mjs';

const { sdr } = await import('../src/host.mjs');
const { realRuntime, mapRetrieve } = await import('../src/runtime.mjs');
const { compareWithOrg, candidateProblems, parseEntries } = await import('../src/types.mjs');
const { xmlWithin } = await import('../src/xml.mjs');
const { hashFiles } = await import('../src/hash.mjs');

after(cleanupTemps);

const walk = (dir) => readdirSync(dir).flatMap((name) => (statSync(join(dir, name)).isDirectory() ? walk(join(dir, name)) : [join(dir, name)]));

async function convert(root, keys) {
  const { componentSet } = await realRuntime().resolveSource(root, [join(root, 'force-app')], keys.map(entry), '64.0');
  const out = temp('sf-mp-convert-');
  const { MetadataConverter } = sdr();
  await new MetadataConverter().convert(componentSet, 'metadata', { type: 'directory', outputDirectory: out, genUniqueDir: false });
  return { componentSet, out, files: walk(out).map((path) => relative(out, path)).sort() };
}

// The container still carries the local object file's settings; the deploy changes only what
// package.xml names, so they're ignored. A live trial proved it (a stale local object description
// didn't revert the org's). Page action overrides are untested.
test('a CustomField deploys as its child alone: package.xml names only the field, never the object', async () => {
  const { root } = await makeKit({ register: false, commit: false });
  write(root, 'force-app/main/default/objects/Thing__c/Thing__c.object-meta.xml', '<?xml version="1.0" encoding="UTF-8"?>\n<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">\n    <label>Thing</label>\n    <pluralLabel>Things</pluralLabel>\n    <sharingModel>ReadWrite</sharingModel>\n    <description>object settings that must not travel</description>\n</CustomObject>\n');
  addField(root, 'Thing__c', 'Note__c', 'Text');
  addField(root, 'Thing__c', 'Other__c', 'Text');
  const { componentSet, out, files } = await convert(root, ['CustomField:Thing__c.Note__c']);
  assert.deepEqual(componentSet.getSourceComponents().toArray().map((c) => `${c.type.name}:${c.fullName}`), ['CustomField:Thing__c.Note__c']);
  assert.deepEqual(files, ['objects/Thing__c.object', 'package.xml']);
  const object = readFileSync(join(out, 'objects/Thing__c.object'), 'utf8');
  assert.match(object, /<fullName>Note__c<\/fullName>/);
  assert.doesNotMatch(object, /Other__c/, 'no sibling field travels');
  const manifest = readFileSync(join(out, 'package.xml'), 'utf8');
  assert.match(manifest, /<members>Thing__c\.Note__c<\/members>\s*<name>CustomField<\/name>/);
  assert.doesNotMatch(manifest, /<name>CustomObject<\/name>/, 'the object itself is not a member');
  assert.equal((manifest.match(/<members>/g) ?? []).length, 1);
});

test('an LWC bundle deploys its deployable files only: tests and ignored files stay out', async () => {
  const { root } = await makeKit({ register: false, commit: false });
  addLwc(root, 'card', { 'card.css': 'p {}\n', '__tests__/card.test.js': 'test("x", () => {});\n', 'jsconfig.json': '{}\n' });
  const { found } = await realRuntime().resolveSource(root, [join(root, 'force-app')], [entry('LightningComponentBundle:card')], '64.0');
  assert.deepEqual(found.get('LightningComponentBundle:card').files.map((f) => f.key), ['card.css', 'card.html', 'card.js', 'card.js-meta.xml']);
  const { files } = await convert(root, ['LightningComponentBundle:card']);
  assert.deepEqual(files, ['lwc/card/card.css', 'lwc/card/card.html', 'lwc/card/card.js', 'lwc/card/card.js-meta.xml', 'package.xml']);
});

test('an Apex class resolves to its body and meta file, and converts to exactly those', async () => {
  const { root } = await makeKit({ register: false, commit: false });
  addApex(root, 'Foo');
  addApex(root, 'Bar');
  const { found } = await realRuntime().resolveSource(root, [join(root, 'force-app')], [entry('ApexClass:Foo')], '64.0');
  assert.deepEqual([...found.keys()], ['ApexClass:Foo']);
  assert.deepEqual(found.get('ApexClass:Foo').files.map((f) => f.key), ['Foo.cls', 'Foo.cls-meta.xml']);
  const { files } = await convert(root, ['ApexClass:Foo']);
  assert.deepEqual(files, ['classes/Foo.cls', 'classes/Foo.cls-meta.xml', 'package.xml']);
});

test('a requested component that doesn\'t resolve is simply absent from the set, so the deploy checks every one', async () => {
  const { root } = await makeKit({ register: false, commit: false });
  addApex(root, 'Foo');
  const { found } = await realRuntime().resolveSource(root, [join(root, 'force-app')], [entry('ApexClass:Foo'), entry('ApexClass:Ghost')], '64.0');
  assert.deepEqual([...found.keys()], ['ApexClass:Foo']);
});

test('XML structural comparison: formatting and namespaces don\'t count; values, attributes and order do', () => {
  const candidate = '<?xml version="1.0"?>\n<CustomField xmlns="http://soap.sforce.com/2006/04/metadata"><fullName>Note__c</fullName><label>Note</label><type>Text</type></CustomField>';
  const org = '<?xml version="1.0" encoding="UTF-8"?>\n<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">\n    <fullName>Note__c</fullName>\n    <externalId>false</externalId>\n    <label>Note</label>\n    <length>80</length>\n    <type>Text</type>\n</CustomField>\n';
  assert.equal(xmlWithin(candidate, org), true, 'org defaults are allowed');
  assert.equal(xmlWithin(candidate.replace('<label>Note</label>', '<label>Notes</label>'), org), false);
  assert.equal(xmlWithin(candidate.replace('<label>Note</label>', '<label> Note</label>'), org), false, 'no trimming');
  assert.equal(xmlWithin('<a:Root xmlns:a="u"><a:x>1</a:x></a:Root>', '<Root xmlns="u"><x>1</x></Root>'), true, 'prefixes ignored');
  assert.equal(xmlWithin('<R><v>1</v><v>2</v></R>', '<R><v>1</v><v>2</v></R>'), true);
  assert.equal(xmlWithin('<R><v>2</v><v>1</v></R>', '<R><v>1</v><v>2</v></R>'), false, 'order of same-named siblings counts');
  assert.equal(xmlWithin('<R><e k="1">x</e></R>', '<R><e k="2">x</e></R>'), false, 'attributes count');
});

test('compareWithOrg: code bytes exact apart from line endings; XML structural; file sets must match', () => {
  const candidate = [{ key: 'Foo.cls', bytes: Buffer.from('class Foo {\n}\n') }, { key: 'Foo.cls-meta.xml', bytes: Buffer.from(APEX_META) }];
  const crlf = [{ key: 'Foo.cls', bytes: Buffer.from('class Foo {\r\n}\r\n') }, { key: 'Foo.cls-meta.xml', bytes: Buffer.from(APEX_META.replace(/\n {4}/g, '\n\t')) }];
  assert.equal(compareWithOrg(candidate, crlf).matches, true);
  assert.equal(compareWithOrg(candidate, [{ ...crlf[0], bytes: Buffer.from('class Foo { }\n') }, crlf[1]]).matches, false);
  assert.match(compareWithOrg(candidate, [crlf[0]]).differences.join(), /Foo\.cls-meta\.xml is missing from the org's copy/);
  assert.equal(hashFiles(candidate) === hashFiles([candidate[1], candidate[0]]), true, 'the hash ignores order');
});

test('candidateProblems: the code-v1 pair, field types and bundle drops', () => {
  const apex = entry('ApexClass:Foo');
  assert.match(candidateProblems(apex, [{ key: 'Foo.cls', bytes: Buffer.from('') }]).join(), /needs exactly its body and its meta file/);
  const field = entry('CustomField:Thing__c.Kind__c');
  const xml = (type) => Buffer.from(`<CustomField xmlns="x"><fullName>Kind__c</fullName><type>${type}</type></CustomField>`);
  assert.deepEqual(candidateProblems(field, [{ key: 'Kind__c.field-meta.xml', bytes: xml('Text') }], [{ key: 'Kind__c.field-meta.xml', bytes: xml('Text') }]), []);
  assert.match(candidateProblems(field, [{ key: 'Kind__c.field-meta.xml', bytes: xml('MultiselectPicklist') }]).join(), /is a picklist/);
  assert.match(candidateProblems(field, [{ key: 'Kind__c.field-meta.xml', bytes: xml('Text') }], [{ key: 'Kind__c.field-meta.xml', bytes: xml('Picklist') }]).join(), /picklist in the org/);
});

test('parseEntries: Type:Name only, deduplicated, enabled types, within the ceiling', () => {
  assert.deepEqual(parseEntries(['ApexClass:A', 'ApexClass:A']).entries.map((e) => e.key), ['ApexClass:A']);
  assert.match(parseEntries(['ApexClass']).problems.join(), /isn't Type:Name/);
  assert.match(parseEntries([]).problems.join(), /name at least one/);
  assert.match(parseEntries(['ValidationRule:Thing__c.R']).problems.join(), /isn't switched on in v1 yet/);
});

test('mapRetrieve: present, confirmed absent from "cannot be found", unknown otherwise', async () => {
  const { root } = await makeKit({ register: false, commit: false });
  addApex(root, 'Here');
  const { componentSet } = await realRuntime().resolveSource(root, [join(root, 'force-app')], [entry('ApexClass:Here')], '64.0');
  const result = {
    components: componentSet,
    response: { fileProperties: [{ type: 'ApexClass', fullName: 'Here', lastModifiedByName: 'Ada', lastModifiedDate: '2026-10-18T01:00:00.000Z' }] },
    getFileResponses: () => [
      { type: 'ApexClass', fullName: 'Gone', state: 'Failed', error: "Entity of type 'ApexClass' named 'Gone' cannot be found" },
      { type: 'ApexClass', fullName: 'Odd', state: 'Failed', error: 'INVALID_SESSION_ID' },
    ],
  };
  const mapped = mapRetrieve(result, [entry('ApexClass:Here'), entry('ApexClass:Gone'), entry('ApexClass:Odd'), entry('ApexClass:Silent')]);
  assert.equal(mapped.get('ApexClass:Here').state, 'present');
  assert.equal(mapped.get('ApexClass:Here').lastModifiedBy, 'Ada');
  assert.equal(mapped.get('ApexClass:Gone').state, 'confirmed-absent');
  assert.equal(mapped.get('ApexClass:Odd').state, 'unknown');
  assert.equal(mapped.get('ApexClass:Silent').state, 'unknown', 'missing output alone is not confirmed absence');
});

test('mapRetrieve: a bundle takes its newest file\'s who and when; a field doesn\'t borrow its object\'s', async () => {
  const { root } = await makeKit({ register: false, commit: false });
  addLwc(root, 'card');
  addField(root, 'Thing__c', 'Note__c', 'Text');
  const { componentSet } = await realRuntime().resolveSource(root, [join(root, 'force-app')], [entry('LightningComponentBundle:card'), entry('CustomField:Thing__c.Note__c')], '64.0');
  const result = {
    components: componentSet,
    response: { fileProperties: [
      { type: 'LightningComponentBundle', fullName: 'card/card.js', lastModifiedByName: 'Old', lastModifiedDate: '2026-10-01T00:00:00.000Z' },
      { type: 'LightningComponentBundle', fullName: 'card/card.html', lastModifiedByName: 'New', lastModifiedDate: '2026-10-18T00:00:00.000Z' },
      { type: 'CustomObject', fullName: 'Thing__c', lastModifiedByName: 'Object Person', lastModifiedDate: '2026-10-17T00:00:00.000Z' },
    ] },
    getFileResponses: () => [],
  };
  const mapped = mapRetrieve(result, [entry('LightningComponentBundle:card'), entry('CustomField:Thing__c.Note__c')]);
  assert.equal(mapped.get('LightningComponentBundle:card').lastModifiedBy, 'New');
  assert.equal(mapped.get('CustomField:Thing__c.Note__c').lastModifiedBy, undefined);
});
