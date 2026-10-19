// Flag occurrences in argv, read with the command's own flag definitions, so short chars (-o),
// single-character aliases (-u), long aliases (--targetusername), --flag=value, -ovalue, grouped
// booleans and greedy multi-value flags are recognised the way oclif's parser reads them.
// Values are never parsed: no org is created here.
export function readFlags(Command, argv) {
  const defs = { ...(Command?.baseFlags ?? {}), ...(Command?.flags ?? {}) };
  const byLong = new Map();
  const byChar = new Map();
  for (const [name, def] of Object.entries(defs)) {
    byLong.set(name, name);
    for (const alias of def?.aliases ?? []) (alias.length === 1 ? byChar : byLong).set(alias, name);
    for (const char of [def?.char, ...(def?.charAliases ?? [])].filter(Boolean)) byChar.set(char, name);
  }
  const found = [];
  const isOption = (name) => defs[name]?.type === 'option';
  // An option's values start at argv[i + 1]; returns the index of the last value it took.
  const takeValues = (name, i) => {
    let j = i;
    while (j + 1 < argv.length && !String(argv[j + 1]).startsWith('-')) {
      found.push({ name, value: argv[++j] });
      if (!defs[name].multiple) break;
    }
    if (j === i) found.push({ name, value: undefined });
    return j;
  };
  for (let i = 0; i < argv.length; i++) {
    const token = String(argv[i]);
    if (token === '--') break;
    if (token.startsWith('--')) {
      const [long, ...value] = token.slice(2).split('=');
      const name = byLong.get(long);
      if (!name) continue;
      if (value.length) found.push({ name, value: value.join('=') });
      else if (isOption(name)) i = takeValues(name, i);
      else found.push({ name, value: true });
    } else if (token.startsWith('-') && token.length > 1) {
      for (let k = 1; k < token.length; k++) {
        const name = byChar.get(token[k]);
        if (!name) break;
        if (!isOption(name)) {
          found.push({ name, value: true });
          continue;
        }
        const attached = token.slice(k + 1).replace(/^=/, '');
        if (attached) found.push({ name, value: attached });
        else i = takeValues(name, i);
        break;
      }
    }
  }
  return found;
}
