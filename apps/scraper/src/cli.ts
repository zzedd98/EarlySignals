/**
 * Arguments CLI du scraper (tsx src/index.ts --worker-index 0 --batch-size 100)
 */
export interface ScraperCliOptions {
  workerIndex: number | null;
  batchSize: number;
  workerCount: number;
  bulkChunkSize: number;
  launchTerminals: boolean;
  statusFilter: string;
  keepOpen: boolean;
  /** Charge les hashes depuis l'API au démarrage (défaut: false). */
  loadSnapshotCache: boolean;
}

function parseIntArg(name: string, value: string, fallback: number): number {
  const n = parseInt(value, 10);
  if (Number.isNaN(n) || n < 0) {
    throw new Error(`Argument invalide --${name}: ${value}`);
  }
  return n;
}

export function parseScraperCliArgs(argv: string[] = process.argv.slice(2)): ScraperCliOptions {
  let workerIndex: number | null = null;
  let batchSize = parseInt(process.env.SCRAPER_BATCH_SIZE || '400', 10);
  let workerCount = parseInt(process.env.SCRAPER_WORKER_COUNT || '14', 10);
  let bulkChunkSize = parseInt(process.env.SCRAPER_BULK_CHUNK_SIZE || '20', 10);
  let launchTerminals = process.env.SCRAPER_LAUNCH_TERMINALS === 'true';
  let statusFilter = process.env.SCRAPER_STATUS_FILTER || 'active';
  let keepOpen = process.env.SCRAPER_KEEP_OPEN !== 'false';
  let loadSnapshotCache = process.env.SCRAPER_LOAD_SNAPSHOT_CACHE === 'true';

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--launch-terminals') {
      launchTerminals = true;
      continue;
    }
    if (arg === '--load-snapshot-cache' || arg === '--cache') {
      loadSnapshotCache = true;
      continue;
    }
    if (arg === '--no-snapshot-cache') {
      loadSnapshotCache = false;
      continue;
    }
    if (arg === '--keep-open') {
      keepOpen = true;
      continue;
    }
    if (arg === '--no-keep-open') {
      keepOpen = false;
      continue;
    }
    if (arg === '--worker-index' && argv[i + 1] != null) {
      workerIndex = parseIntArg('worker-index', argv[++i], 0);
      continue;
    }
    if (arg === '--batch-size' && argv[i + 1] != null) {
      batchSize = parseIntArg('batch-size', argv[++i], batchSize);
      continue;
    }
    if (arg === '--worker-count' && argv[i + 1] != null) {
      workerCount = parseIntArg('worker-count', argv[++i], workerCount);
      continue;
    }
    if (arg === '--bulk-chunk-size' && argv[i + 1] != null) {
      bulkChunkSize = parseIntArg('bulk-chunk-size', argv[++i], bulkChunkSize);
      continue;
    }
    if (arg === '--status-filter' && argv[i + 1] != null) {
      statusFilter = argv[++i];
      continue;
    }
  }

  if (batchSize < 1) {
    throw new Error('--batch-size doit être >= 1');
  }
  if (workerCount < 1) {
    throw new Error('--worker-count doit être >= 1');
  }
  if (bulkChunkSize < 1) {
    throw new Error('--bulk-chunk-size doit être >= 1');
  }

  return {
    workerIndex,
    batchSize,
    workerCount,
    bulkChunkSize,
    launchTerminals,
    statusFilter,
    keepOpen,
    loadSnapshotCache,
  };
}
