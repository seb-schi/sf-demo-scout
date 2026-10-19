// Org IDs come as 15 or 18 characters; the first 15 identify the org (case-sensitive).
const ORG_ID = /^00D[0-9A-Za-z]{12}(?:[0-9A-Za-z]{3})?$/;

export const org15 = (id) => (typeof id === 'string' && ORG_ID.test(id) ? id.slice(0, 15) : undefined);

export const sameOrg = (a, b) => org15(a) !== undefined && org15(a) === org15(b);
