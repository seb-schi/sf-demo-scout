// Structural XML comparison for read-backs: does the org's copy carry everything the candidate
// says? Formatting, the XML declaration, namespace declarations and prefixes don't count.
// Values, attributes and the order of same-named siblings do. The org may add elements the
// candidate leaves out (its defaults). Text is compared exactly: no trimming or coercion.
import { xmlParser } from './host.mjs';

export const XML_POLICY = 'xml-v1: candidate elements in order with equal values and attributes; org defaults allowed';

const localName = (name) => name.replace(/^[^:]+:/, '');

function normalize(nodes) {
  const out = [];
  for (const node of nodes ?? []) {
    const attrs = node[':@'] ?? {};
    const tag = Object.keys(node).find((key) => key !== ':@');
    if (tag === undefined || tag === '?xml' || tag === '#comment') continue;
    if (tag === '#text') {
      const text = String(node['#text']);
      if (text.trim() !== '') out.push({ text });
      continue;
    }
    const kept = {};
    for (const [name, value] of Object.entries(attrs)) {
      const bare = name.replace(/^@_/, '');
      if (bare === 'xmlns' || bare.startsWith('xmlns:')) continue;
      kept[localName(bare)] = String(value);
    }
    const raw = node[tag] ?? [];
    const leaf = !raw.some((child) => Object.keys(child).some((key) => key !== '#text' && key !== ':@' && key !== '#comment'));
    if (leaf) {
      // A leaf keeps its exact text, empty or not: <description/> means "cleared".
      out.push({ tag: localName(tag), attrs: kept, leaf: true, value: raw.filter((child) => '#text' in child).map((child) => String(child['#text'])).join(''), children: [] });
    } else {
      out.push({ tag: localName(tag), attrs: kept, leaf: false, children: normalize(raw) });
    }
  }
  return out;
}

export function parseXml(text) {
  const { XMLParser } = xmlParser();
  const parser = new XMLParser({
    preserveOrder: true,
    ignoreAttributes: false,
    attributeNamePrefix: '@_',
    trimValues: false,
    parseTagValue: false,
    parseAttributeValue: false,
    commentPropName: '#comment',
    processEntities: true,
  });
  return normalize(parser.parse(String(text)));
}

const attrsWithin = (candidate, org) => Object.entries(candidate).every(([name, value]) => org[name] === value);

/** True when every candidate node appears in org, in order among same-named siblings. */
export function within(candidate, org) {
  const texts = org.filter((node) => node.text !== undefined).map((node) => node.text);
  const cursor = new Map();
  for (const node of candidate) {
    if (node.text !== undefined) {
      if (!texts.includes(node.text)) return false;
      continue;
    }
    const siblings = org.filter((other) => other.tag === node.tag);
    // The API omits empty elements; an empty element with attributes (an LWC <property/>) still counts.
    if (node.leaf && node.value === '' && !Object.keys(node.attrs).length && !siblings.length) continue;
    const same = (other) => attrsWithin(node.attrs, other.attrs) && (node.leaf ? other.leaf && other.value === node.value : !other.leaf && within(node.children, other.children));
    let i = cursor.get(node.tag) ?? 0;
    while (i < siblings.length && !same(siblings[i])) i++;
    if (i === siblings.length) return false;
    cursor.set(node.tag, i + 1);
  }
  return true;
}

export const xmlWithin = (candidateText, orgText) => within(parseXml(candidateText), parseXml(orgText));

/** The text of the first top-level-child element named tag, e.g. a CustomField's <type>. */
export function childText(xmlText, tag) {
  const [root] = parseXml(xmlText).filter((node) => node.tag);
  return root?.children.find((node) => node.tag === tag)?.value;
}

export const hasChild = (xmlText, tag) => {
  const [root] = parseXml(xmlText).filter((node) => node.tag);
  return Boolean(root?.children.some((node) => node.tag === tag));
};
