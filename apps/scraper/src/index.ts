import { Crawler } from './crawler';
import { getDomainsToCrawl, saveSnapshotsBulk, updateDomainCrawlTime, markDomainError, updateDomainWorkingPaths, getLatestSnapshotsByDomains } from './api';
import { config } from './config';
import { createLimit } from './utils/limit';
import { parseScraperCliArgs } from './cli';
import {
  createRunId,
  getOrchestratorContext,
  prepareStatsDir,
  printScraperOrchestratorSummary,
  ScraperWorkerStats,
  waitForAllWorkers,
  writeWorkerStats,
} from './orchestratorStats';
import { launchScraperWorkerTerminals } from './launchWorkers';
import {
  configureProxyForWorker,
  initProxyPool,
  maskProxyUrl,
} from './proxyPool';
import { pauseBeforeExit } from './keepOpen';
import { filterHtmlWorkingPaths, isNonHtmlAssetUrl, isSnapshotableHtml, sanitizeTextForStorage } from './utils/sanitizeText';

const cli = parseScraperCliArgs();
const limit = createLimit(config.parallelism);
const crawler = new Crawler();

async function crawlDomain(domain: any, snapshotCache: Map<string, string>): Promise<any[]> {
  const domainStartTime = Date.now();

  console.log(`\n🕷️  Starting crawl for: ${domain.domain}`);

  let crawlSuccess = false;
  let updateSuccess = false;

  try {
    // Get working paths from database (persistent - stored per domain)
    const workingPathsRaw: string[] = domain.working_paths || [];
    // Dédoublonner les URLs pour éviter de tester / sauvegarder plusieurs fois la même page
    const workingPaths: string[] = Array.from(new Set(workingPathsRaw));
    const workingPathsHtml = filterHtmlWorkingPaths(workingPaths);
    if (workingPaths.length > 0) {
      const dedupInfo =
        workingPaths.length !== workingPathsRaw.length
          ? ` (dedup: ${workingPathsRaw.length} → ${workingPaths.length})`
          : '';
      const assetInfo =
        workingPathsHtml.length < workingPaths.length
          ? `, ${workingPaths.length - workingPathsHtml.length} PDF/asset(s) exclus`
          : '';
      console.log(
        `  [${domain.domain}] 📝 Found ${workingPathsHtml.length} HTML path(s) to crawl${dedupInfo}${assetInfo}`,
      );
    }
    
    const results = await crawler.probePaths(domain.domain, workingPathsHtml);

      console.log(`  [${domain.domain}] Analyzing and saving snapshots...`);
      // Plus de compteurs d'erreur/empty - on sauvegarde tout
      let antibotCount = 0;
      let totalScore = 0; // Pour calculer le score moyen
      let maxScore = 0; // Score maximum
      
      // Buffer pour accumulation des snapshots avant bulk save
      const snapshotBuffer: any[] = [];

      for (const result of results) {
        if (result.success && result.html && result.hash) {
          const relevance = result.relevance;
          const isEmpty = result.isEmpty;
          const isError = result.isError;
          const score = result.relevanceScore || 0;
          const reasons = result.relevanceReasons || [];
          
          // Track scores for summary
          if (relevance && score > 0) {
            totalScore += score;
            if (score > maxScore) {
              maxScore = score;
            }
          }

        // Check for antibot
        const isAntibot = result.isAntibot;

        if (isAntibot) {
          antibotCount++;
          // Don't save antibot pages, but log them
          console.log(`  [${domain.domain}] 🛡️  Skipping antibot page: ${result.url}`);
        } else if (isNonHtmlAssetUrl(result.url)) {
          console.log(`  [${domain.domain}] ⏭️  Skip snapshot (PDF/asset): ${result.url}`);
        } else if (
          result.html &&
          !isSnapshotableHtml(result.html, result.url)
        ) {
          console.log(`  [${domain.domain}] ⏭️  Skip snapshot (binary content): ${result.url}`);
        } else {
          // Sauvegarder les pages HTML valides
          const shouldSave = result.success && result.html && result.hash && (result.status_code || 200) < 400;

          if (shouldSave) {
            // Check cache: skip if hash is identical to latest snapshot for this (domain_id, url)
            const cacheKey = `${domain.id}|${result.url}`;
            const existingHash = snapshotCache.get(cacheKey);
            
            if (existingHash === result.hash) {
              console.log(
                `  [${domain.domain}] ⏭️  Skip snapshot (unchanged): ${result.url}`,
              );
              continue;
            }

            // Extract detected tools from HTML (if available)
            let detectedTools: string[] = [];
            if (result.html) {
              // Simple tool detection (same logic as in crawler)
              const lowerHtml = result.html.toLowerCase();
              const tools = {
                stripe: ['stripe.com', 'js.stripe.com'],
                intercom: ['intercom.io', 'widget.intercom.io'],
                crisp: ['crisp.chat'],
                hubspot: ['hubspot.com', 'js.hubspot.com'],
                meta_pixel: ['facebook.com/tr', 'connect.facebook.net'],
                google_ads: ['googletagmanager.com', 'google-analytics.com'],
                segment: ['segment.io', 'cdn.segment.com'],
                shopify: ['shopify.com', 'cdn.shopify.com'],
                salesforce: ['salesforce.com', 'force.com'],
                zendesk: ['zendesk.com', 'zdassets.com'],
                mixpanel: ['mixpanel.com'],
                amplitude: ['amplitude.com'],
                hotjar: ['hotjar.com'],
                datadog: ['datadoghq.com'],
                sentry: ['sentry.io'],
                mailchimp: ['mailchimp.com', 'list-manage.com'],
                sendgrid: ['sendgrid.com'],
                twilio: ['twilio.com'],
                algolia: ['algolia.net', 'algolia.com'],
                elasticsearch: ['elastic.co'],
                mongodb: ['mongodb.com'],
                aws: ['amazonaws.com', 'aws.amazon.com'],
                azure: ['azure.com', 'microsoft.com'],
                gcp: ['googlecloud.com', 'gcp.com'],
              };
              
              for (const [toolName, patterns] of Object.entries(tools)) {
                if (patterns.some((pattern: string) => lowerHtml.includes(pattern))) {
                  detectedTools.push(toolName);
                }
              }
            }
            
            // Detect signal types from URL and content
            const lowerUrl = result.url.toLowerCase();
            const lowerHtml = result.html.toLowerCase();
            const hasJobContent = lowerHtml.includes('job') || lowerHtml.includes('career') || 
                                 lowerHtml.includes('emploi') || lowerHtml.includes('recrut') ||
                                 lowerHtml.includes('hiring') || lowerHtml.includes('carrière') ||
                                 lowerUrl.includes('career') || lowerUrl.includes('job') ||
                                 lowerUrl.includes('recrut') || lowerUrl.includes('emploi');
            const hasPricingContent = lowerHtml.includes('pricing') || lowerHtml.includes('tarif') ||
                                     lowerHtml.includes('prix') || lowerHtml.includes('plan') ||
                                     lowerUrl.includes('pricing') || lowerUrl.includes('tarif') ||
                                     lowerUrl.includes('prix') || lowerUrl.includes('plan');
            
            // Determine signal types
            const signalTypes: string[] = [];
            if (detectedTools.length > 0) {
              signalTypes.push('tool_added');
            }
            if (hasPricingContent) {
              signalTypes.push('pricing_change');
            }
            if (hasJobContent) {
              signalTypes.push('jobs');
            }
            
            // Add to buffer instead of saving immediately
            snapshotBuffer.push({
              domain_id: domain.id,
              url: result.url,
              status_code: result.status_code || 200,
              html: sanitizeTextForStorage(result.html),
              hash: result.hash,
              extracted_json: {
                title: result.url.endsWith('/') ? 'Homepage' : result.url,
                relevance_score: score,
                relevance_reasons: reasons,
                is_relevant: relevance,
                is_empty: false,
                is_error: false,
                is_antibot: false,
                content_length: result.html?.length || 0,
                detected_tools: detectedTools,
                signal_types: signalTypes,
              },
            });
            
            // Update cache with new hash (for subsequent checks in same run)
            snapshotCache.set(cacheKey, result.hash);
          }
        }
      }
    }

    // Return snapshots to be saved in bulk at the end (not saved here)
    // Log queued snapshots for visibility
    for (const snap of snapshotBuffer) {
      const urlDisplay = snap.url.length > 60 ? snap.url.substring(0, 60) + '...' : snap.url;
      const score = snap.extracted_json?.relevance_score || 0;
      console.log(`  [${domain.domain}] 💾 Queued snapshot: ${urlDisplay} (score: ${score})`);
    }
    
    if (snapshotBuffer.length > 0) {
      console.log(`  [${domain.domain}] 📦 Queued ${snapshotBuffer.length} snapshot(s) for bulk save at the end`);
    }

    // Collect successful HTML URLs for persistent working_paths (sans PDF/assets)
    const newWorkingPaths: string[] = [];
    for (const result of results) {
      if (
        result.success &&
        result.relevance &&
        !result.isAntibot &&
        !result.isError &&
        !result.isEmpty &&
        !isNonHtmlAssetUrl(result.url) &&
        result.html &&
        isSnapshotableHtml(result.html, result.url)
      ) {
        if (!newWorkingPaths.includes(result.url)) {
          newWorkingPaths.push(result.url);
        }
      }
    }
    
    // Met à jour working_paths : HTML only, retire les PDF hérités de l'import Grenouille
    const mergedPaths = filterHtmlWorkingPaths(
      [...new Set([...workingPathsHtml, ...newWorkingPaths])],
    ).slice(0, 10);
    const hadAssetsInDb = workingPaths.length !== workingPathsHtml.length;

    if (mergedPaths.length > 0 && (newWorkingPaths.length > 0 || hadAssetsInDb)) {
      try {
        await updateDomainWorkingPaths(domain.id, mergedPaths);
        if (hadAssetsInDb) {
          console.log(
            `  [${domain.domain}] 🧹 working_paths nettoyés (PDF/assets retirés) — ${mergedPaths.length} URL(s) HTML`,
          );
        } else {
          console.log(`  [${domain.domain}] 💾 Saved ${mergedPaths.length} working path(s) in database (persistent)`);
        }
      } catch (error: any) {
        console.warn(`  [${domain.domain}] ⚠️  Could not save working paths: ${error.message}`);
      }
    }

    // Log summary - seulement les succès
    if (snapshotBuffer.length > 0) {
      const avgScore = totalScore > 0 && snapshotBuffer.length > 0 ? totalScore / snapshotBuffer.length : 0;
      const scoreInfo = maxScore > 0 ? ` (avg score: ${avgScore.toFixed(1)}, max: ${maxScore})` : ''; 
      console.log(`  [${domain.domain}] ✅ ${snapshotBuffer.length} snapshot(s) queued${scoreInfo}`);
    }
    if (antibotCount > 0) {
      console.log(`  [${domain.domain}] 🛡️  ${antibotCount} antibot page(s) detected and skipped`);
    }

    if (snapshotBuffer.length > 0) {
      console.log(`  [${domain.domain}] 💾 Queued ${snapshotBuffer.length} snapshot(s) for bulk save`);
      crawlSuccess = true;
    } else {
      console.log(`  [${domain.domain}] ⚠️  No snapshots queued (all paths failed or empty)`);
    }

    // Try to update crawl time
    try {
      await updateDomainCrawlTime(domain.id);
      updateSuccess = true;
    } catch (error: any) {
      console.error(`  [${domain.domain}] ❌ Error updating crawl time:`, error.message);
      // Don't mark as error if only the update failed
      throw error; // Re-throw to mark as error
    }

    const totalDuration = Date.now() - domainStartTime;
    if (crawlSuccess && updateSuccess) {
      console.log(`✅ Successfully crawled: ${domain.domain} (${snapshotBuffer.length} snapshots queued, ${totalDuration}ms)`);
    }
    
    // Return snapshots for bulk save at the end
    return snapshotBuffer;
  } catch (error: any) {
    const totalDuration = Date.now() - domainStartTime;
    console.error(`❌ Error crawling ${domain.domain} (${totalDuration}ms):`, error.message);
    try {
      await markDomainError(domain.id, error.message);
    } catch (markError: any) {
      console.error(`  [${domain.domain}] ❌ Failed to mark error:`, markError.message);
    }
    // Return empty array on error
    return [];
  } finally {
    // Petite pause aléatoire entre deux domaines pour un rythme plus humain
    const pauseMs = 1000 + Math.floor(Math.random() * 2000);
    await new Promise((resolve) => setTimeout(resolve, pauseMs));
  }
}

async function main() {
  const mainStartTime = Date.now();
  const batchSize = cli.batchSize || config.batchSize;
  const bulkChunkSize = cli.bulkChunkSize || config.bulkChunkSize;
  const statusFilter = cli.statusFilter || config.statusFilter;

  if (cli.launchTerminals) {
    console.log('🚀 Mode orchestrateur — lancement des terminaux workers...');
    await launchScraperWorkerTerminals({
      statusFilter,
      workerCount: cli.workerCount || config.workerCount,
      loadSnapshotCache: cli.loadSnapshotCache,
    });
    return;
  }

  const workerIndex = cli.workerIndex;
  const skip = workerIndex != null ? workerIndex * batchSize : 0;
  const orchestratorCtx = getOrchestratorContext();
  let runStats: ScraperWorkerStats | null = null;

  const pool = initProxyPool();
  const assignedProxy = configureProxyForWorker(workerIndex);
  if (pool.length > 0) {
    if (assignedProxy) {
      config.proxies = [assignedProxy];
      console.log(`🔀 Proxy worker #${workerIndex}: ${maskProxyUrl(assignedProxy)}`);
    } else {
      config.proxies = pool;
      console.log(`🔀 ${pool.length} proxy(s) Lightning — rotation par domaine`);
    }
  } else if (config.proxiesFile) {
    console.warn(
      `⚠️  Aucun proxy chargé (fichier attendu: ${config.proxiesFile}). Crawl en IP directe.`,
    );
  }

  console.log('🚀 Starting scraper...');
  if (workerIndex != null) {
    console.log(`👷 Worker #${workerIndex} | skip=${skip} | limit=${batchSize}`);
  } else {
    console.log(
      `ℹ️  Mode single-run : ${batchSize} domaine(s) max (skip=0). Pour tout le parc : pnpm launch:terminals`,
    );
  }
  try {
      // Log HTML processing options
      const htmlProcessing = [];
      if (config.normalizeHtml) {
        htmlProcessing.push('normalize');
      }
      if (config.extractStableContent) {
        htmlProcessing.push('extract-stable');
      }
      const htmlProcessingStr = htmlProcessing.length > 0 
        ? `, HTML processing: ${htmlProcessing.join(' + ')}`
        : ', HTML processing: none (raw)';

      if (config.httpModeForWorkingPaths) {
        console.log(`📊 Configuration: parallelism=${config.parallelism}, timeout=${config.timeoutMs}ms, mode=HTTP (seed_builder‑like)${htmlProcessingStr}`);
      } else {
      // Mode rapide avec Stealth (playwright-extra + puppeteer-extra-plugin-stealth) pour comportement humain
      console.log(`📊 Configuration: parallelism=${config.parallelism}, timeout=${config.timeoutMs}ms, mode=fast + Stealth (humain), browser=${config.browserType}`);
      if (config.largeDomains.length > 0) {
        console.log(`🏢 Large domains (working_paths only): ${config.largeDomains.join(', ')}`);
      }
      console.log('🔧 Initializing browser (headless OFF)...');
      await crawler.init();
      console.log('✅ Browser initialized (fast mode, headless OFF, human mode disabled)');
    }

    console.log('🔐 Authenticating with API...');
    const domains = await getDomainsToCrawl({
      skip,
      limit: batchSize,
      statusFilter,
    });
    console.log(`\n📋 Found ${domains.length} domain(s) to crawl`);
    
    if (domains.length === 0) {
      console.log('⚠️  No domains to crawl. Exiting.');
      if (orchestratorCtx && workerIndex != null) {
        runStats = {
          workerIndex,
          status: 'no_domains',
          domainsAssigned: 0,
          domainsCrawled: 0,
          snapshotsQueued: 0,
          snapshotsSaved: 0,
          durationMs: Date.now() - mainStartTime,
          finishedAt: new Date().toISOString(),
        };
        writeWorkerStats(orchestratorCtx.statsDir, workerIndex, runStats);
      }
      return;
    }

    // Cache optionnel : hashes existants pour skip les pages inchangées
    let snapshotCache = new Map<string, string>();
    if (cli.loadSnapshotCache) {
      console.log('📦 Loading snapshot cache (latest hash per URL)...');
      const domainIds = domains.map((d) => d.id);
      snapshotCache = await getLatestSnapshotsByDomains(domainIds);
      console.log(`✅ Cache loaded: ${snapshotCache.size} existing snapshot(s) found\n`);
    } else {
      console.log('⏭️  Snapshot cache désactivé — démarrage immédiat du crawl\n');
    }

    console.log(`🔄 Starting parallel crawl (max ${config.parallelism} concurrent domains)...\n`);

    const promises = domains.map(domain =>
      limit(() => crawlDomain(domain, snapshotCache))
    );

    const allSnapshotArrays = await Promise.all(promises);
    
    // Flatten all snapshots from all domains into a single array
    const allSnapshots: any[] = [];
    for (const snapshotArray of allSnapshotArrays) {
      if (Array.isArray(snapshotArray)) {
        allSnapshots.push(...snapshotArray);
      }
    }
    
    const totalDuration = Date.now() - mainStartTime;
    console.log(`\n✨ Crawling completed in ${totalDuration}ms`);
    
    let snapshotsSaved = 0;
    // ONE SINGLE bulk save at the end for ALL domains
    if (allSnapshots.length > 0) {
      console.log(`\n📦 Saving ${allSnapshots.length} snapshot(s) in chunks of ${bulkChunkSize}...`);
      try {
        snapshotsSaved = await saveSnapshotsBulk(allSnapshots, bulkChunkSize);
        console.log(`✅ Bulk saved ${snapshotsSaved}/${allSnapshots.length} snapshot(s) (duplicates filtered by API)`);
      } catch (error: any) {
        console.error(`❌ Error during bulk save:`, error.message);
        process.exitCode = 1;
        if (orchestratorCtx && workerIndex != null) {
          runStats = {
            workerIndex,
            status: 'error',
            domainsAssigned: domains.length,
            domainsCrawled: domains.length,
            snapshotsQueued: allSnapshots.length,
            snapshotsSaved: 0,
            durationMs: totalDuration,
            errorMessage: error.message,
            finishedAt: new Date().toISOString(),
          };
          writeWorkerStats(orchestratorCtx.statsDir, workerIndex, runStats);
        }
        return;
      }
    } else {
      console.log(`\n⚠️  No snapshots to save`);
    }

    if (orchestratorCtx && workerIndex != null) {
      runStats = {
        workerIndex,
        status: 'completed',
        domainsAssigned: domains.length,
        domainsCrawled: domains.length,
        snapshotsQueued: allSnapshots.length,
        snapshotsSaved,
        durationMs: totalDuration,
        finishedAt: new Date().toISOString(),
      };
      writeWorkerStats(orchestratorCtx.statsDir, workerIndex, runStats);
    }
  } catch (error: any) {
    console.error('💥 Fatal error:', error);
    process.exitCode = 1;
    if (orchestratorCtx && workerIndex != null && !runStats) {
      runStats = {
        workerIndex,
        status: 'error',
        domainsAssigned: 0,
        domainsCrawled: 0,
        snapshotsQueued: 0,
        snapshotsSaved: 0,
        durationMs: Date.now() - mainStartTime,
        errorMessage: error?.message || String(error),
        finishedAt: new Date().toISOString(),
      };
      writeWorkerStats(orchestratorCtx.statsDir, workerIndex, runStats);
    }
  } finally {
    await crawler.close();
    console.log('👋 Scraper closed');
    if (cli.keepOpen) {
      await pauseBeforeExit();
    }
  }
}

// Run if called directly
main().catch(async (error) => {
  console.error('Unhandled error:', error);
  process.exitCode = 1;
  if (cli.keepOpen) {
    await pauseBeforeExit();
  }
});
