// The real runtime: the host CLI's @salesforce/core and source-deploy-retrieve. Tests swap in a
// fake with the same shape. Deploys are SOAP, with explicit API options and rollback on error.
import { existsSync } from 'node:fs';
import { core, sdr } from './host.mjs';
import { watchDeploys, withMarker } from './guard.mjs';
import { componentFiles, hashFiles, readFiles } from './hash.mjs';
import { org15 } from './ids.mjs';
import { Refusal } from './lane.mjs';

const ensureArray = (value) => (value === undefined || value === null ? [] : Array.isArray(value) ? value : [value]);

/** Retrieve results per requested component: present, confirmed-absent or unknown. */
export function mapRetrieve(result, entries) {
  const responses = result?.getFileResponses?.() ?? [];
  const props = ensureArray(result?.response?.fileProperties);
  const retrieved = result?.components?.getSourceComponents?.().toArray?.() ?? [];
  const out = new Map();
  for (const entry of entries) {
    const component = retrieved.find((c) => c.type?.name === entry.type && c.fullName === entry.name);
    const failure = responses.find((r) => r.state === 'Failed' && r.type === entry.type && r.fullName === entry.name);
    // Bundles report one entry per file ("card/card.js"): take the newest. A child such as a
    // CustomField reports only its object, whose date doesn't move with the field, so it
    // gets nothing here; lastModified() looks it up when it matters.
    const prop = props
      .filter((p) => p.type === entry.type && (p.fullName === entry.name || p.fullName?.startsWith(`${entry.name}/`)))
      .sort((a, b) => String(b.lastModifiedDate).localeCompare(String(a.lastModifiedDate)))[0];
    const who = prop ? { lastModifiedBy: prop.lastModifiedByName, lastModifiedDate: prop.lastModifiedDate } : {};
    if (component) {
      const files = readFiles(componentFiles(component));
      out.set(entry.key, { state: 'present', files, hash: hashFiles(files), xml: component.xml, ...who });
    } else if (failure && /cannot be found/i.test(failure.error ?? '')) {
      out.set(entry.key, { state: 'confirmed-absent', ...who });
    } else {
      out.set(entry.key, { state: 'unknown', problem: failure?.error ?? 'nothing came back for it', ...who });
    }
  }
  return out;
}

export function deployOutcome(response = {}) {
  const truthy = (value) => value === true || value === 'true';
  const failures = ensureArray(response.details?.componentFailures).map((f) => `${f.componentType}:${f.fullName}: ${f.problem}`);
  const testFailures = ensureArray(response.details?.runTestResult?.failures).map((f) => `${f.name}.${f.methodName}: ${f.message}`);
  return {
    done: truthy(response.done),
    status: response.status,
    success: truthy(response.success) && response.status === 'Succeeded',
    checkOnly: truthy(response.checkOnly),
    runTestsEnabled: truthy(response.runTestsEnabled),
    testsRun: Number(response.details?.runTestResult?.numTestsRun ?? 0) || 0,
    failures: [...failures, ...testFailures].slice(0, 20),
  };
}

export function realRuntime() {
  return {
    async connect(target) {
      const org = await core().Org.create({ aliasOrUsername: target });
      return { org, orgId: org15(org.getOrgId()), username: org.getUsername(), conn: org.getConnection() };
    },

    async describe(c) {
      const result = await c.conn.query('SELECT Id, OrganizationType, IsSandbox, TrialExpirationDate FROM Organization');
      const row = result.records?.[0] ?? {};
      let tracksSource;
      try {
        tracksSource = await c.org.tracksSource();
      } catch {
        tracksSource = undefined;
      }
      return { edition: row.OrganizationType, sandbox: Boolean(row.IsSandbox), trial: Boolean(row.TrialExpirationDate), tracksSource, apiVersion: c.conn.getApiVersion() };
    },

    /** Source components for the entries in a project: { componentSet, found: Map key -> { component, files } }. */
    async resolveSource(projectRoot, packageDirs, entries, sourceApiVersion) {
      const { ComponentSet, ComponentSetBuilder } = sdr();
      // A fresh project may not have its package folders yet; SDR refuses missing ones.
      const existing = packageDirs.filter((dir) => existsSync(dir));
      if (!existing.length) return { componentSet: new ComponentSet(), found: new Map() };
      let componentSet;
      try {
        componentSet = await ComponentSetBuilder.build({
          sourceapiversion: sourceApiVersion,
          metadata: { metadataEntries: entries.map((entry) => entry.key), directoryPaths: existing },
          projectDir: projectRoot,
        });
      } catch (error) {
        // For example half a component (a meta file without its body): refuse, write nothing.
        throw new Refusal(`the project's source doesn't resolve, so nothing was changed: ${error.message}`);
      }
      componentSet.sourceApiVersion = sourceApiVersion;
      componentSet.projectDirectory = projectRoot;
      const found = new Map();
      for (const component of componentSet.getSourceComponents().toArray()) {
        found.set(`${component.type.name}:${component.fullName}`, { component, files: readFiles(componentFiles(component)) });
      }
      return { componentSet, found };
    },

    /** Every source component under one folder (`sf mp validate`). */
    async sourceSet(dir) {
      const { ComponentSet } = sdr();
      try {
        return { componentSet: ComponentSet.fromSource(dir) };
      } catch (error) {
        throw new Refusal(`the folder's source doesn't resolve, so nothing was validated: ${error.message}`);
      }
    },

    async retrieve(c, entries, outDir, sourceApiVersion) {
      const { ComponentSet, RegistryAccess } = sdr();
      const registry = new RegistryAccess();
      const set = new ComponentSet(entries.map((entry) => ({ fullName: entry.name, type: registry.getTypeByName(entry.type) })), registry);
      set.sourceApiVersion = sourceApiVersion;
      const operation = await set.retrieve({ usernameOrConnection: c.conn, output: outDir, merge: false });
      return mapRetrieve(await operation.pollStatus(), entries);
    },

    /** Starts the deploy with the marker set; the operation's id is the job ID. */
    async deploy(c, componentSet, apiOptions, mark) {
      watchDeploys(core(), new Set([mark.orgId]));
      return withMarker(mark, () => componentSet.deploy({ usernameOrConnection: c.conn, apiOptions }));
    },

    async poll(operation) {
      const result = await operation.pollStatus();
      return deployOutcome(result?.response);
    },

    async deployStatus(c, jobId) {
      const { MetadataApiDeploy } = sdr();
      const operation = new MetadataApiDeploy({ id: jobId, usernameOrConnection: c.conn });
      return deployOutcome(await operation.checkStatus());
    },

    /**
     * DeployRequests the given user created from just before `sinceIso` on, oldest first. The
     * 30-second margin covers ordinary clock skew between this machine and the org.
     */
    async deployRequestsSince(c, username, sinceIso) {
      const name = String(username ?? c.username).replace(/'/g, "\\'");
      const user = await c.conn.query(`SELECT Id FROM User WHERE Username = '${name}'`);
      const userId = user.records?.[0]?.Id;
      if (!userId) return [];
      const since = new Date(new Date(sinceIso).getTime() - 30_000).toISOString().replace(/\.\d+Z$/, 'Z');
      const result = await c.conn.tooling.query(
        `SELECT Id, Status, CheckOnly, CreatedDate FROM DeployRequest WHERE CreatedDate >= ${since} AND CreatedById = '${userId}' ORDER BY CreatedDate`
      );
      return (result.records ?? []).map((row) => ({ id: row.Id, status: row.Status, checkOnly: row.CheckOnly, createdDate: row.CreatedDate }));
    },

    /** Who changed a custom field last, from the Tooling API (best effort; {} when unknown). */
    async lastModified(c, entry) {
      if (entry.type !== 'CustomField') return {};
      const [object, field] = entry.name.split('.');
      if (!/^\w+$/.test(object) || !/^\w+__c$/.test(field)) return {};
      try {
        let table = object;
        if (object.endsWith('__c')) {
          const parent = await c.conn.tooling.query(`SELECT Id FROM CustomObject WHERE DeveloperName = '${object.slice(0, -3).split('__').pop()}'`);
          table = parent.records?.[0]?.Id ?? object;
        }
        const rows = await c.conn.tooling.query(`SELECT LastModifiedBy.Name, LastModifiedDate FROM CustomField WHERE DeveloperName = '${field.slice(0, -3)}' AND TableEnumOrId = '${table}'`);
        const row = rows.records?.[0];
        return row ? { lastModifiedBy: row.LastModifiedBy?.Name, lastModifiedDate: row.LastModifiedDate } : {};
      } catch {
        return {};
      }
    },

    sdrVersion() {
      try {
        return sdr().__version ?? undefined;
      } catch {
        return undefined;
      }
    },
  };
}
