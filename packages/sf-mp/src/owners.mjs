// The ownership map: `.mp/owners.yaml`, `components: { "Type:Name": owner }`. A listed
// component needs its owner running the lane, or the owner's recorded approval.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { yaml } from './host.mjs';

export const OWNERS_TEMPLATE = `# Who owns which component in the common org (sf-mp).
# A component listed here is deployed only when its owner runs the lane, or with
# \`sf mp deploy ... --approved-by <owner>\` recording the owner's yes.
# Use the names people have in Git (git config user.name). "Type:*" covers a whole type.
components: {}
#  ApexClass:PaymentService: Ada Lovelace
#  LightningComponentBundle:*: Grace Hopper
`;

export function readOwners(root) {
  const path = join(root, '.mp', 'owners.yaml');
  if (!existsSync(path)) return new Map();
  let data;
  try {
    data = yaml().parse(readFileSync(path, 'utf8'));
  } catch (error) {
    throw new Error(`.mp/owners.yaml is unreadable (${error.message})`);
  }
  const components = data?.components ?? {};
  if (typeof components !== 'object' || Array.isArray(components)) throw new Error('.mp/owners.yaml: components must be a map of "Type:Name" to an owner');
  const owners = new Map();
  for (const [key, owner] of Object.entries(components)) {
    if (!key.includes(':') || typeof owner !== 'string' || !owner.trim()) throw new Error(`.mp/owners.yaml: "${key}" needs an owner's name`);
    owners.set(key, owner.trim());
  }
  return owners;
}

export const ownerOf = (owners, entry) => owners.get(entry.key) ?? owners.get(`${entry.type}:*`);
