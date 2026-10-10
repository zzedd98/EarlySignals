#!/usr/bin/env node
/**
 * Lanceur unifié EarlySignals — scraper ou workers avec N terminaux.
 *
 * Usage :
 *   node scripts/launch.mjs scraper 30
 *   node scripts/launch.mjs scraper 30 --cache
 *   node scripts/launch.mjs worker 10
 *   pnpm run scraper -- 30
 *   pnpm run scraper -- 30 --cache
 */
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const USAGE = `
Usage:
  node scripts/launch.mjs <scraper|worker> [count] [--cache]

Options scraper:
  --cache   Charge le cache hash snapshots depuis l'API (désactivé par défaut)

Exemples:
  node scripts/launch.mjs scraper 30
  node scripts/launch.mjs scraper 30 --cache
  node scripts/launch.mjs worker 10
  pnpm run scraper -- 30
  pnpm run scraper -- 30 --cache
  .\\launch.ps1 scraper 30 -Cache
`.trim();

function parseCount(raw) {
  const n = parseInt(raw ?? '10', 10);
  if (Number.isNaN(n) || n < 1) {
    console.error(`❌ Nombre de terminaux invalide: ${raw ?? '(vide)'}`);
    process.exit(1);
  }
  return n;
}

function parseArgs(argv) {
  const positional = argv.filter((a) => !a.startsWith('--'));
  const flags = new Set(argv.filter((a) => a.startsWith('--')));

  const command = positional[0];
  const countRaw = positional.find((a, i) => i > 0 && /^\d+$/.test(a));
  const loadCache =
    flags.has('--cache') || flags.has('--load-snapshot-cache');

  return { command, countRaw, loadCache };
}

function runScraper(count, loadCache) {
  const scraperDir = path.join(ROOT, 'apps', 'scraper');
  console.log(
    `\n🚀 Lancement scraper — ${count} terminal(aux)` +
      (loadCache ? ' (cache activé)' : ' (sans cache)') +
      '\n',
  );

  const args = [
    'tsx',
    'src/index.ts',
    '--launch-terminals',
    '--worker-count',
    String(count),
  ];
  if (loadCache) {
    args.push('--load-snapshot-cache');
  }

  const result = spawnSync(
    process.platform === 'win32' ? 'npx.cmd' : 'npx',
    args,
    { cwd: scraperDir, stdio: 'inherit', shell: process.platform === 'win32' },
  );

  process.exit(result.status ?? 1);
}

function runWorker(count) {
  const workerDir = path.join(ROOT, 'apps', 'worker');
  const pythonCandidates = [
    path.join(ROOT, 'apps', 'api', 'venv', 'Scripts', 'python.exe'),
    path.join(ROOT, 'apps', 'api', 'venv', 'bin', 'python'),
    'python',
    'python3',
  ];

  const python = pythonCandidates.find(
    (p) => p === 'python' || p === 'python3' || fs.existsSync(p),
  );
  if (!python) {
    console.error(
      '❌ Python introuvable. Crée le venv API : cd apps/api && python -m venv venv',
    );
    process.exit(1);
  }

  const script = path.join(workerDir, 'launch_workers.py');
  console.log(`\n🚀 Lancement workers signaux — ${count} terminal(aux)\n`);

  const result = spawnSync(
    python,
    [script, '--count', String(count)],
    { cwd: workerDir, stdio: 'inherit', shell: process.platform === 'win32' },
  );

  process.exit(result.status ?? 1);
}

const { command, countRaw, loadCache } = parseArgs(process.argv.slice(2));

if (!command || !['scraper', 'worker'].includes(command)) {
  console.error(USAGE);
  process.exit(1);
}

const count = parseCount(countRaw);

if (command === 'scraper') {
  runScraper(count, loadCache);
} else {
  if (loadCache) {
    console.warn('⚠️  --cache ne s\'applique qu\'au scraper, ignoré pour worker.');
  }
  runWorker(count);
}
