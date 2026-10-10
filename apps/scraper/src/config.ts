import dotenv from 'dotenv';
import path from 'path';

// Charge d'abord un .env local (apps/scraper/.env) si présent,
// puis le .env global à la racine du repo (../..//.env) si présent.
// Les variables déjà définies ne sont pas écrasées.
dotenv.config(); // .env local (cwd)
dotenv.config({ path: path.resolve(process.cwd(), '..', '..', '.env') });

export const config = {
  apiUrl: process.env.API_URL || 'http://localhost:8000',
  timeoutMs: parseInt(process.env.SCRAPER_TIMEOUT_MS || '20000', 10), // Increased to 20s for better success rate
  maxRetries: parseInt(process.env.SCRAPER_MAX_RETRIES || '3', 10),
  parallelism: parseInt(process.env.SCRAPER_PARALLELISM || '5', 10), // 5 sites en parallèle
  maxConcurrentPathsPerDomain: parseInt(process.env.SCRAPER_MAX_CONCURRENT_PATHS || '1', 10), // Max paths per domain in parallel (1 = sequential)
  headless: process.env.SCRAPER_HEADLESS === 'true', // Default: false (visible browser is more human-like)
  browserType: process.env.SCRAPER_BROWSER || 'chromium', // chromium, firefox, or webkit
  // Pour éviter "Google Chrome for Testing" et utiliser un Chrome humain installé :
  // ex: SCRAPER_BROWSER_CHANNEL=chrome (ou msedge) sur ta machine.
  browserChannel: process.env.SCRAPER_BROWSER_CHANNEL || 'chrome',
  // Bypass antibot lourd (Cloudflare/AWS WAF) – désactivé par défaut pour éviter les blocages longs.
  enableAntibotBypass: process.env.SCRAPER_ENABLE_ANTIBOT_BYPASS === 'true',
  /** Gros sites : pas de discovery, uniquement working_paths. Ex: SCRAPER_LARGE_DOMAINS=laredoute.fr,manomano.fr */
  largeDomains: (process.env.SCRAPER_LARGE_DOMAINS || '').split(',').map((d) => d.trim().toLowerCase()).filter(Boolean),
  /** Découverte carrières via Google : recherche "domaine + careers" et utilisation du premier lien pertinent. */
  // Désactivé par défaut pour éviter de spammer Google : il faut mettre SCRAPER_USE_GOOGLE_CAREERS_DISCOVERY=true pour l’activer.
  useGoogleCareersDiscovery: process.env.SCRAPER_USE_GOOGLE_CAREERS_DISCOVERY === 'true',
  /** Proxies HTTP (URLs complètes, virgules). Complété par SCRAPER_PROXIES_FILE (Lightning). */
  proxies: (process.env.SCRAPER_PROXIES || process.env.SCRAPER_PROXY || '')
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => (p.startsWith('http://') || p.startsWith('https://') ? p : `http://${p}`)),
  /** Fichier host:port:user:password (même format que seed_builder Lightning) */
  proxiesFile: process.env.SCRAPER_PROXIES_FILE
    ? path.resolve(process.cwd(), process.env.SCRAPER_PROXIES_FILE)
    : path.resolve(process.cwd(), '..', 'seed_builder_prospects', 'data', 'proxies.lightning.txt'),
  userAgent: process.env.SCRAPER_USER_AGENT || 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
  apiEmail: process.env.SCRAPER_API_EMAIL || 'admin@example.com',
  apiPassword: process.env.SCRAPER_API_PASSWORD || 'admin123456',
  /** Nombre de terminaux workers (launch:terminals). Batch size = ceil(domaines / workers). */
  workerCount: parseInt(process.env.SCRAPER_WORKER_COUNT || '14', 10),
  /** Domaines par worker en mode manuel (--worker-index seul). Ignoré si launch:terminals calcule le batch. */
  batchSize: parseInt(process.env.SCRAPER_BATCH_SIZE || '400', 10),
  /** Snapshots envoyés par requête POST /snapshots/bulk */
  bulkChunkSize: parseInt(process.env.SCRAPER_BULK_CHUNK_SIZE || '10', 10),
  statusFilter: process.env.SCRAPER_STATUS_FILTER || 'active',
  // Mode HTTP simple pour les working_paths : ressemble davantage au seed_builder (pas de Playwright pour ces URLs)
  httpModeForWorkingPaths: process.env.SCRAPER_HTTP_MODE_FOR_WORKING_PATHS !== 'false',
  // Normalisation HTML : supprime timestamps, IDs aléatoires, etc. pour un hash plus stable
  normalizeHtml: process.env.SCRAPER_NORMALIZE_HTML === 'true',
  // Extraction de contenu stable : utilise uniquement le contenu principal (main, article, etc.) pour le hash
  extractStableContent: process.env.SCRAPER_EXTRACT_STABLE_CONTENT === 'true',
};
