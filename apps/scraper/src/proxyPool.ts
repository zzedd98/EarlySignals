import fs from 'fs';
import path from 'path';
import { HttpsProxyAgent } from 'https-proxy-agent';
import { config } from './config';

/** host:port:user:password → http://user:pass@host:port */
export function proxyLineToUrl(line: string): string {
  const raw = line.trim();
  if (!raw || raw.startsWith('#')) {
    throw new Error('ligne vide ou commentaire');
  }

  const parts = raw.split(':');
  if (parts.length < 4) {
    throw new Error(`format invalide (attendu host:port:user:password): ${raw.slice(0, 80)}`);
  }

  const host = parts[0].trim();
  const port = parts[1].trim();
  const user = parts[2].trim();
  const password = parts.slice(3).join(':').trim();

  if (!host || !port || !user) {
    throw new Error(`host/port/user manquant: ${raw.slice(0, 80)}`);
  }

  const userQ = encodeURIComponent(user);
  const passQ = encodeURIComponent(password);
  return `http://${userQ}:${passQ}@${host}:${port}`;
}

export function loadProxiesFromFile(filePath: string): string[] {
  const resolved = path.resolve(filePath);
  if (!fs.existsSync(resolved)) {
    throw new Error(`Fichier proxy introuvable: ${resolved}`);
  }

  const proxies: string[] = [];
  const lines = fs.readFileSync(resolved, 'utf-8').split(/\r?\n/);
  lines.forEach((line, idx) => {
    const stripped = line.trim();
    if (!stripped || stripped.startsWith('#')) return;
    try {
      proxies.push(proxyLineToUrl(stripped));
    } catch (e: any) {
      throw new Error(`${resolved}:${idx + 1}: ${e.message}`);
    }
  });

  if (proxies.length === 0) {
    throw new Error(`Aucun proxy valide dans ${resolved}`);
  }
  return proxies;
}

export function defaultProxiesFilePath(): string {
  return path.resolve(
    process.cwd(),
    '..',
    'seed_builder_prospects',
    'data',
    'proxies.lightning.txt',
  );
}

export function maskProxyUrl(proxyUrl: string): string {
  try {
    const u = new URL(proxyUrl);
    const host = u.hostname + (u.port ? `:${u.port}` : '');
    return u.username ? `***@${host}` : host;
  } catch {
    return '***';
  }
}

let pool: string[] = [];
let workerFixedProxy: string | null = null;
let domainRotationIndex = 0;
const agentCache = new Map<string, { httpAgent: HttpsProxyAgent<string>; httpsAgent: HttpsProxyAgent<string> }>();

/** Charge SCRAPER_PROXIES + fichier Lightning (dédupliqué). */
export function initProxyPool(): string[] {
  if (pool.length > 0) {
    return pool;
  }

  const seen = new Set<string>();
  const merged: string[] = [];

  for (const url of config.proxies) {
    if (!seen.has(url)) {
      seen.add(url);
      merged.push(url);
    }
  }

  const filePath = config.proxiesFile;
  if (filePath && fs.existsSync(path.resolve(filePath))) {
    for (const url of loadProxiesFromFile(filePath)) {
      if (!seen.has(url)) {
        seen.add(url);
        merged.push(url);
      }
    }
  }

  pool = merged;
  return pool;
}

/** 1 proxy fixe par worker (workerIndex % pool). */
export function configureProxyForWorker(workerIndex: number | null): string | null {
  initProxyPool();
  workerFixedProxy = null;
  domainRotationIndex = 0;

  if (pool.length === 0) {
    return null;
  }
  if (workerIndex == null) {
    return null;
  }

  workerFixedProxy = pool[workerIndex % pool.length];
  return workerFixedProxy;
}

/** Proxy pour un domaine : fixe si worker, sinon rotation. */
export function getProxyForDomainCrawl(): string | undefined {
  if (pool.length === 0) {
    initProxyPool();
  }
  if (workerFixedProxy) {
    return workerFixedProxy;
  }
  if (pool.length === 0) {
    return undefined;
  }
  return pool[domainRotationIndex++ % pool.length];
}

export function getProxyPoolSize(): number {
  return pool.length;
}

export function getAxiosProxyAgents(proxyUrl: string) {
  let agents = agentCache.get(proxyUrl);
  if (!agents) {
    const agent = new HttpsProxyAgent(proxyUrl);
    agents = { httpAgent: agent, httpsAgent: agent };
    agentCache.set(proxyUrl, agents);
  }
  return { ...agents, proxy: false as const };
}
