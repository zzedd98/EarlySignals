import fs from 'fs';
import path from 'path';

export interface ScraperWorkerStats {
  workerIndex: number;
  status: 'completed' | 'error' | 'no_domains';
  domainsAssigned: number;
  domainsCrawled: number;
  snapshotsQueued: number;
  snapshotsSaved: number;
  durationMs: number;
  errorMessage?: string;
  finishedAt: string;
}

export interface OrchestratorContext {
  statsDir: string;
  workerIndex: number;
  runId: string;
}

export function createRunId(prefix = 'scraper'): string {
  return `${prefix}-${Date.now()}`;
}

export function prepareStatsDir(baseDir: string, runId: string): string {
  const statsDir = path.join(baseDir, '.orchestrator-runs', runId);
  fs.mkdirSync(statsDir, { recursive: true });
  return statsDir;
}

export function getOrchestratorContext(): OrchestratorContext | null {
  const statsDir = process.env.SCRAPER_ORCHESTRATOR_STATS_DIR?.trim();
  const runId = process.env.SCRAPER_ORCHESTRATOR_RUN_ID?.trim();
  const workerIndexRaw = process.env.SCRAPER_ORCHESTRATOR_WORKER_INDEX?.trim();

  if (!statsDir || !runId || workerIndexRaw == null || workerIndexRaw === '') {
    return null;
  }

  const workerIndex = parseInt(workerIndexRaw, 10);
  if (Number.isNaN(workerIndex)) {
    return null;
  }

  return { statsDir, workerIndex, runId };
}

export function workerStatsPath(statsDir: string, workerIndex: number): string {
  return path.join(statsDir, `worker-${workerIndex}.json`);
}

export function writeWorkerStats(
  statsDir: string,
  workerIndex: number,
  stats: ScraperWorkerStats,
): void {
  fs.mkdirSync(statsDir, { recursive: true });
  fs.writeFileSync(
    workerStatsPath(statsDir, workerIndex),
    JSON.stringify(stats, null, 2),
    'utf8',
  );
}

function readWorkerStats(filePath: string): ScraperWorkerStats | null {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8')) as ScraperWorkerStats;
  } catch {
    return null;
  }
}

export async function waitForAllWorkers(
  statsDir: string,
  expectedCount: number,
  options: { pollIntervalMs?: number; onProgress?: (done: number, total: number) => void } = {},
): Promise<ScraperWorkerStats[]> {
  const pollIntervalMs = options.pollIntervalMs ?? 2000;
  const results = new Map<number, ScraperWorkerStats>();

  while (results.size < expectedCount) {
    for (let i = 0; i < expectedCount; i++) {
      if (results.has(i)) continue;
      const filePath = workerStatsPath(statsDir, i);
      if (!fs.existsSync(filePath)) continue;
      const stats = readWorkerStats(filePath);
      if (stats) {
        results.set(i, stats);
      }
    }

    options.onProgress?.(results.size, expectedCount);

    if (results.size < expectedCount) {
      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
    }
  }

  return Array.from({ length: expectedCount }, (_, i) => results.get(i)!);
}

export function printScraperOrchestratorSummary(
  results: ScraperWorkerStats[],
  meta: { totalDomains: number; workerCount: number; batchSize: number; runId: string },
): void {
  const totals = results.reduce(
    (acc, r) => {
      acc.domainsCrawled += r.domainsCrawled;
      acc.snapshotsQueued += r.snapshotsQueued;
      acc.snapshotsSaved += r.snapshotsSaved;
      acc.errors += r.status === 'error' ? 1 : 0;
      acc.noDomains += r.status === 'no_domains' ? 1 : 0;
      acc.durationMs = Math.max(acc.durationMs, r.durationMs);
      return acc;
    },
    {
      domainsCrawled: 0,
      snapshotsQueued: 0,
      snapshotsSaved: 0,
      errors: 0,
      noDomains: 0,
      durationMs: 0,
    },
  );

  console.log('\n══════════════════════════════════════════════════');
  console.log('📊 RÉSUMÉ ORCHESTRATEUR SCRAPER');
  console.log('══════════════════════════════════════════════════');
  console.log(`   Run ID          : ${meta.runId}`);
  console.log(`   Workers         : ${meta.workerCount}`);
  console.log(`   Batch / worker  : ${meta.batchSize}`);
  console.log(`   Domaines (API)  : ${meta.totalDomains}`);
  console.log('──────────────────────────────────────────────────');
  console.log(`   Domaines crawlés: ${totals.domainsCrawled}`);
  console.log(`   Snapshots file  : ${totals.snapshotsQueued}`);
  console.log(`   Snapshots sauvés: ${totals.snapshotsSaved}`);
  if (totals.errors > 0) {
    console.log(`   Workers en erreur: ${totals.errors}`);
  }
  if (totals.noDomains > 0) {
    console.log(`   Workers sans domaine: ${totals.noDomains}`);
  }
  console.log(`   Durée max worker: ${(totals.durationMs / 1000).toFixed(1)}s`);
  console.log('──────────────────────────────────────────────────');
  for (const r of results) {
    const icon = r.status === 'error' ? '❌' : r.status === 'no_domains' ? '⚠️' : '✅';
    console.log(
      `   ${icon} Worker #${r.workerIndex} — ${r.domainsCrawled} domaine(s), ` +
        `${r.snapshotsSaved} snapshot(s) sauvé(s) (${(r.durationMs / 1000).toFixed(1)}s)`,
    );
    if (r.errorMessage) {
      console.log(`      └─ ${r.errorMessage}`);
    }
  }
  console.log('══════════════════════════════════════════════════');
  console.log('Les fenêtres workers restent ouvertes (pause).\n');
}
