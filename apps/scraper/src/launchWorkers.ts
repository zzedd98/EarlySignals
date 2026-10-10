import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import { authenticate, getDomainCount } from './api';
import { initProxyPool, maskProxyUrl } from './proxyPool';
import {
  createRunId,
  prepareStatsDir,
  printScraperOrchestratorSummary,
  waitForAllWorkers,
} from './orchestratorStats';

export interface LaunchWorkersOptions {
  statusFilter: string;
  /** Nombre de terminaux à ouvrir (ex. 14 pour ~1307 domaines). */
  workerCount: number;
  /** Charge le cache hash snapshots depuis l'API (défaut: false). */
  loadSnapshotCache?: boolean;
}

/** Titre fenêtre cmd — pas d'espace ni # (cassent la commande START). */
function workerWindowTitle(workerIndex: number): string {
  return `ScraperWorker-${workerIndex}`;
}

/**
 * Lance N terminaux Windows, chacun avec un slice de domaines.
 * batchSize = ceil(total / workerCount) pour couvrir tout le parc sans trou.
 */
export async function launchScraperWorkerTerminals(
  options: LaunchWorkersOptions,
): Promise<void> {
  const { statusFilter, workerCount: requestedWorkers, loadSnapshotCache = false } = options;

  await authenticate();
  const counts = await getDomainCount();
  const total = statusFilter === 'active' ? counts.active : counts.total;

  if (total === 0) {
    console.log('⚠️  Aucun domaine à crawler. Abandon.');
    return;
  }

  const workerCount = Math.min(Math.max(1, requestedWorkers), total);
  const batchSize = Math.ceil(total / workerCount);
  const scraperDir = path.resolve(__dirname, '..');
  const pool = initProxyPool();
  const runId = createRunId('scraper');
  const statsDir = prepareStatsDir(scraperDir, runId);

  console.log(`\n🚀 Orchestrateur scraper`);
  console.log(`   Run ID          : ${runId}`);
  console.log(`   Domaines (${statusFilter}): ${total}`);
  console.log(`   Workers demandés: ${requestedWorkers}`);
  console.log(`   Workers lancés  : ${workerCount}`);
  console.log(`   Batch size (auto): ${batchSize} domaine(s)/worker`);
  console.log(
    `   Couverture: ${workerCount} × ${batchSize} = ${workerCount * batchSize} slots (dernier worker peut en avoir moins)`,
  );
  console.log(`   Snapshot cache  : ${loadSnapshotCache ? 'activé' : 'désactivé (défaut)'}`);
  if (pool.length > 0) {
    console.log(
      `   Proxies Lightning: ${pool.length} (1 proxy fixe par worker, rotation si pool < workers)`,
    );
  } else {
    console.warn(`   ⚠️  Aucun proxy Lightning — IP directe`);
  }
  console.log('');

  for (let i = 0; i < workerCount; i++) {
    const skip = i * batchSize;
    const windowTitle = workerWindowTitle(i);
    const proxyLabel =
      pool.length > 0 ? maskProxyUrl(pool[i % pool.length]) : 'direct';

    const cacheFlag = loadSnapshotCache ? ' --load-snapshot-cache' : '';
    const runCmd = `npx tsx src/index.ts --worker-index ${i} --batch-size ${batchSize} --status-filter ${statusFilter} --keep-open${cacheFlag}`;

    if (process.platform === 'win32') {
      const batPath = path.join(statsDir, `run-worker-${i}.bat`);
      const batLines = [
        '@echo off',
        `title ${windowTitle}`,
        `cd /d "${scraperDir}"`,
        `set "SCRAPER_ORCHESTRATOR_RUN_ID=${runId}"`,
        `set "SCRAPER_ORCHESTRATOR_STATS_DIR=${statsDir}"`,
        `set "SCRAPER_ORCHESTRATOR_WORKER_INDEX=${i}"`,
        `set "SCRAPER_LOAD_SNAPSHOT_CACHE=${loadSnapshotCache ? 'true' : 'false'}"`,
        'echo.',
        `echo ===== ${windowTitle} (worker #${i}) =====`,
        `echo proxy=${proxyLabel}  skip=${skip}  limit=${batchSize}`,
        'echo.',
        runCmd,
        'echo.',
        `echo [${windowTitle}] Termine (code %ERRORLEVEL%).`,
        'pause',
      ];
      fs.writeFileSync(batPath, batLines.join('\r\n'), 'utf8');

      // start cmd /k — sans titre (evite les bugs start "title" sous Windows)
      spawn('cmd.exe', ['/c', 'start', 'cmd', '/k', batPath], {
        detached: true,
        stdio: 'ignore',
        windowsHide: false,
        cwd: scraperDir,
      }).unref();
    } else {
      spawn(
        'bash',
        [
          '-lc',
          `printf '\\033]0;${windowTitle}\\007' && cd "${scraperDir}" && export SCRAPER_ORCHESTRATOR_RUN_ID="${runId}" SCRAPER_ORCHESTRATOR_STATS_DIR="${statsDir}" SCRAPER_ORCHESTRATOR_WORKER_INDEX="${i}" && echo "===== ${windowTitle} (worker #${i}) =====" && echo "proxy=${proxyLabel} skip=${skip} limit=${batchSize}" && ${runCmd}; echo; echo "[${windowTitle}] Termine"; read -p 'Entree pour fermer...' _`,
        ],
        { cwd: scraperDir, detached: true, stdio: 'ignore' },
      ).unref();
    }

    const end = Math.min(skip + batchSize, total);
    const sliceSize = Math.max(0, end - skip);
    console.log(
      `   ✅ ${windowTitle} → skip=${skip}, limit=${batchSize} (~${sliceSize} domaine(s)), proxy=${proxyLabel}`,
    );
  }

  console.log(`\n✨ ${workerCount} worker(s) lancé(s).`);
  console.log('⏳ En attente de la fin des workers...\n');

  const results = await waitForAllWorkers(statsDir, workerCount, {
    pollIntervalMs: 2000,
    onProgress: (done, total) => {
      process.stdout.write(`   … ${done}/${total} worker(s) terminé(s)\r`);
    },
  });
  console.log('');

  printScraperOrchestratorSummary(results, {
    totalDomains: total,
    workerCount,
    batchSize,
    runId,
  });
}
