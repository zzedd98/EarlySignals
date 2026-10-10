import { firefox, webkit, Browser, BrowserContext, Page } from 'playwright';
import { chromium as chromiumExtra } from 'playwright-extra';
import StealthPlugin from 'puppeteer-extra-plugin-stealth';
import { hashContent } from './utils/hash';
import axios from 'axios';
import { config } from './config';
import { CrawlResult } from './types';
import { getProxyForDomainCrawl, getAxiosProxyAgents, maskProxyUrl } from './proxyPool';
import { isNonHtmlAssetUrl, isNonHtmlBinaryContent, isSnapshotableHtml, sanitizeTextForStorage } from './utils/sanitizeText';

// Chromium avec Stealth (playwright-extra + puppeteer-extra-plugin-stealth) pour un comportement
// le plus humain possible et contourner détection bots/CAPTCHA (cf. Bright Data).
// Firefox/Webkit restent en Playwright standard.
chromiumExtra.use(StealthPlugin());

interface PageRelevance {
  isRelevant: boolean;
  score: number;
  reasons: string[];
  isEmpty: boolean;
  isError: boolean;
  statusCode?: number;
}

export class Crawler {
  private browser: Browser | null = null;
  private fastBrowser: Browser | null = null; // Browser headless séparé pour mode rapide
  private context: BrowserContext | null = null;
  /** Un ou plusieurs contextes (un par proxy si config.proxies, sinon un seul). Rotation par domaine. */
  private fastContexts: BrowserContext[] = [];
  private contextRotationIndex = 0;
  /** Proxy HTTP(S) pour le mode axios (1 par domaine ou fixe par worker). */
  private currentHttpProxy?: string;

  async init(): Promise<void> {
    // Chromium : playwright-extra + Stealth (comportement humain, bypass CAPTCHA/bots).
    // Firefox/Webkit : Playwright standard.
    const browserLauncher = config.browserType === 'firefox' ? firefox
      : config.browserType === 'webkit' ? webkit
      : chromiumExtra;
    
    // Realistic viewport (common resolution)
    const viewport = { width: 1920, height: 1080 };
    const timezoneId = 'America/New_York';
    const locale = 'en-US';
    
    // Options de lancement du navigateur (on force un vrai Chrome via channel quand possible)
    const launchOptions: Parameters<typeof browserLauncher.launch>[0] = {
      headless: false, // Désactivé temporairement pour debug (mode visible)
      args: [
        // Masquer l'automation (CRITIQUE)
        '--disable-blink-features=AutomationControlled',
        '--exclude-switches=enable-automation',
        '--disable-blink-features=AutomationControlled',
        
        // Masquer les indicateurs d'automation
        '--disable-infobars',
        '--disable-dev-shm-usage',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-default-apps',
        
        // Sécurité et performance
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-web-security',
        '--disable-features=IsolateOrigins,site-per-process',
        
        // Notifications et popups
        '--disable-notifications',
        '--disable-popup-blocking',

        // User agent et langue (sera override par context)
        '--lang=en-US,en,fr',
        
        // Masquer les traces d'automation dans les logs
        '--log-level=3',
        '--silent',
        
        // Performance
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
        '--disable-features=TranslateUI',
        '--disable-ipc-flooding-protection',
      ],
    };

    // Si on est en chromium, on demande explicitement le channel "chrome" (ou celui de la config)
    // pour utiliser ton Chrome installé et éviter "Google Chrome for Testing".
    if (config.browserType === 'chromium' && config.browserChannel) {
      (launchOptions as any).channel = config.browserChannel;
    }

    // Arguments Chrome optimisés pour l'indétection (selon techniques Bright Data)
    this.fastBrowser = await browserLauncher.launch(launchOptions);

    // Créer un ou plusieurs contextes (un par proxy pour rotation d’IP, sinon un seul)
    if (!this.fastBrowser) {
      throw new Error('Fast browser not initialized');
    }
    const contextOptions: Parameters<Browser['newContext']>[0] = {
      userAgent: config.userAgent,
      viewport: viewport,
      locale: locale,
      timezoneId: timezoneId,
      permissions: ['geolocation', 'notifications'],
      geolocation: { longitude: -74.006, latitude: 40.7128 },
      colorScheme: 'light',
      extraHTTPHeaders: {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9,fr-FR,fr;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
        'DNT': '1',
        'Pragma': 'no-cache',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-ch-ua-platform-version': '"15.0.0"',
        'sec-ch-ua-arch': '"x86"',
        'sec-ch-ua-bitness': '"64"',
        'sec-ch-ua-model': '""',
        'sec-ch-ua-full-version': '"120.0.0.0"',
        'sec-ch-ua-full-version-list': '"Not_A Brand";v="8.0.0.0", "Chromium";v="120.0.0.0", "Google Chrome";v="120.0.0.0"',
      },
      storageState: undefined,
    };
    const proxyList = config.proxies.length > 0 ? config.proxies : [undefined];
    for (const proxyUrl of proxyList) {
      const ctx = await this.fastBrowser.newContext({
        ...contextOptions,
        ...(proxyUrl != null && { proxy: { server: proxyUrl } }),
      });
      this.fastContexts.push(ctx);
    }
    if (config.proxies.length > 0) {
      console.log(`  [Proxy] Using ${this.fastContexts.length} proxy/context(s): ${config.proxies.join(', ')}`);
    }

    // Advanced anti-detection script (applied to each context)
    const antiDetectionScript = () => {
      const win = globalThis as any;
      const nav = win.navigator;
      
      // 1. Remove webdriver property (CRITICAL)
      Object.defineProperty(nav, 'webdriver', {
        get: () => false,
        configurable: true,
      });
      
      // 2. Override plugins with realistic list (CRITIQUE pour fingerprinting)
      const plugins = [
        { 
          name: 'Chrome PDF Plugin', 
          filename: 'internal-pdf-viewer',
          description: 'Portable Document Format',
          length: 1,
          0: { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: null },
        },
        { 
          name: 'Chrome PDF Viewer', 
          filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
          description: '',
          length: 1,
          0: { type: 'application/pdf', suffixes: 'pdf', description: '', enabledPlugin: null },
        },
        { 
          name: 'Native Client', 
          filename: 'internal-nacl-plugin',
          description: '',
          length: 2,
          0: { type: 'application/x-nacl', suffixes: '', description: 'Native Client Executable', enabledPlugin: null },
          1: { type: 'application/x-pnacl', suffixes: '', description: 'Portable Native Client Executable', enabledPlugin: null },
        },
      ];
      
      // Créer un objet PluginArray réaliste
      const pluginArray = plugins as any;
      pluginArray.refresh = function() {};
      pluginArray.item = function(index: number) { return plugins[index] || null; };
      pluginArray.namedItem = function(name: string) { 
        return plugins.find((p: any) => p.name === name) || null;
      };
      
      Object.defineProperty(nav, 'plugins', {
        get: () => pluginArray,
        configurable: true,
      });
      
      // MimeTypes array (doit correspondre aux plugins)
      const mimeTypes = [
        { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: plugins[0] },
        { type: 'application/x-nacl', suffixes: '', description: 'Native Client Executable', enabledPlugin: plugins[2] },
        { type: 'application/x-pnacl', suffixes: '', description: 'Portable Native Client Executable', enabledPlugin: plugins[2] },
      ];
      
      const mimeTypeArray = mimeTypes as any;
      mimeTypeArray.item = function(index: number) { return mimeTypes[index] || null; };
      mimeTypeArray.namedItem = function(name: string) { 
        return mimeTypes.find((m: any) => m.type === name) || null;
      };
      
      Object.defineProperty(nav, 'mimeTypes', {
        get: () => mimeTypeArray,
        configurable: true,
      });
      
      // 3. Override languages
      Object.defineProperty(nav, 'languages', {
        get: () => ['en-US', 'en', 'fr'],
        configurable: true,
      });
      
      // 4. Override platform
      Object.defineProperty(nav, 'platform', {
        get: () => 'Win32',
        configurable: true,
      });
      
      // 5. Override hardwareConcurrency (CPU cores)
      Object.defineProperty(nav, 'hardwareConcurrency', {
        get: () => 8, // Common value
        configurable: true,
      });
      
      // 6. Override deviceMemory
      Object.defineProperty(nav, 'deviceMemory', {
        get: () => 8, // 8GB RAM
        configurable: true,
      });
      
      // 7. Override permissions API
      const originalQuery = nav.permissions?.query;
      if (nav.permissions) {
        nav.permissions.query = function(parameters: any) {
          if (parameters.name === 'notifications') {
            return Promise.resolve({ state: 'default' });
          }
          return originalQuery ? originalQuery.call(this, parameters) : Promise.resolve({ state: 'granted' });
        };
      }
      
      // 8. Mock chrome object (Chrome-specific) - CRITIQUE pour Cloudflare
      win.chrome = {
        runtime: {
          onConnect: undefined,
          onMessage: undefined,
        },
        loadTimes: function() {
          return {
            commitLoadTime: Date.now() / 1000 - Math.random() * 2,
            connectionInfo: 'http/1.1',
            finishDocumentLoadTime: Date.now() / 1000 - Math.random(),
            finishLoadTime: Date.now() / 1000 - Math.random() * 0.5,
            firstPaintAfterLoadTime: 0,
            firstPaintTime: Date.now() / 1000 - Math.random() * 1.5,
            navigationType: 'Other',
            npnNegotiatedProtocol: 'unknown',
            requestTime: Date.now() / 1000 - Math.random() * 3,
            startLoadTime: Date.now() / 1000 - Math.random() * 3.5,
            wasAlternateProtocolAvailable: false,
            wasFetchedViaSpdy: false,
            wasNpnNegotiated: false,
          };
        },
        csi: function() {
          return {
            startE: Date.now() - Math.random() * 1000,
            onloadT: Date.now() - Math.random() * 500,
            pageT: Math.random() * 1000 + 500,
            tran: 15,
          };
        },
        app: {
          isInstalled: false,
          InstallState: {
            DISABLED: 'disabled',
            INSTALLED: 'installed',
            NOT_INSTALLED: 'not_installed',
          },
          RunningState: {
            CANNOT_RUN: 'cannot_run',
            READY_TO_RUN: 'ready_to_run',
            RUNNING: 'running',
          },
        },
      };
      
      // Masquer window.chrome si non-Chrome (mais on est sur Chromium)
      if (!win.chrome) {
        Object.defineProperty(win, 'chrome', {
          get: () => win.chrome,
          configurable: true,
        });
      }
      
      // 9. Canvas fingerprinting protection - add noise to canvas
      const CanvasPrototype = (win.HTMLCanvasElement as any)?.prototype;
      if (CanvasPrototype) {
        const originalToDataURL = CanvasPrototype.toDataURL;
        CanvasPrototype.toDataURL = function(type?: string, quality?: any) {
          const context = this.getContext('2d');
          if (context) {
            const imageData = context.getImageData(0, 0, this.width, this.height);
            // Add minimal random noise (undetectable to human eye)
            for (let i = 0; i < imageData.data.length; i += 4) {
              if (Math.random() < 0.01) { // 1% of pixels
                imageData.data[i] += Math.random() < 0.5 ? 1 : -1; // R
              }
            }
            context.putImageData(imageData, 0, 0);
          }
          return originalToDataURL.apply(this, [type, quality]);
        };
      }
      
      // 10. WebGL fingerprinting protection (CRITIQUE pour Cloudflare)
      const WebGLPrototype = (win.WebGLRenderingContext as any)?.prototype;
      if (WebGLPrototype) {
        const getParameter = WebGLPrototype.getParameter;
        WebGLPrototype.getParameter = function(parameter: number) {
          // UNMASKED_VENDOR_WEBGL
          if (parameter === 37445) {
            return 'Intel Inc.';
          }
          // UNMASKED_RENDERER_WEBGL
          if (parameter === 37446) {
            return 'Intel Iris OpenGL Engine';
          }
          return getParameter.apply(this, [parameter]);
        };
        
        // WebGL2 protection
        const WebGL2Prototype = (win.WebGL2RenderingContext as any)?.prototype;
        if (WebGL2Prototype) {
          const getParameter2 = WebGL2Prototype.getParameter;
          WebGL2Prototype.getParameter = function(parameter: number) {
            if (parameter === 37445) {
              return 'Intel Inc.';
            }
            if (parameter === 37446) {
              return 'Intel Iris OpenGL Engine';
            }
            return getParameter2.apply(this, [parameter]);
          };
        }
      }
      
      // Protection contre la détection de headless via WebGL
      const getContext = (win.HTMLCanvasElement as any)?.prototype?.getContext;
      if (getContext) {
        (win.HTMLCanvasElement as any).prototype.getContext = function(contextType: string, ...args: any[]) {
          const context = getContext.apply(this, [contextType, ...args]);
          if (contextType === 'webgl' || contextType === 'experimental-webgl') {
            const getParameter = (context as any).getParameter;
            (context as any).getParameter = function(parameter: number) {
              if (parameter === 37445) return 'Intel Inc.';
              if (parameter === 37446) return 'Intel Iris OpenGL Engine';
              return getParameter.apply(this, [parameter]);
            };
          }
          return context;
        };
      }
      
      // 11. AudioContext fingerprinting protection
      if (win.AudioContext || win.webkitAudioContext) {
        const AudioContextClass = win.AudioContext || win.webkitAudioContext;
        const originalCreateOscillator = AudioContextClass.prototype.createOscillator;
        AudioContextClass.prototype.createOscillator = function() {
          const oscillator = originalCreateOscillator.apply(this);
          const originalFrequency = oscillator.frequency.value;
          Object.defineProperty(oscillator.frequency, 'value', {
            get: () => originalFrequency + (Math.random() * 0.0001 - 0.00005), // Tiny noise
          });
          return oscillator;
        };
      }
      
      // 12. Font fingerprinting - simulate common fonts
      const HTMLElementPrototype = (win.HTMLElement as any)?.prototype;
      if (HTMLElementPrototype) {
        const originalOffsetWidth = Object.getOwnPropertyDescriptor(HTMLElementPrototype, 'offsetWidth')?.get;
        if (originalOffsetWidth) {
          Object.defineProperty(HTMLElementPrototype, 'offsetWidth', {
            get: function() {
              const width = originalOffsetWidth.call(this);
              // Add minimal variation for font detection
              return width + (Math.random() < 0.1 ? Math.random() * 0.1 - 0.05 : 0);
            },
          });
        }
      }
      
      // 13. Battery API (if available)
      if (nav.getBattery) {
        const originalGetBattery = nav.getBattery;
        nav.getBattery = function() {
          return originalGetBattery.call(nav).then((battery: any) => {
            // Add small noise to battery level
            const originalLevel = battery.level;
            Object.defineProperty(battery, 'level', {
              get: () => Math.min(1, originalLevel + (Math.random() * 0.01 - 0.005)),
            });
            return battery;
          });
        };
      }
      
      // 14. Screen properties
      Object.defineProperty(win.screen, 'availWidth', {
        get: () => 1920,
      });
      Object.defineProperty(win.screen, 'availHeight', {
        get: () => 1040,
      });
      Object.defineProperty(win.screen, 'width', {
        get: () => 1920,
      });
      Object.defineProperty(win.screen, 'height', {
        get: () => 1080,
      });
      Object.defineProperty(win.screen, 'colorDepth', {
        get: () => 24,
      });
      Object.defineProperty(win.screen, 'pixelDepth', {
        get: () => 24,
      });
      
      // 15. Connection API
      if (nav.connection || nav.mozConnection || nav.webkitConnection) {
        const connection = nav.connection || nav.mozConnection || nav.webkitConnection;
        if (connection) {
          Object.defineProperty(connection, 'rtt', {
            get: () => 50 + Math.random() * 50, // 50-100ms
          });
          Object.defineProperty(connection, 'downlink', {
            get: () => 10 + Math.random() * 5, // 10-15 Mbps
          });
        }
      }
      
      // 16. Override toString methods to hide automation (first declaration)
      const originalToString1 = Function.prototype.toString;
      Function.prototype.toString = function() {
        if (this === nav.getBattery || this === nav.permissions?.query) {
          return 'function () { [native code] }';
        }
        return originalToString1.apply(this);
      };
      
      // 17. Storage APIs - ensure they work
      try {
        win.localStorage.setItem('test', 'test');
        win.localStorage.removeItem('test');
        win.sessionStorage.setItem('test', 'test');
        win.sessionStorage.removeItem('test');
      } catch (e) {
        // Ignore
      }
      
      // 18. Override Notification permission
      if (win.Notification) {
        Object.defineProperty(win.Notification, 'permission', {
          get: () => 'default',
          configurable: true,
        });
      }
      
      // 19. Masquer les propriétés d'automation (CRITIQUE)
      // Supprimer toutes les traces de webdriver
      delete (nav as any).__proto__.webdriver;
      
      // 20. Protection contre la détection via document.documentElement
      if (win.document && win.document.documentElement) {
        Object.defineProperty(win.document.documentElement, 'webdriver', {
          get: () => undefined,
          configurable: true,
        });
      }
      
      // 21. Protection contre la détection via window.navigator
      // Supprimer les propriétés suspectes
      try {
        delete (nav as any).webdriver;
      } catch (e) {
        // Ignore
      }
      
      // 22. Override toString pour masquer les fonctions modifiées (second declaration - reuse originalToString1)
      Function.prototype.toString = function() {
        if (this === nav.getBattery || 
            this === nav.permissions?.query ||
            this === (win.chrome as any)?.loadTimes ||
            this === (win.chrome as any)?.csi) {
          return 'function () { [native code] }';
        }
        return originalToString1.apply(this);
      };
      
      // 23. Protection contre la détection de headless via window.outerHeight/outerWidth
      Object.defineProperty(win, 'outerHeight', {
        get: () => 1080,
        configurable: true,
      });
      Object.defineProperty(win, 'outerWidth', {
        get: () => 1920,
        configurable: true,
      });
      
      // 24. Protection contre la détection via navigator.permissions
      if (nav.permissions) {
        const originalQuery = nav.permissions.query.bind(nav.permissions);
        nav.permissions.query = function(parameters: any) {
          // Retourner des valeurs réalistes
          if (parameters.name === 'notifications') {
            return Promise.resolve({ state: 'default' });
          }
          if (parameters.name === 'geolocation') {
            return Promise.resolve({ state: 'prompt' });
          }
          return originalQuery(parameters).catch(() => ({ state: 'prompt' }));
        };
      }
      
      // 25. Protection contre la détection via navigator.getUserMedia
      if (nav.mediaDevices && nav.mediaDevices.getUserMedia) {
        const originalGetUserMedia = nav.mediaDevices.getUserMedia.bind(nav.mediaDevices);
        nav.mediaDevices.getUserMedia = function(constraints: any) {
          // Retourner une erreur réaliste plutôt que de bloquer
          return Promise.reject(new DOMException('Permission denied', 'NotAllowedError'));
        };
      }
      
      // 26. Masquer les propriétés suspectes de window
      const suspiciousProps = ['__playwright', '__pw', '__Puppeteer', '__nightmare', '__selenium'];
      suspiciousProps.forEach(prop => {
        try {
          delete (win as any)[prop];
        } catch (e) {
          // Ignore
        }
      });
      
      // 27. Protection contre la détection via document.$cdc, $chrome_asyncScriptInfo, etc.
      if (win.document) {
        const suspiciousDocProps = ['$cdc', '$chrome_asyncScriptInfo', '__$webdriverAsyncExecutor', '__driver_evaluate', '__webdriver_evaluate', '__selenium_evaluate', '__fxdriver_evaluate', '__driver_unwrapped', '__webdriver_unwrapped', '__selenium_unwrapped', '__fxdriver_unwrapped', '__webdriver_script_fn', '__selenium_unwrapped', '__fxdriver_unwrapped'];
        suspiciousDocProps.forEach(prop => {
          try {
            delete (win.document as any)[prop];
          } catch (e) {
            // Ignore
          }
        });
      }
    };
    
    // Apply anti-detection script to each context
    for (const ctx of this.fastContexts) {
      await ctx.addInitScript(antiDetectionScript);
    }
  }

  /** Retourne le prochain contexte (rotation round-robin quand plusieurs proxies). */
  private getNextContext(): BrowserContext {
    if (this.fastContexts.length === 0) throw new Error('Fast browser not initialized');
    return this.fastContexts[this.contextRotationIndex++ % this.fastContexts.length];
  }

  async close(): Promise<void> {
    for (const ctx of this.fastContexts) {
      await ctx.close();
    }
    this.fastContexts = [];
    if (this.fastBrowser) {
      await this.fastBrowser.close();
    }
    // Mode humain désactivé - pas de browser/context humain à fermer
  }

  /**
   * Log path crawl result with appropriate emoji and details
   */
  private logPathResult(domain: string, path: string, result: CrawlResult, duration: number): void {
    if (result.success) {
      const relevance = result.relevance;
      const score = result.relevanceScore || 0;
      const isEmpty = result.isEmpty;
      const isError = result.isError;
      const isAntibot = result.isAntibot;
      
      if (isAntibot) {
        const confidence = result.antibotConfidence || 0;
        console.log(`  [${domain}] 🛡️  ${path} - ANTIBOT DETECTED (confidence: ${confidence}%, ${duration}ms)`);
      } else if (relevance) {
        console.log(`  [${domain}] ✅ ${path} - Saved (score: ${score}, ${duration}ms)`);
      } else {
        console.log(`  [${domain}] 💾 ${path} - Saved (score: ${score}, ${duration}ms)`);
      }
    } else {
      const isAntibot = result.isAntibot;
      if (isAntibot) {
        const confidence = result.antibotConfidence || 0;
        console.log(`  [${domain}] 🛡️  ${path} - ANTIBOT: ${result.error} (confidence: ${confidence}%, ${duration}ms)`);
      } else {
        console.log(`  [${domain}] ❌ ${path} - Failed: ${result.error} (${duration}ms)`);
      }
    }
  }

  /**
   * Detect if page is blocked by antibot (Cloudflare, etc.)
   */
  private detectAntibot(html: string, title: string, url: string): {
    isBlocked: boolean;
    reason: string;
    confidence: number;
  } {
    const lowerHtml = html.toLowerCase();
    const lowerTitle = title.toLowerCase();
    let confidence = 0;
    const reasons: string[] = [];

    // Cloudflare checks
    if (lowerHtml.includes('cloudflare') || lowerHtml.includes('cf-')) {
      confidence += 30;
      reasons.push('Cloudflare detected');
    }
    if (lowerHtml.includes('checking your browser') || lowerHtml.includes('just a moment')) {
      confidence += 50;
      reasons.push('Cloudflare challenge page');
    }
    if (lowerHtml.includes('ray id') || lowerHtml.includes('cf-ray')) {
      confidence += 20;
      reasons.push('Cloudflare Ray ID found');
    }

    // Other antibot indicators
    if (lowerHtml.includes('access denied') && lowerHtml.includes('bot')) {
      confidence += 40;
      reasons.push('Bot access denied message');
    }
    if (lowerHtml.includes('captcha') || lowerHtml.includes('recaptcha')) {
      confidence += 30;
      reasons.push('CAPTCHA detected');
    }
    if (lowerHtml.includes('please enable javascript') && html.length < 5000) {
      confidence += 25;
      reasons.push('JavaScript required (likely antibot)');
    }
    if (lowerTitle.includes('access denied') || lowerTitle.includes('blocked')) {
      confidence += 30;
      reasons.push('Blocked page title');
    }

    // Check for very short content (could be antibot page)
    const textContent = html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    if (textContent.length < 200 && (lowerHtml.includes('verify') || lowerHtml.includes('security'))) {
      confidence += 20;
      reasons.push('Very short content with security keywords');
    }

    // Check for specific antibot services
    const antibotServices = [
      'datadome',
      'imperva',
      'akamai',
      'sucuri',
      'incapsula',
      'distil networks',
    ];
    for (const service of antibotServices) {
      if (lowerHtml.includes(service)) {
        confidence += 25;
        reasons.push(`${service} detected`);
      }
    }

    const isBlocked = confidence >= 30;
    return {
      isBlocked,
      reason: reasons.length > 0 ? reasons.join(', ') : 'No antibot detected',
      confidence: Math.min(100, confidence),
    };
  }

  /**
   * Detect B2B tools in HTML content (similar to worker signal detection)
   */
  private detectTools(html: string): string[] {
    const lowerHtml = html.toLowerCase();
    const detectedTools: string[] = [];
    
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
      if (patterns.some(pattern => lowerHtml.includes(pattern))) {
        detectedTools.push(toolName);
      }
    }
    
    return detectedTools;
  }

  /**
   * Analyze page content to determine if it's relevant for B2B signals
   * Detects: jobs, pricing, tools, products, partnerships, expansions, funding, etc.
   */
  private analyzeRelevance(html: string, title: string, url: string): PageRelevance {
    // REPRODUIT EXACTEMENT LA LOGIQUE DU SEED_BUILDER
    // 1. Extraire le texte (title, meta, h1, h2, body) comme extract_page_evidence
    // 2. Détecter les signaux comme detect_* du seed_builder
    // 3. Calculer un score comme compute_score du seed_builder
    
    const lowerHtml = html.toLowerCase();
    const lowerTitle = title.toLowerCase();
    const lowerUrl = url.toLowerCase();

    let score = 0;
    const reasons: string[] = [];
    let isEmpty = false;
    let isError = false;

    // Extract text content (comme extract_page_evidence du seed_builder)
    const textContent = html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    const textLength = textContent.length;
    
    // Extraire meta description, h1, h2 (comme le seed_builder)
    const metaMatch = html.match(/<meta[^>]*(?:name|property)=["'](?:description|og:description)["'][^>]*content=["']([^"']*)["']/i);
    const metaDescription = metaMatch ? metaMatch[1] : '';
    const h1Matches = html.match(/<h1[^>]*>([^<]*)<\/h1>/gi) || [];
    const h1Texts = h1Matches.map(m => m.replace(/<[^>]*>/g, '').trim());
    const h2Matches = html.match(/<h2[^>]*>([^<]*)<\/h2>/gi) || [];
    const h2Texts = h2Matches.map(m => m.replace(/<[^>]*>/g, '').trim());
    
    // Combiner tout comme le seed_builder : " ".join([title, meta_description] + h1 + h2 + [body_text])
    const combinedText = [title, metaDescription, ...h1Texts, ...h2Texts, textContent].join(' ').toLowerCase();
    
    // 2. Détecter les signaux EXACTEMENT comme le seed_builder (detect_*)
    // Sales-led CTA
    const salesLedCta = [
      "demander une démo", "demander une demo", "demander un démo",
      "contact commercial", "contactez nos experts", "parler à un expert",
      "réserver une démo", "book a demo", "request a demo", "schedule a demo",
      "contact sales", "contactez le commercial", "échangez avec un expert",
      "demandez une démo", "obtenir une démo",
    ];
    const hasSalesLedCta = salesLedCta.some(phrase => combinedText.includes(phrase));
    
    // Pricing
    const pricingKeywords = [
      "tarifs", "tarif", "pricing", "plans", "plan", "nos tarifs",
      "prix", "abonnement", "subscription", "voir les tarifs",
      "comparer les offres", "plans et tarifs",
    ];
    const hasPricing = pricingKeywords.some(kw => combinedText.includes(kw));
    
    // Recruitment
    const recruitmentKeywords = [
      "recrutement", "nous recrutons", "offres d'emploi", "offres d'emploi",
      "sales", "commercial", "marketing", "growth", "lead generation",
      "carrières", "careers", "jobs", "rejoignez-nous", "rejoignez nous",
      "postuler", "candidater", "open position", "hiring",
    ];
    const hasRecruitment = recruitmentKeywords.some(kw => combinedText.includes(kw));
    
    // Clients / case studies
    const clientsCaseKeywords = [
      "étude de cas", "etude de cas", "case study", "nos clients",
      "références", "references", "témoignages", "temoignages",
      "success stories", "clients", "qui nous font confiance",
    ];
    const hasClientsCaseStudies = clientsCaseKeywords.some(kw => combinedText.includes(kw));
    
    // France indices
    const franceIndices = [
      "siret", "siren", "société française", "societe française",
      "siège social", "siege social", "rance", "france", "paris", "lyon", "marseille",
      "bordeaux", "lille", "toulouse", "nantes", "strasbourg",
      "mentions légales", "mentions legales", "rcs ", "rcs paris", "rcs lyon",
      "sarl", "sas", "sasu", "sci ", "société par actions",
    ];
    const hasFranceIndices = franceIndices.some(kw => combinedText.includes(kw)) || 
                             /\b\d{9}\b|\b\d{14}\b/.test(combinedText);
    
    // Tools detection (comme detect_tools_in_html)
    const detectedTools = this.detectTools(html);
    const toolsCount = detectedTools.length;
    
    // 3. Calculer le score EXACTEMENT comme compute_score du seed_builder
    // Bonus (comme SCORING_BONUS)
    if (hasSalesLedCta) {
      score += 30;
      reasons.push('sales_led_cta');
    }
    if (hasPricing) {
      score += 20;
      reasons.push('pricing_plans');
    }
    if (hasRecruitment) {
      score += 25;
      reasons.push('recruitment');
    }
    if (hasClientsCaseStudies) {
      score += 15;
      reasons.push('clients_case_studies');
    }
    if (toolsCount > 0) {
      score += 10;
      reasons.push(`tools (${toolsCount})`);
    }
    if (hasFranceIndices) {
      score += 10;
      reasons.push('france_indices');
    }
    
    // Pas de pénalités pour l'instant (comme le seed_builder qui ne pénalise plus ecommerce/agency)
    
    // SUPPRIMÉ : Plus de détection d'erreur/empty - on sauvegarde TOUT ce qui a du HTML
    // Le stockage ne coûte rien, on laisse le worker décider plus tard
    
    // Page is relevant if it has some score (mais on sauvegarde quand même même si score=0)
    const isRelevant = score > 0;

    return {
      isRelevant,
      score,
      reasons: reasons.length > 0 ? reasons : ['No specific indicators found'],
      isEmpty: false, // Plus jamais de isEmpty - on sauvegarde tout
      isError: false, // Plus jamais de isError - on sauvegarde tout
    };
  }

  /**
   * Détection très simple du français sur une page HTML
   * Utilisé pour décider si on doit tester /fr pour les domaines en .com
   */
  private isFrenchContent(html: string): boolean {
    const lower = html.toLowerCase();

    // Indicateur fort : attribut de langue
    if (lower.includes('lang="fr"') || lower.includes("lang='fr'") || lower.includes('lang="fr-fr"') || lower.includes("lang='fr-fr'")) {
      return true;
    }

    // Quelques mots/expressions très fréquents sur des sites FR B2B
    const frenchKeywords = [
      'mentions légales',
      'politique de confidentialité',
      'conditions générales',
      'conditions g\u00e9n\u00e9rales',
      'recrutement',
      'nous rejoindre',
      'accueil',
      'nos offres',
      'nos services',
      'nos produits',
      'contactez-nous',
      'entreprise',
      'société',
      'soci\u00e9t\u00e9',
      'tarifs',
      'prix',
      'abonnement',
    ];

    let score = 0;
    for (const k of frenchKeywords) {
      if (lower.includes(k)) {
        score++;
        if (score >= 2) {
          return true;
        }
      }
    }

    return false;
  }

  /**
   * Detect and accept cookie popups/banners.
   * En mode rapide (fastMode=true), attente courte pour ne pas bloquer le crawl.
   */
  private async handleCookiePopup(page: Page, fastMode = false): Promise<void> {
    try {
      const waitMs = fastMode ? 400 : 1000 + Math.random() * 1000;
      await page.waitForTimeout(waitMs);
      
      // La Redoute et variantes FR
      const cookieSelectors = [
        'button:has-text("Tout accepter")',
        'a:has-text("Continuer sans accepter")',
        'button:has-text("Continuer sans accepter")',
        '[data-testid*="accept"], [data-testid*="cookie"]',
        // French
        'button:has-text("Accepter")',
        'button:has-text("Accepter tous")',
        'button:has-text("Accepter les cookies")',
        'button:has-text("J\'accepte")',
        'a:has-text("Accepter")',
        'a:has-text("Accepter tous")',
        // English
        'button:has-text("Accept")',
        'button:has-text("Accept All")',
        'button:has-text("Accept Cookies")',
        'button:has-text("I Accept")',
        'button:has-text("I Agree")',
        'button:has-text("OK")',
        'button:has-text("Allow All")',
        'a:has-text("Accept")',
        'a:has-text("Accept All")',
        // Common IDs and classes
        '#accept-cookies',
        '#cookie-accept',
        '#acceptCookie',
        '.accept-cookies',
        '.cookie-accept',
        '.accept-cookie-button',
        '[data-cookie-accept]',
        '[data-accept-cookies]',
        '[id*="accept"][id*="cookie"]',
        '[class*="accept"][class*="cookie"]',
        // Generic patterns
        'button[aria-label*="accept" i]',
        'button[aria-label*="cookie" i]',
        'button[title*="accept" i]',
        'button[title*="cookie" i]',
      ];
      
      let cookieAccepted = false;
      const clickDelayMs = fastMode ? 80 : 200 + Math.random() * 300;
      const afterClickMs = fastMode ? 300 : 500 + Math.random() * 500;
      for (const selector of cookieSelectors) {
        try {
          const element = await page.$(selector);
          if (element) {
            const isVisible = await element.isVisible().catch(() => false);
            if (isVisible) {
              console.log(`  🍪 Cookie popup detected, clicking: ${selector}`);
              await element.scrollIntoViewIfNeeded();
              await page.waitForTimeout(fastMode ? 80 : 200);
              await element.click({ delay: Math.random() * 80 + 40 });
              await page.waitForTimeout(afterClickMs);
              cookieAccepted = true;
              console.log(`  ✅ Cookie popup accepted`);
              break;
            }
          }
        } catch (e) {
          continue;
        }
      }
      
      // If no specific button found, try to find any button with cookie-related text in the page
      if (!cookieAccepted) {
        try {
          // Look for buttons containing cookie-related keywords
          const cookieKeywords = ['cookie', 'cookies', 'accept', 'accepter', 'consent'];
          const allButtons = await page.$$('button, a[role="button"], [onclick*="cookie" i]');
          
          for (const button of allButtons) {
            try {
              const text = await button.textContent();
              const ariaLabel = await button.getAttribute('aria-label') || '';
              const className = await button.getAttribute('class') || '';
              const id = await button.getAttribute('id') || '';
              
              const combinedText = `${text} ${ariaLabel} ${className} ${id}`.toLowerCase();
              
              // Check if button text contains cookie-related keywords
              if (cookieKeywords.some(keyword => combinedText.includes(keyword))) {
                const isVisible = await button.isVisible().catch(() => false);
                if (isVisible) {
                  console.log(`  🍪 Cookie popup detected (generic), clicking button with text: "${text?.substring(0, 50)}"`);
                  
                  await button.scrollIntoViewIfNeeded();
                  await page.waitForTimeout(200 + Math.random() * 300);
                  await button.click({ delay: Math.random() * 100 + 50 });
                  await page.waitForTimeout(500 + Math.random() * 500);
                  
                  cookieAccepted = true;
                  console.log(`  ✅ Cookie popup accepted (generic)`);
                  break;
                }
              }
            } catch (e) {
              continue;
            }
          }
        } catch (e) {
          // Ignore errors
        }
      }
      
      // Additional wait after accepting cookies (for page to update)
      if (cookieAccepted) {
        await page.waitForTimeout(500 + Math.random() * 500);
      }
    } catch (error) {
      // Ignore errors - cookie popup handling is best effort
      // Don't fail the entire crawl if we can't handle cookies
    }
  }

  /**
   * Simulate human-like behavior (scroll, mouse movements, keyboard, etc.)
   * Based on AWS WAF detection patterns
   */
  private async simulateHumanBehavior(page: Page): Promise<void> {
    try {
      // 1. Random delay before interaction (human reaction time)
      const initialDelay = Math.random() * 800 + 500; // 500-1300ms
      await page.waitForTimeout(initialDelay);
      
      // 2. Mouse movement pattern (human-like curve)
      const mouseMovements = 3 + Math.floor(Math.random() * 4); // 3-6 movements
      let currentX = Math.random() * 200 + 100;
      let currentY = Math.random() * 200 + 100;
      
      for (let i = 0; i < mouseMovements; i++) {
        const targetX = Math.random() * 800 + 200;
        const targetY = Math.random() * 600 + 200;
        
        // Bezier-like curve movement (human mouse path)
        const steps = 10 + Math.floor(Math.random() * 10);
        for (let step = 0; step <= steps; step++) {
          const t = step / steps;
          // Ease-in-out curve
          const eased = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
          const x = currentX + (targetX - currentX) * eased;
          const y = currentY + (targetY - currentY) * eased;
          
          await page.mouse.move(x, y, { steps: 1 });
          await page.waitForTimeout(Math.random() * 20 + 10); // 10-30ms per step
        }
        
        currentX = targetX;
        currentY = targetY;
        await page.waitForTimeout(Math.random() * 300 + 100); // Pause between movements
      }
      
      // 3. Scroll down slowly like a human (variable speed)
      const scrollSteps = 4 + Math.floor(Math.random() * 4); // 4-7 steps
      for (let i = 0; i < scrollSteps; i++) {
        const scrollAmount = Math.random() * 400 + 200; // 200-600px
        const scrollSpeed = Math.random() * 150 + 50; // 50-200ms
        
        await page.evaluate((amount) => {
          (globalThis as any).scrollBy({
            top: amount,
            left: 0,
            behavior: 'smooth'
          });
        }, scrollAmount);
        
        await page.waitForTimeout(scrollSpeed);
      }
      
      // 4. Random small scrolls (human reading behavior)
      const microScrolls = 2 + Math.floor(Math.random() * 3);
      for (let i = 0; i < microScrolls; i++) {
        await page.evaluate(() => {
          (globalThis as any).scrollBy(0, Math.random() * 50 + 20);
        });
        await page.waitForTimeout(Math.random() * 500 + 300);
      }
      
      // 5. Scroll back up a bit (common human behavior)
      await page.evaluate(() => {
        (globalThis as any).scrollBy({
          top: -(Math.random() * 300 + 100),
          behavior: 'smooth'
        });
      });
      await page.waitForTimeout(Math.random() * 400 + 200);
      
      // 6. Random mouse clicks (hover behavior)
      const clicks = Math.floor(Math.random() * 2); // 0-1 clicks
      for (let i = 0; i < clicks; i++) {
        await page.mouse.click(
          Math.random() * 800 + 200,
          Math.random() * 600 + 200,
          { delay: Math.random() * 100 + 50 } // 50-150ms click delay
        );
        await page.waitForTimeout(Math.random() * 300 + 200);
      }
      
      // 7. Keyboard activity simulation (tab navigation)
      if (Math.random() < 0.3) { // 30% chance
        await page.keyboard.press('Tab');
        await page.waitForTimeout(Math.random() * 200 + 100);
        await page.keyboard.press('Tab');
        await page.waitForTimeout(Math.random() * 200 + 100);
      }
      
      // 8. Final delay (human reading time)
      await page.waitForTimeout(Math.random() * 1000 + 500);
    } catch (error) {
      // Ignore errors in human simulation
    }
  }

  /**
   * Attempt to bypass antibot detection with multiple strategies
   * Returns true if bypass successful, false otherwise
   */
  private async attemptAntibotBypass(
    page: Page, 
    url: string, 
    initialAntibot: { isBlocked: boolean; confidence: number; reason: string },
    attemptNumber: number = 1
  ): Promise<{ success: boolean; html: string; title: string; reason: string }> {
    const bypassStartTime = Date.now();
    console.log(`  [BYPASS] 🔄 Attempt #${attemptNumber} to bypass antibot (confidence: ${initialAntibot.confidence}%, reason: ${initialAntibot.reason})`);
    
    try {
      // Strategy 1: Wait longer for challenge to resolve
      console.log(`  [BYPASS] ⏳ Strategy 1: Waiting for challenge resolution (5-10s)...`);
      const waitTime = 5000 + Math.random() * 5000; // 5-10 seconds
      await page.waitForTimeout(waitTime);
      
      // Check if challenge resolved
      let html = await page.content().catch(() => '');
      let title = await page.title().catch(() => '');
      let antibot = this.detectAntibot(html, title, url);
      
      if (!antibot.isBlocked || antibot.confidence < 30) {
        const elapsed = Date.now() - bypassStartTime;
        console.log(`  [BYPASS] ✅ Strategy 1 SUCCESS: Challenge resolved after ${elapsed}ms`);
        return { success: true, html, title, reason: 'Challenge resolved after waiting' };
      }
      
      console.log(`  [BYPASS] ⚠️  Strategy 1 FAILED: Still blocked (confidence: ${antibot.confidence}%)`);
      
      // Strategy 2: Simulate human behavior (scroll, mouse movements)
      console.log(`  [BYPASS] 🖱️  Strategy 2: Simulating human behavior...`);
      await this.simulateHumanBehavior(page);
      await page.waitForTimeout(2000 + Math.random() * 2000); // 2-4s more
      
      html = await page.content().catch(() => '');
      title = await page.title().catch(() => '');
      antibot = this.detectAntibot(html, title, url);
      
      if (!antibot.isBlocked || antibot.confidence < 30) {
        const elapsed = Date.now() - bypassStartTime;
        console.log(`  [BYPASS] ✅ Strategy 2 SUCCESS: Bypassed after human behavior (${elapsed}ms)`);
        return { success: true, html, title, reason: 'Bypassed after human behavior simulation' };
      }
      
      console.log(`  [BYPASS] ⚠️  Strategy 2 FAILED: Still blocked (confidence: ${antibot.confidence}%)`);
      
      // Strategy 3: Try to click on challenge buttons/elements
      console.log(`  [BYPASS] 🖱️  Strategy 3: Looking for challenge buttons to click...`);
      const challengeSelectors = [
        'button:has-text("Verify")',
        'button:has-text("Continue")',
        'button:has-text("I\'m not a robot")',
        'button:has-text("Vérifier")',
        'button:has-text("Continuer")',
        '[data-callback]',
        '.cf-browser-verification',
        'input[type="checkbox"]',
        '#challenge-form button',
        '.challenge-form button',
        'button[type="submit"]',
      ];
      
      let clicked = false;
      for (const selector of challengeSelectors) {
        try {
          const element = await page.$(selector);
          if (element) {
            const isVisible = await element.isVisible().catch(() => false);
            if (isVisible) {
              console.log(`  [BYPASS] 🖱️  Found challenge button: ${selector}, clicking...`);
              await element.scrollIntoViewIfNeeded();
              await page.waitForTimeout(500 + Math.random() * 500);
              await element.click({ delay: Math.random() * 100 + 50 });
              clicked = true;
              await page.waitForTimeout(3000 + Math.random() * 2000); // 3-5s after click
              break;
            }
          }
        } catch (e) {
          // Continue to next selector
        }
      }
      
      if (clicked) {
        html = await page.content().catch(() => '');
        title = await page.title().catch(() => '');
        antibot = this.detectAntibot(html, title, url);
        
        if (!antibot.isBlocked || antibot.confidence < 30) {
          const elapsed = Date.now() - bypassStartTime;
          console.log(`  [BYPASS] ✅ Strategy 3 SUCCESS: Bypassed after clicking challenge button (${elapsed}ms)`);
          return { success: true, html, title, reason: 'Bypassed after clicking challenge button' };
        }
        console.log(`  [BYPASS] ⚠️  Strategy 3 FAILED: Still blocked after click (confidence: ${antibot.confidence}%)`);
      } else {
        console.log(`  [BYPASS] ⚠️  Strategy 3 SKIPPED: No challenge button found`);
      }
      
      // Strategy 4: Reload page and wait
      if (attemptNumber < 2) {
        console.log(`  [BYPASS] 🔄 Strategy 4: Reloading page and waiting longer...`);
        await page.reload({ waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {});
        await page.waitForTimeout(5000 + Math.random() * 5000); // 5-10s
        
        html = await page.content().catch(() => '');
        title = await page.title().catch(() => '');
        antibot = this.detectAntibot(html, title, url);
        
        if (!antibot.isBlocked || antibot.confidence < 30) {
          const elapsed = Date.now() - bypassStartTime;
          console.log(`  [BYPASS] ✅ Strategy 4 SUCCESS: Bypassed after reload (${elapsed}ms)`);
          return { success: true, html, title, reason: 'Bypassed after page reload' };
        }
        console.log(`  [BYPASS] ⚠️  Strategy 4 FAILED: Still blocked after reload (confidence: ${antibot.confidence}%)`);
      }
      
      // All strategies failed
      const elapsed = Date.now() - bypassStartTime;
      console.log(`  [BYPASS] ❌ ALL STRATEGIES FAILED after ${elapsed}ms (final confidence: ${antibot.confidence}%)`);
      return { success: false, html, title, reason: `All bypass strategies failed (confidence: ${antibot.confidence}%)` };
      
    } catch (error: any) {
      const elapsed = Date.now() - bypassStartTime;
      console.log(`  [BYPASS] ❌ ERROR during bypass attempt after ${elapsed}ms: ${error.message}`);
      return { success: false, html: '', title: '', reason: `Bypass error: ${error.message}` };
    }
  }

  /**
   * Wait for Cloudflare challenge to resolve (technique Bright Data)
   */
  private async waitForCloudflareChallenge(page: Page, url: string, maxWait: number = 10000): Promise<boolean> {
    try {
      // Attendre que le challenge Cloudflare se résolve
      // Cloudflare affiche généralement "Checking your browser" puis redirige
      const startTime = Date.now();
      
      while (Date.now() - startTime < maxWait) {
        const content = await page.content().catch(() => '');
        const title = await page.title().catch(() => '');
        const lowerContent = content.toLowerCase();
        const lowerTitle = title.toLowerCase();
        
        // Si on ne voit plus les indicateurs Cloudflare, le challenge est résolu
        const hasCloudflareChallenge = 
          lowerContent.includes('checking your browser') ||
          lowerContent.includes('just a moment') ||
          lowerContent.includes('ddos protection') ||
          lowerContent.includes('ray id') ||
          lowerTitle.includes('just a moment') ||
          lowerTitle.includes('checking');
        
        if (!hasCloudflareChallenge) {
          // Attendre un peu plus pour être sûr que le contenu est chargé
          await page.waitForTimeout(500 + Math.random() * 500);
          const elapsed = Date.now() - startTime;
          console.log(`    [${url}] ✅ Cloudflare challenge cleared or not detected after ${elapsed}ms`);
          return true;
        }
        
        // Attendre un peu avant de vérifier à nouveau
        await page.waitForTimeout(500);
      }
      
      const elapsed = Date.now() - startTime;
      console.log(`    [${url}] ⚠️ Cloudflare challenge still present after ${elapsed}ms (timeout ${maxWait}ms)`);
      return false; // Timeout
    } catch (e) {
      console.log(`    [${url}] ⚠️ Error while waiting for Cloudflare challenge: ${(e as any)?.message || e}`);
      return false;
    }
  }

  /**
   * Crawl URL in fast mode with existing page (headless, minimal delays) - first pass
   * Réutilise une page existante pour éviter de créer/fermer à chaque fois
   */
  async crawlUrlFastWithPage(page: Page, url: string): Promise<CrawlResult> {
    // Mode HTTP simple optionnel (proche du seed_builder) : pas de Playwright, simple requête GET
    if (config.httpModeForWorkingPaths) {
      const httpStartTime = Date.now();
      try {
        const proxyUrl = this.currentHttpProxy;
        const response = await axios.get<string>(url, {
          headers: {
            'User-Agent': config.userAgent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
          },
          timeout: config.timeoutMs,
          maxRedirects: 5,
          validateStatus: () => true,
          ...(proxyUrl ? getAxiosProxyAgents(proxyUrl) : {}),
        });

        const statusCode = response.status;
        const contentType =
          typeof response.headers?.['content-type'] === 'string'
            ? response.headers['content-type']
            : undefined;
        const rawBody = typeof response.data === 'string' ? response.data : '';

        if (
          statusCode < 400 &&
          rawBody.trim() &&
          isNonHtmlBinaryContent(rawBody, url, contentType)
        ) {
          const elapsed = Date.now() - httpStartTime;
          console.log(
            `    [HTTP] ⏭️ ${url} skipped (binary/PDF, not HTML) (${elapsed}ms)`,
          );
          return {
            success: false,
            domain_id: '',
            url,
            status_code: statusCode,
            error: 'Binary or PDF content (not HTML)',
            html: '',
            hash: '',
            isError: true,
          };
        }

        const html = sanitizeTextForStorage(rawBody);

        if (statusCode >= 400 || !html.trim()) {
          const elapsed = Date.now() - httpStartTime;
          console.log(`    [HTTP] ⚠️ ${url} returned HTTP ${statusCode} or empty body (${elapsed}ms)`);
          return {
            success: false,
            domain_id: '',
            url,
            status_code: statusCode,
            error: `HTTP ${statusCode} or empty body`,
            html,
            hash: html ? hashContent(html) : '',
            isError: true,
          };
        }

        // Analyse de pertinence sur le HTML brut (même logique que le mode Playwright)
        const titleMatch = html.match(/<title[^>]*>([^<]*)<\/title>/i);
        const title = titleMatch ? titleMatch[1] : '';
        const relevance = this.analyzeRelevance(html, title, url);
        const hash = hashContent(html);
        const elapsed = Date.now() - httpStartTime;
        console.log(`    [HTTP] ✅ Done ${url} (status ${statusCode}, relevant=${relevance.isRelevant}, score=${relevance.score}, ${elapsed}ms)`);

        return {
          success: true,
          domain_id: '',
          url,
          status_code: statusCode,
          html,
          hash,
          relevance: relevance.isRelevant,
          relevanceScore: relevance.score,
          relevanceReasons: relevance.reasons,
          isEmpty: false, // Plus jamais de isEmpty - on sauvegarde tout
          isError: false, // Plus jamais de isError - on sauvegarde tout
        };
      } catch (error: any) {
        const elapsed = Date.now() - httpStartTime;
        console.log(`    [HTTP] ❌ Error on ${url}: ${error.message} (${elapsed}ms)`);
        return {
          success: false,
          domain_id: '',
          url,
          error: error.message,
        };
      }
    }

    const fastStartTime = Date.now();
    console.log(`    [FAST] ▶️ Navigating to ${url}`);
    try {
      // Mode rapide ULTRA rapide : ~1 seconde maximum
      // Pas de délai avant la requête (0ms)
      
      // Navigate avec timeout court pour ne pas bloquer
      const response = await page.goto(url, {
        waitUntil: 'domcontentloaded',
        timeout: 8000, // 8s pour laisser La Redoute / WAF charger
      }).catch(() => null);
      
      // Attendre que Cloudflare/WAF se résolve si présent
      await this.waitForCloudflareChallenge(page, url, 4000);

      const statusCode = response?.status() || 200;

      if (statusCode >= 400) {
        return {
          success: false,
          domain_id: '',
          url,
          status_code: statusCode,
          error: `HTTP ${statusCode}`,
          html: '',
          hash: '',
        };
      }

      await page.waitForLoadState('domcontentloaded', { timeout: 2000 }).catch(() => {});
      
      try {
        await this.handleCookiePopup(page, true); // fastMode pour ne pas bloquer
      } catch {
        // best-effort
      }

      // Pas de scroll ni de simulation humaine lourde ici pour garder le mode vraiment rapide.
      // (le mode “lent” / humain complet reste dans crawlUrlWithPage si on le réactive un jour)
      
      // Attente minimale : 100ms maximum
      await page.waitForTimeout(100);
      
      // Pas de waitForSelector en mode rapide (trop lent)
      
      // Ensure basic async operations complete (timeout très court)
      await page.evaluate(() => {
        return new Promise((resolve) => {
          if ((globalThis as any).requestIdleCallback) {
            (globalThis as any).requestIdleCallback(resolve, { timeout: 200 }); // 200ms max
          } else {
            setTimeout(resolve, 100); // 100ms max
          }
        });
      });

      // Get initial content AFTER all waits
      let html = await page.content();
      let hash = hashContent(html);
      let title = await page.title();

      // Fast mode: quick antibot check
      const antibot = this.detectAntibot(html, title, url);
      if (antibot.isBlocked && antibot.confidence >= 30) {
        console.log(`  [${url}] 🛡️  ANTIBOT DETECTED in fast mode (confidence: ${antibot.confidence}%, reason: ${antibot.reason})`);

        // Par défaut, on NE TENTE PAS de bypass lourd en mode rapide pour éviter les blocages de 20–60s.
        if (!config.enableAntibotBypass) {
          console.log(`  [${url}] ⏩ Skipping heavy antibot bypass (config.enableAntibotBypass=false)`);
          const elapsed = Date.now() - fastStartTime;
          return {
            success: false,
            domain_id: '',
            url,
            status_code: statusCode,
            error: `Antibot detected (fast mode, no bypass): ${antibot.reason} (confidence: ${antibot.confidence}%)`,
            html: html.substring(0, 5000),
            hash,
            isAntibot: true,
            antibotConfidence: antibot.confidence,
            antibotReason: antibot.reason,
          };
        }

        console.log(`  [${url}] 🔄 Attempting to bypass antibot (enableAntibotBypass=true)...`);
        
        // Attempt to bypass antibot (this may take longer)
        const bypassResult = await this.attemptAntibotBypass(page, url, antibot, 1);
        
        if (bypassResult.success) {
          console.log(`  [${url}] ✅ ANTIBOT BYPASSED: ${bypassResult.reason}`);
          // Update html and title with bypassed content
          html = bypassResult.html;
          title = bypassResult.title;
          hash = hashContent(html);
          
          // Re-check antibot after bypass
          const finalAntibot = this.detectAntibot(html, title, url);
          if (finalAntibot.isBlocked && finalAntibot.confidence >= 50) {
            console.log(`  [${url}] ⚠️  Still blocked after bypass (confidence: ${finalAntibot.confidence}%)`);
            return {
              success: false,
              domain_id: '',
              url,
              status_code: statusCode,
              error: `Antibot still detected after bypass: ${finalAntibot.reason} (confidence: ${finalAntibot.confidence}%)`,
              html: html.substring(0, 5000),
              hash,
              isAntibot: true,
              antibotConfidence: finalAntibot.confidence,
              antibotReason: finalAntibot.reason,
            };
          }
          // Bypass successful, continue with normal processing
          console.log(`  [${url}] ✅ Bypass confirmed: antibot cleared (confidence: ${finalAntibot.confidence}%)`);
        } else {
          console.log(`  [${url}] ❌ ANTIBOT BYPASS FAILED: ${bypassResult.reason}`);
          return {
            success: false,
            domain_id: '',
            url,
            status_code: statusCode,
            error: `Antibot detected (bypass failed): ${antibot.reason} (confidence: ${antibot.confidence}%)`,
            html: html.substring(0, 5000),
            hash: hashContent(html),
            isAntibot: true,
            antibotConfidence: antibot.confidence,
            antibotReason: antibot.reason,
          };
        }
      }

      // Analyze relevance
      const relevance = this.analyzeRelevance(html, title, url);

      const elapsed = Date.now() - fastStartTime;
      console.log(`    [FAST] ✅ Done ${url} (status ${statusCode}, relevant=${relevance.isRelevant}, score=${relevance.score}, ${elapsed}ms)`);
      return {
        success: true,
        domain_id: '', // Will be set by caller
        url,
        status_code: statusCode,
        html,
        hash,
        relevance: relevance.isRelevant,
        relevanceScore: relevance.score,
        relevanceReasons: relevance.reasons,
        isEmpty: relevance.isEmpty,
        isError: relevance.isError,
      };
    } catch (error: any) {
      // Check if it's a timeout
      if (error.message.includes('timeout') || error.message.includes('Timeout')) {
        return {
          success: false,
          domain_id: '',
          url,
          error: `Timeout after ${config.timeoutMs}ms`,
        };
      }
      const elapsed = Date.now() - fastStartTime;
      console.log(`    [FAST] ❌ Error on ${url}: ${error.message} (${elapsed}ms)`);
      return {
        success: false,
        domain_id: '',
        url,
        error: error.message,
      };
    }
    // Note: On ne ferme pas la page ici car elle est réutilisée
  }

  /**
   * Crawl URL in fast mode (headless, minimal delays) - first pass
   * Version qui crée/ferme une page (pour compatibilité avec mode batch)
   */
  async crawlUrlFast(url: string): Promise<CrawlResult> {
    if (!this.fastBrowser || this.fastContexts.length === 0) {
      throw new Error('Fast browser not initialized');
    }

    const page = await this.getNextContext().newPage();
    try {
      return await this.crawlUrlFastWithPage(page, url);
    } finally {
      await page.close();
    }
  }

  /**
   * Crawl URL in human mode with existing page (DEPRECATED - human mode disabled, kept for compatibility)
   * Réutilise une page existante pour éviter de créer/fermer à chaque fois
   */
  async crawlUrlWithPage(page: Page, url: string): Promise<CrawlResult> {
    try {
      // Add random delay before request (human-like reaction time)
      const preRequestDelay = Math.random() * 1500 + 800; // 800-2300ms
      await new Promise(resolve => setTimeout(resolve, preRequestDelay));
      
      // Navigate with realistic wait strategy and referer
      const referers = [
        'https://www.google.com/',
        'https://www.google.com/search?q=',
        'https://www.bing.com/',
        undefined, // Direct navigation (30% chance)
      ];
      const referer = Math.random() < 0.7 ? referers[Math.floor(Math.random() * 3)] : undefined;
      
      const response = await page.goto(url, {
        waitUntil: 'domcontentloaded',
        timeout: config.timeoutMs,
        referer: referer,
      }).catch(() => null);
      
      // Attendre que Cloudflare challenge se résolve si présent (technique Bright Data)
      await this.waitForCloudflareChallenge(page, url, 8000);

      // Get actual status code
      const statusCode = response?.status() || 200;

      // Check for error status codes IMMEDIATELY - ne pas perdre de temps avec les délais
      if (statusCode >= 400) {
        return {
          success: false,
          domain_id: '',
          url,
          status_code: statusCode,
          error: `HTTP ${statusCode}`,
          html: '',
          hash: '',
        };
      }

      // Détection précoce d'erreur : vérifier le contenu après chargement initial
      // (avant tous les délais longs)
      await page.waitForLoadState('domcontentloaded', { timeout: 3000 }).catch(() => {});
      await page.waitForTimeout(200); // Délai minimal pour le DOM
      
      // Vérifier rapidement si c'est une page d'erreur (avant tous les délais)
      const quickHtml = await page.content();
      const quickTitle = await page.title();
      const quickRelevance = this.analyzeRelevance(quickHtml, quickTitle, url);
      
      // Si c'est une page d'erreur, arrêter immédiatement (ne pas perdre de temps)
      if (quickRelevance.isError) {
        return {
          success: true,
          domain_id: '',
          url,
          status_code: statusCode,
          html: quickHtml,
          hash: hashContent(quickHtml),
          relevance: false,
          relevanceScore: quickRelevance.score,
          relevanceReasons: quickRelevance.reasons,
          isEmpty: quickRelevance.isEmpty,
          isError: true,
        };
      }

      // Attendre que Cloudflare challenge se résolve si présent (CRITIQUE)
      await this.waitForCloudflareChallenge(page, url, 8000);
      
      // Wait for page to be interactive (but not too long)
      await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {
        // Ignore timeout, continue anyway
      });
      
      // Wait for JavaScript to execute (critical for bot detection and Cloudflare)
      // Cloudflare a besoin de temps pour exécuter son JavaScript de vérification
      await page.waitForTimeout(1000 + Math.random() * 1000); // 1-2s (augmenté pour Cloudflare)
      
      // Detect and accept cookie popups/banners
      await this.handleCookiePopup(page);
      
      // Simulate human behavior (scroll, mouse movements, keyboard)
      // This is CRITICAL for AWS WAF and similar systems
      await this.simulateHumanBehavior(page);
      
      // Additional wait for dynamic content and JavaScript execution
      await page.waitForTimeout(1500 + Math.random() * 1500); // 1.5-3s random delay
      
      // Wait for potential lazy-loaded content (job listings, etc.)
      // Many career pages load content dynamically after scroll
      try {
        // Wait for common job listing selectors to appear
        await page.waitForSelector('article, [class*="job"], [class*="offer"], [class*="poste"], [class*="emploi"], [id*="job"], [id*="offer"]', { 
          timeout: 5000 
        }).catch(() => {
          // Ignore if no specific selector found - continue anyway
        });
      } catch (e) {
        // Ignore selector timeout
      }
      
      // Additional wait after potential content load
      await page.waitForTimeout(1000 + Math.random() * 1000); // 1-2s more
      
      // Ensure all async operations are complete
      await page.evaluate(() => {
        return new Promise((resolve) => {
          if ((globalThis as any).requestIdleCallback) {
            (globalThis as any).requestIdleCallback(resolve, { timeout: 2000 });
          } else {
            setTimeout(resolve, 500);
          }
        });
      });

      // Get initial content AFTER all waits
      let html = await page.content();
      let hash = hashContent(html);
      let title = await page.title();

      // Wait for potential challenge pages to resolve (Cloudflare, AWS WAF, etc.)
      // Many antibot systems need time to verify the browser
      let challengeResolved = false;
      let attempts = 0;
      const maxChallengeAttempts = 3;
      
      while (attempts < maxChallengeAttempts && !challengeResolved) {
        // Wait for potential challenge resolution
        await page.waitForTimeout(2000 + Math.random() * 2000); // 2-4 seconds
        
        // Check if page content changed (challenge resolved)
        const currentHtml = await page.content();
        const currentTitle = await page.title();
        
        // Detect antibot
        const antibot = this.detectAntibot(currentHtml, currentTitle, url);
        
        if (antibot.isBlocked && antibot.confidence >= 50) {
          // High confidence antibot - try to wait longer and simulate more human behavior
          if (attempts < maxChallengeAttempts - 1) {
            console.log(`  [${url}] ⏳ Waiting for challenge resolution (attempt ${attempts + 1}/${maxChallengeAttempts})...`);
            
            // Simulate more human behavior to help pass challenge
            await this.simulateHumanBehavior(page);
            await page.waitForTimeout(3000 + Math.random() * 3000); // 3-6 seconds
            
            // Try clicking on potential challenge buttons/elements
            try {
              const challengeSelectors = [
                'button:has-text("Verify")',
                'button:has-text("Continue")',
                'button:has-text("I\'m not a robot")',
                '[data-callback]',
                '.cf-browser-verification',
                'input[type="checkbox"]',
              ];
              
              for (const selector of challengeSelectors) {
                try {
                  const element = await page.$(selector);
                  if (element) {
                    await element.click();
                    await page.waitForTimeout(1000 + Math.random() * 1000);
                    break;
                  }
                } catch (e) {
                  // Ignore click errors
                }
              }
            } catch (e) {
              // Ignore click errors
            }
            
            attempts++;
            continue;
          } else {
            // Final attempt failed - mark as antibot but continue
            html = currentHtml;
            title = currentTitle;
            hash = hashContent(html);
            
            return {
              success: false,
              domain_id: '',
              url,
              status_code: statusCode,
              error: `Antibot detected: ${antibot.reason} (confidence: ${antibot.confidence}%)`,
              html: html.substring(0, 5000), // Save more for analysis
              hash,
              isAntibot: true,
              antibotConfidence: antibot.confidence,
              antibotReason: antibot.reason,
            };
          }
        } else {
          // Challenge resolved or low confidence - continue
          challengeResolved = true;
          html = currentHtml;
          title = currentTitle;
          hash = hashContent(html);
        }
      }
      
      // Final antibot check (even if challenge seems resolved)
      const finalAntibot = this.detectAntibot(html, title, url);
      if (finalAntibot.isBlocked && finalAntibot.confidence >= 70) {
        // Very high confidence - likely still blocked
        return {
          success: false,
          domain_id: '',
          url,
          status_code: statusCode,
          error: `Antibot detected: ${finalAntibot.reason} (confidence: ${finalAntibot.confidence}%)`,
          html: html.substring(0, 5000),
          hash,
          isAntibot: true,
          antibotConfidence: finalAntibot.confidence,
          antibotReason: finalAntibot.reason,
        };
      }

      // Analyze relevance
      const relevance = this.analyzeRelevance(html, title, url);

      return {
        success: true,
        domain_id: '', // Will be set by caller
        url,
        status_code: statusCode,
        html,
        hash,
        relevance: relevance.isRelevant,
        relevanceScore: relevance.score,
        relevanceReasons: relevance.reasons,
        isEmpty: relevance.isEmpty,
        isError: relevance.isError,
      };
    } catch (error: any) {
      // Check if it's a timeout
      if (error.message.includes('timeout') || error.message.includes('Timeout')) {
        return {
          success: false,
          domain_id: '',
          url,
          error: `Timeout after ${config.timeoutMs}ms`,
        };
      }
      return {
        success: false,
        domain_id: '',
        url,
        error: error.message,
      };
    }
    // Note: On ne ferme pas la page ici car elle est réutilisée
  }

  /**
   * Crawl URL (DEPRECATED - now uses fast mode only, human mode disabled)
   * Version qui crée/ferme une page (pour compatibilité avec mode batch)
   */
  async crawlUrl(url: string): Promise<CrawlResult> {
    // Mode humain désactivé - utiliser le mode rapide à la place
    if (this.fastContexts.length === 0) {
      throw new Error('Fast browser not initialized');
    }

    const page = await this.getNextContext().newPage();
    try {
      return await this.crawlUrlFastWithPage(page, url);
    } finally {
      await page.close();
    }
  }

  /**
   * Generate subdomain variants for careers/jobs pages
   * Examples: manomano.fr -> careers.manomano.fr, careers.manomano.jobs, jobs.manomano.fr, etc.
   */
  private generateSubdomainVariants(domain: string): string[] {
    const variants: string[] = [];
    
    // Extract base domain and TLD
    // manomano.fr -> base: manomano, tld: fr
    // careers.manomano.jobs -> base: manomano, tld: jobs
    const parts = domain.split('.');
    if (parts.length < 2) {
      return variants; // Invalid domain
    }
    
    // Get base domain (remove subdomain if present, keep last 2 parts for TLD)
    // manomano.fr -> manomano.fr
    // www.manomano.fr -> manomano.fr
    // careers.manomano.jobs -> manomano.jobs
    let baseDomain = domain;
    if (parts.length > 2) {
      // Has subdomain, extract base
      baseDomain = parts.slice(-2).join('.');
    }
    
    const baseParts = baseDomain.split('.');
    const baseName = baseParts[0]; // manomano
    const tld = baseParts[1] || 'com'; // fr, jobs, com, etc.
    
    // Common subdomain prefixes for careers/jobs (réduit pour éviter trop de tentatives)
    // On garde seulement les plus courants
    const subdomainPrefixes = [
      'careers',
      'jobs',
      'recrutement', // Français
      'emplois',     // Français
    ];
    
    // Common TLD variants (réduit : seulement original + jobs si différent)
    const tldVariants = [tld]; // Start with original TLD
    if (tld !== 'jobs') tldVariants.push('jobs'); // Seulement .jobs en plus
    
    // Generate subdomain variants
    for (const prefix of subdomainPrefixes) {
      for (const tldVariant of tldVariants) {
        const subdomain = `${prefix}.${baseName}.${tldVariant}`;
        variants.push(subdomain);
      }
    }
    
    // Remove duplicates
    return [...new Set(variants)];
  }

  /**
   * Extract relevant links/buttons from a page that might lead to job/career pages
   * Returns array of URLs that are likely to contain job listings
   */
  private async extractRelevantLinks(page: Page, currentUrl: string, domain: string): Promise<string[]> {
    try {
      // Wait a bit for dynamic content to load
      await page.waitForTimeout(500);
      
      // Extract all links and buttons that might lead to job pages
      const links = await page.evaluate((args: { domain: string; currentUrl: string }) => {
        // Declare document for TypeScript in evaluate context
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const doc = (globalThis as any).document;
        
        const { domain, currentUrl } = args;
        const relevantUrls: string[] = [];
        const baseDomain = domain.toLowerCase();
        const baseName = baseDomain.split('.')[0]; // ex: laredoute.fr -> laredoute
        const currentUrlObj = new URL(currentUrl);
        const currentHostname = currentUrlObj.hostname.toLowerCase();
        
        // Hôtes externes connus pour les sites carrières "dédiés" (ex: TalentView),
        // autorisés UNIQUEMENT quand le sous-domaine contient le nom de la marque.
        // Exemple autorisé : laredoute-talent.talentview.io (contient "laredoute")
        // Exemple rejeté : talentview.io tout seul (générique / job board).
        const externalCareerHosts = [
          'talentview.io',
        ];
        
        // Keywords to look for in link text, href, or button text - ALL B2B signals (French + English)
        const b2bKeywords = [
          // Jobs - French
          'emploi', 'emplois', 'carrière', 'carrières', 'recrutement', 'recrute', 'recrutons',
          'poste', 'postes', 'offre', 'offres', 'candidature', 'candidater', 'candidat',
          'rejoindre', 'rejoins', 'rejoignez', 'nous rejoindre', 'travailler avec nous',
          'opportunité', 'opportunités', 'vacance', 'vacances',
          // Jobs - English
          'job', 'jobs', 'career', 'careers', 'recruitment', 'recruit', 'recruiting', 'hiring',
          'position', 'positions', 'opening', 'openings', 'application', 'apply', 'applicant',
          'join', 'join us', 'join our team', 'work with us', 'work for us',
          'opportunity', 'opportunities', 'vacancy', 'vacancies',
          // Pricing - French
          'tarif', 'tarifs', 'prix', 'pricing', 'abonnement', 'facturation', 'plan', 'plans',
          // Pricing - English
          'pricing', 'price', 'subscription', 'billing', 'plan', 'plans', 'package', 'quote',
          // Products - French
          'produit', 'produits', 'solution', 'solutions', 'service', 'services', 'fonctionnalité',
          // Products - English
          'product', 'products', 'solution', 'solutions', 'service', 'services', 'feature',
          // Expansions - French
          'ouverture', 'expansion', 'nouveau bureau', 'nouvelle ville',
          // Expansions - English
          'opening', 'expansion', 'new office', 'new location',
          // Partnerships - French
          'partenaire', 'partenariat', 'collaboration',
          // Partnerships - English
          'partner', 'partnership', 'collaboration',
          // Funding - French
          'financement', 'investissement', 'levée de fonds',
          // Funding - English
          'funding', 'investment', 'fundraise'
        ];
        
        // Get all links (a tags)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const allLinks = Array.from(doc.querySelectorAll('a[href]')) as any[];
        for (const link of allLinks) {
          const href = (link.getAttribute('href') || '').trim();
          const text = (link.textContent || '').toLowerCase();
          const ariaLabel = (link.getAttribute('aria-label') || '').toLowerCase();
          const title = (link.getAttribute('title') || '').toLowerCase();
          
          // Combine all text for keyword matching
          const combinedText = `${text} ${ariaLabel} ${title} ${href}`.toLowerCase();
          
          // Check if link contains B2B-related keywords
          const hasB2BKeyword = b2bKeywords.some((keyword: string) => combinedText.includes(keyword));
          
          if (hasB2BKeyword && href) {
            try {
              // Resolve relative URLs
              const absoluteUrl = new URL(href, currentUrl);
              const urlHostname = absoluteUrl.hostname.toLowerCase();

              // Autoriser :
              // - même domaine ou sous-domaine
              // - OU tout hostname qui contient le nom de la marque (ex: corporate.laredoute.com)
              // - OU hôte carrière externe connu (ex: *.talentview.io) dont le sous-domaine contient le nom de la marque
              const isSameOrSubdomain =
                urlHostname === baseDomain ||
                urlHostname.endsWith(`.${baseDomain}`) ||
                urlHostname.includes(baseName);

              const isExternalCareerHost =
                externalCareerHosts.some((host: string) => urlHostname.endsWith(host)) &&
                urlHostname.includes(baseName);

              if (isSameOrSubdomain || isExternalCareerHost) {
                // Normalize URL (remove fragments, trailing slashes for comparison)
                const normalizedUrl = absoluteUrl.href.split('#')[0].replace(/\/$/, '');
                if (normalizedUrl && !relevantUrls.includes(normalizedUrl)) {
                  relevantUrls.push(normalizedUrl);
                }
              }
            } catch (e) {
              // Invalid URL, skip
            }
          }
        }
        
        // Get all buttons that might be links (check onclick, data-href, etc.)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const allButtons = Array.from(doc.querySelectorAll('button, [role="button"], [onclick]')) as any[];
        for (const button of allButtons) {
          const text = (button.textContent || '').toLowerCase();
          const ariaLabel = (button.getAttribute('aria-label') || '').toLowerCase();
          const title = (button.getAttribute('title') || '').toLowerCase();
          const onclick = (button.getAttribute('onclick') || '').toLowerCase();
          const dataHref = (button.getAttribute('data-href') || '').trim();
          const dataUrl = (button.getAttribute('data-url') || '').trim();
          
          const combinedText = `${text} ${ariaLabel} ${title} ${onclick} ${dataHref} ${dataUrl}`.toLowerCase();
          
          // Check if button contains B2B-related keywords
          const hasB2BKeyword = b2bKeywords.some((keyword: string) => combinedText.includes(keyword));
          
          if (hasB2BKeyword) {
            // Try to extract URL from data attributes or onclick
            let extractedUrl = dataHref || dataUrl;
            if (!extractedUrl && onclick) {
              // Try to extract URL from onclick (simple regex)
              const urlMatch = onclick.match(/(https?:\/\/[^\s"'<>]+|['"]([^'"]+)['"])/);
              if (urlMatch) {
                extractedUrl = urlMatch[1].replace(/['"]/g, '');
              }
            }
            
            if (extractedUrl) {
              try {
                const absoluteUrl = new URL(extractedUrl, currentUrl);
                const urlHostname = absoluteUrl.hostname.toLowerCase();

                const isSameOrSubdomain =
                  urlHostname === baseDomain ||
                  urlHostname.endsWith(`.${baseDomain}`) ||
                  urlHostname.includes(baseName);

                const isExternalCareerHost =
                  externalCareerHosts.some((host: string) => urlHostname.endsWith(host)) &&
                  urlHostname.includes(baseName);

                if (isSameOrSubdomain || isExternalCareerHost) {
                  const normalizedUrl = absoluteUrl.href.split('#')[0].replace(/\/$/, '');
                  if (normalizedUrl && !relevantUrls.includes(normalizedUrl)) {
                    relevantUrls.push(normalizedUrl);
                  }
                }
              } catch (e) {
                // Invalid URL, skip
              }
            }
          }
        }
        
        return relevantUrls;
      }, { domain, currentUrl });
      
      return links as string[];
    } catch (error) {
      // If extraction fails, return empty array
      return [];
    }
  }

  /**
   * Recherche Google "domaine + careers" (ou carrières/jobs) et retourne le premier lien
   * dont l'hôte contient le domaine (site ou sous-domaine du même groupe).
   */
  async discoverCareersUrlViaGoogle(domain: string, page: Page): Promise<string | null> {
    const baseName = domain.split('.')[0];
    const tld = domain.split('.')[1] || 'com';
    const queries = [
      `${baseName} careers`,
      `${baseName} carrières`,
      `${baseName} jobs`,
      `${baseName} recrutement`,
    ];
    for (const q of queries) {
      const searchUrl = `https://www.google.com/search?q=${encodeURIComponent(q)}`;
      try {
        await page.goto(searchUrl, { waitUntil: 'domcontentloaded', timeout: 12000 });
        await page.waitForTimeout(800);
        await this.handleCookiePopup(page, true);

        const firstResult = await page.evaluate((args: { domain: string; baseName: string }) => {
          const doc = (globalThis as any).document;
          const domain = args.domain.toLowerCase();
          const baseName = args.baseName.toLowerCase();
          const skipHosts = ['google.com', 'youtube.com', 'facebook.com', 'linkedin.com', 'twitter.com', 'instagram.com', 'wikipedia.org', 'glassdoor.com', 'indeed.com', 'monster.com'];
          const links = Array.from(doc.querySelectorAll('a[href^="http"]')) as any[];
          for (const a of links) {
            try {
              const href = a.href;
              const u = new URL(href);
              const host = u.hostname.toLowerCase();
              if (skipHosts.some(h => host === h || host.endsWith('.' + h))) continue;
              if (host === domain || host.endsWith('.' + domain) || host.includes(baseName)) {
                return href.split('#')[0].replace(/\/$/, '') || null;
              }
            } catch {
              // ignore
            }
          }
          return null;
        }, { domain: domain.toLowerCase(), baseName });

        if (firstResult) {
          console.log(`  [${domain}] 🔍 Google careers: found ${firstResult}`);
          return firstResult;
        }
      } catch (e) {
        // try next query
      }
    }
    return null;
  }

  /**
   * Depuis une page carrières, trouve les liens vers les listes d'offres (ou confirme que la page actuelle est une liste).
   * Retourne les URLs à crawler (landing + liste(s)).
   */
  async findJobListingPagesFromCareers(page: Page, careersUrl: string, domain: string): Promise<string[]> {
    const baseName = domain.split('.')[0].toLowerCase();
    const out: string[] = [];
    try {
      const listingLinks = await page.evaluate((args: { baseName: string; domain: string; currentUrl: string }) => {
        const doc = (globalThis as any).document;
        const baseName = args.baseName;
        const domain = args.domain;
        const currentUrl = args.currentUrl;
        const keywords = [
          'voir les offres', 'toutes les offres', 'offres d\'emploi', 'liste des offres', 'nos offres', 'nos postes',
          'jobs', 'job openings', 'open positions', 'view jobs', 'see jobs', 'all jobs', 'our openings',
          'carrières', 'rejoignez-nous', 'join us', 'we\'re hiring', 'we are hiring',
        ];
        const links = Array.from(doc.querySelectorAll('a[href]')) as any[];
        const candidates: { url: string; score: number }[] = [];
        for (const a of links) {
          const href = (a.getAttribute('href') || '').trim();
          const text = (a.textContent || '').toLowerCase();
          const aria = (a.getAttribute('aria-label') || '').toLowerCase();
          const combined = `${text} ${aria} ${href}`.toLowerCase();
          const score = keywords.reduce((acc, kw) => acc + (combined.includes(kw) ? 1 : 0), 0);
          if (score > 0 && href && href.startsWith('http')) {
            try {
              const u = new URL(href, currentUrl);
              const host = u.hostname.toLowerCase();
              if (host.includes(baseName) || host.endsWith(domain)) {
                candidates.push({ url: u.href.split('#')[0].replace(/\/$/, ''), score });
              }
            } catch {
              // ignore
            }
          }
        }
        candidates.sort((a, b) => b.score - a.score);
        return [...new Set(candidates.map(c => c.url))].slice(0, 5);
      }, { baseName, domain: domain.toLowerCase(), currentUrl: careersUrl });

      const hasListOnPage = await page.evaluate(() => {
        const doc = (globalThis as any).document;
        const selectors = [
          '[data-job-id]', '[data-offer]', '.job-card', '.job-listing', '.offer-card', '.position-card',
          '.job-list', '.offers-list', '[class*="job"] [class*="list"]', '[class*="offer"]',
          'article[class*="job"]', 'li[class*="job"]', '[data-cy="job-list"]',
        ];
        return selectors.some(sel => {
          try {
            return doc.querySelectorAll(sel).length >= 2;
          } catch {
            return false;
          }
        });
      });

      if (hasListOnPage) {
        out.push(careersUrl);
      }
      listingLinks.forEach(url => {
        if (!out.includes(url)) out.push(url);
      });
    } catch {
      out.push(careersUrl);
    }
    return out.length ? out : [careersUrl];
  }

  /**
   * Sur une page de liste d'offres : clique "Voir plus" / "Load more" / "Expand" tant qu'il y en a,
   * puis récupère les liens de pagination (page 2, 3...) pour les retourner.
   */
  async expandJobListingsPage(page: Page): Promise<{ paginationUrls: string[] }> {
    const paginationUrls: string[] = [];
    const loadMorePatterns = [
      /voir plus|load more|show more|more jobs|plus d'offres|plus d’offres/i,
      /expand|afficher plus/i,
    ];
    let expanded = 0;
    const maxExpand = 10;
    while (expanded < maxExpand) {
      let clicked = false;
      for (const pattern of loadMorePatterns) {
        try {
          const btn = page.getByRole('button', { name: pattern }).or(page.getByRole('link', { name: pattern })).first();
          if (await btn.isVisible({ timeout: 500 })) {
            await btn.click();
            await page.waitForTimeout(1200);
            clicked = true;
            expanded++;
            break;
          }
        } catch {
          // ignore
        }
      }
      if (!clicked) {
        try {
          const byData = page.locator('[data-action="load-more"], .load-more, [aria-label*="more"]').first();
          if (await byData.isVisible({ timeout: 300 })) {
            await byData.click();
            await page.waitForTimeout(1200);
            clicked = true;
            expanded++;
          }
        } catch {
          // ignore
        }
      }
      if (!clicked) break;
    }

    const pagination = await page.evaluate((current: string) => {
      const doc = (globalThis as any).document;
      const currentUrl = current;
      const nextKeywords = ['next', 'suivant', 'suivante', 'page 2', 'page 3', '›', '»'];
      const links = Array.from(doc.querySelectorAll('a[href]')) as any[];
      const urls: string[] = [];
      for (const a of links) {
        const text = (a.textContent || '').toLowerCase();
        const aria = (a.getAttribute('aria-label') || '').toLowerCase();
        const href = a.getAttribute('href') || '';
        const combined = `${text} ${aria}`;
        if (nextKeywords.some(kw => combined.includes(kw)) && href.startsWith('http')) {
          try {
            const u = new URL(href, currentUrl);
            urls.push(u.href.split('#')[0].replace(/\/$/, ''));
          } catch {
            // ignore
          }
        }
      }
      return [...new Set(urls)];
    }, page.url());
    pagination.forEach(u => {
      if (u && !paginationUrls.includes(u)) paginationUrls.push(u);
    });
    return { paginationUrls };
  }

  async probePaths(domain: string, workingPaths: string[] = []): Promise<CrawlResult[]> {
    const baseUrl = `https://${domain}`;
    
    // Set to track visited URLs (to avoid revisiting)
    const visitedUrls = new Set<string>();
    
    // Combine all URLs à tester
    const allUrls: string[] = [];
    
    // 1. Utiliser UNIQUEMENT les working_paths connus (BDD / import)
    // Extract base domain name (without TLD) for matching
    const baseDomainName = domain.split('.')[0]; // manomano.fr -> manomano
    const tld = domain.split('.')[1] || '';
    
    const knownWorkingUrls = workingPaths.filter(url => {
      try {
        const urlObj = new URL(url);
        const urlHostname = urlObj.hostname;
        if (urlHostname === domain) return true;
        if (urlHostname.includes(baseDomainName)) return true;
        if (urlHostname.endsWith(`.${domain}`)) return true;
        return false;
      } catch {
        return false;
      }
    });

    const htmlWorkingUrls = knownWorkingUrls.filter((url) => !isNonHtmlAssetUrl(url));
    const skippedAssetUrls = knownWorkingUrls.filter((url) => isNonHtmlAssetUrl(url));
    if (skippedAssetUrls.length > 0) {
      console.log(
        `  [${domain}] ⏭️  ${skippedAssetUrls.length} asset(s) non-HTML ignoré(s) (PDF, etc.) — les autres pages seront crawlées`,
      );
      for (const assetUrl of skippedAssetUrls) {
        const short = assetUrl.length > 80 ? `${assetUrl.slice(0, 80)}...` : assetUrl;
        console.log(`  [${domain}]     ↳ ${short}`);
      }
    }

    // Ajouter les working paths HTML uniquement
    if (htmlWorkingUrls.length > 0) {
      allUrls.push(...htmlWorkingUrls);
      console.log(
        `  [${domain}] 🎯 Using ${htmlWorkingUrls.length} working path(s) from database/import (no discovery)`,
      );
    } else if (knownWorkingUrls.length > 0) {
      console.log(
        `  [${domain}] ⚪ Tous les working_paths sont des assets non-HTML — fallback homepage`,
      );
    }

    // Garder l'information "gros site" pour le reste de la logique (même si on ne fait plus de discovery)
    const isLargeSite = config.largeDomains.includes(domain.toLowerCase());

    // 2. Si aucun working_path n'est disponible, fallback minimal sur la homepage
    if (allUrls.length === 0) {
      allUrls.push(baseUrl);
      console.log(`  [${domain}] ⚪ No working_paths found, falling back to homepage only`);
    }

    this.currentHttpProxy = getProxyForDomainCrawl();
    if (this.currentHttpProxy) {
      console.log(`  [${domain}] 🔀 Proxy: ${maskProxyUrl(this.currentHttpProxy)}`);
    }

    const results: CrawlResult[] = [];
    const startTime = Date.now();
    
    // Mark initial URLs as visited
    allUrls.forEach(url => visitedUrls.add(url));
    
    // MODE HTTP (seed_builder-like) : pas de Playwright, simple boucle séquentielle sur les URLs
    if (config.httpModeForWorkingPaths) {
      for (let i = 0; i < allUrls.length; i++) {
        const url = allUrls[i];
        const pathStartTime = Date.now();
        const urlObj = new URL(url);
        const displayPath = urlObj.pathname || '/';
        const isSubdomain = urlObj.hostname !== domain;
        const displayName = isSubdomain ? `${urlObj.hostname}${displayPath}` : displayPath;
        const isWorkingPath = htmlWorkingUrls.includes(url);
        const prefix = isWorkingPath ? '🎯' : '';
        console.log(`  [${domain}] ${prefix} Testing ${i + 1}/${allUrls.length}: ${displayName}`);

        const result = await this.crawlUrlFastWithPage(null as any, url);
        const duration = Date.now() - pathStartTime;
        this.logPathResult(domain, displayName, result, duration);
        results.push(result);
      }

      const totalDuration = Date.now() - startTime;
      const successCount = results.filter(r => r.success && !r.isError && !r.isAntibot && !r.isEmpty).length;
      console.log(`  [${domain}] Completed: ${successCount}/${allUrls.length} URLs successful (${totalDuration}ms total, HTTP mode)`);
      return results;
    }
    
    // MODE PLAYWRIGHT (héritage) : fastContexts + pages réutilisées
    const maxConcurrent = config.maxConcurrentPathsPerDomain;
    
    if (maxConcurrent === 1) {
      // Sequential crawling avec réutilisation de la même page pour gagner du temps
      // Créer une seule page pour toutes les URLs du domaine
      if (this.fastContexts.length === 0) {
        throw new Error('Fast context not initialized');
      }
      const ctx = this.getNextContext();
      const fastPage = await ctx.newPage();
      // Mode humain désactivé - humanPage n'est plus utilisé

      // Découverte carrières via Google (sites moyens/petits) : premier lien pertinent "domaine + careers"
      if (!isLargeSite && config.useGoogleCareersDiscovery) {
        try {
          const careersUrl = await this.discoverCareersUrlViaGoogle(domain, fastPage);
          if (careersUrl && !visitedUrls.has(careersUrl)) {
            const gotoOk = await fastPage.goto(careersUrl, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => null);
            if (gotoOk && gotoOk.status() && gotoOk.status()! < 400) {
              await fastPage.waitForTimeout(600);
              await this.handleCookiePopup(fastPage, true);
              const jobListingUrls = await this.findJobListingPagesFromCareers(fastPage, careersUrl, domain);
              const toPrepend = [careersUrl];
              jobListingUrls.forEach(u => { if (!toPrepend.includes(u)) toPrepend.push(u); });
              const { paginationUrls } = await this.expandJobListingsPage(fastPage);
              paginationUrls.forEach(u => { if (u && !toPrepend.includes(u)) toPrepend.push(u); });
              const newOnes = toPrepend.filter(u => !visitedUrls.has(u));
              if (newOnes.length > 0) {
                newOnes.forEach(u => visitedUrls.add(u));
                allUrls.unshift(...newOnes);
                console.log(`  [${domain}] 🔍 Google careers: prepended ${newOnes.length} URL(s) (careers + listes + pagination)`);
              }
            }
          }
        } catch (e: any) {
          console.log(`  [${domain}] 🔍 Google careers discovery skipped: ${e?.message || e}`);
        }
      }

      try {
        for (let i = 0; i < allUrls.length; i++) {
          const url = allUrls[i];
          const pathStartTime = Date.now();
          
          try {
            // Extract display name for logging
            const urlObj = new URL(url);
            const displayPath = urlObj.pathname || '/';
            const isSubdomain = urlObj.hostname !== domain;
            const displayName = isSubdomain ? `${urlObj.hostname}${displayPath}` : displayPath;
            
            // Show special indicator for working paths
            const isWorkingPath = htmlWorkingUrls.includes(url);
            const prefix = isWorkingPath ? '🎯' : '';
            console.log(`  [${domain}] ${prefix} Testing ${i + 1}/${allUrls.length}: ${displayName}`);
            
            // Fast crawl (headless, ~1 seconde max) - réutiliser la même page
            // Mode humain désactivé - utiliser uniquement le mode rapide
            let result = await this.crawlUrlFastWithPage(fastPage, url);
            
            // Si antibot détecté après tentative de bypass
            if (result.isAntibot && result.antibotConfidence && result.antibotConfidence >= 30) {
              console.log(`  [${domain}] 🛡️  Antibot still detected after bypass attempt (${result.antibotConfidence}%) - ${result.antibotReason || 'bypass failed'}`);
            }
            
            const duration = Date.now() - pathStartTime;
            
            // Use URL for logging instead of just path
            this.logPathResult(domain, displayName, result, duration);
            results.push(result);
            
            // Mark URL as visited
            visitedUrls.add(url);

            // Si c'est la homepage d'un domaine en .com et que la page N'EST PAS en français, tester /fr juste après
            if (
              url === baseUrl &&
              tld === 'com' &&
              result.success &&
              result.html &&
              !result.isAntibot &&
              !result.isError
            ) {
              const isFrench = this.isFrenchContent(result.html);
              if (!isFrench) {
                const frUrl = `${baseUrl}/fr`;
                if (!visitedUrls.has(frUrl) && !allUrls.includes(frUrl)) {
                  console.log(`  [${domain}] 🇫🇷 Homepage not detected as French, adding ${frUrl} before other patterns`);
                  allUrls.splice(i + 1, 0, frUrl);
                  visitedUrls.add(frUrl);
                }
              }
            }
            
            // Si c'est une page d'erreur, passer directement à la suivante (ne pas perdre de temps)
            if (result.isError) {
              console.log(`  [${domain}] ⏭️  Error page detected - skipping to next URL`);
              // Pas de délai supplémentaire pour les pages d'erreur - continuer immédiatement
              continue; // Passer à l'URL suivante immédiatement
            }
            
            // Si c'est une page valide avec du contenu B2B, extraire les liens pertinents
            // (jobs, pricing, products, tools, etc.)
            if (result.success && result.relevance && result.html && !result.isEmpty && !result.isError) {
              try {
                // Navigate to the page to extract links (if not already there)
                const currentPageUrl = fastPage.url();
                if (currentPageUrl !== url) {
                  await fastPage.goto(url, { waitUntil: 'domcontentloaded', timeout: 3000 }).catch(() => {});
                }
                
                // Extract relevant links from the page
                const relevantLinks = await this.extractRelevantLinks(fastPage, url, domain);
                
                if (relevantLinks.length > 0) {
                  console.log(`  [${domain}] 🔗 Found ${relevantLinks.length} relevant link(s) on ${displayName}`);
                  
                  // Filter out already visited URLs and add new ones to queue
                  const newLinks = relevantLinks.filter(link => !visitedUrls.has(link));
                  
                  if (newLinks.length > 0) {
                    console.log(`  [${domain}] ➕ Adding ${newLinks.length} new link(s) to crawl queue`);
                    // Add new links to the queue (insert after current position to process them soon)
                    allUrls.splice(i + 1, 0, ...newLinks);
                    // Mark them as visited in the Set to avoid duplicates
                    newLinks.forEach(link => visitedUrls.add(link));
                  }
                }

                // Si la page ressemble à une liste d'offres : expand "Voir plus" / Load more et récupérer la pagination
                const lowerUrl = url.toLowerCase();
                const isJobListingPage = (result.relevanceReasons || []).some(r =>
                  /job|career|emploi|recrut|offre|poste/i.test(r)
                ) || /\/jobs|\/careers|\/offres|\/emplois|\/recrutement|\/positions/i.test(lowerUrl);
                if (isJobListingPage) {
                  try {
                    const { paginationUrls } = await this.expandJobListingsPage(fastPage);
                    const newPagination = paginationUrls.filter(u => !visitedUrls.has(u));
                    if (newPagination.length > 0) {
                      newPagination.forEach(u => visitedUrls.add(u));
                      allUrls.splice(i + 1, 0, ...newPagination);
                      console.log(`  [${domain}] 📄 Added ${newPagination.length} pagination URL(s) from listing page`);
                    }
                  } catch {
                    // best-effort
                  }
                }
              } catch (error: any) {
                // If link extraction fails, continue anyway
                // Don't log error to avoid spam
              }
            }
            
            // Note: On teste TOUS les working paths même si le premier est pertinent
            // (pour avoir plusieurs snapshots et vérifier la cohérence)
            
            // Pas de délai entre URLs en mode rapide - on navigue directement
            // (seulement un petit délai si on a besoin de laisser le navigateur se stabiliser)
            if (i < allUrls.length - 1 && !result.isError) {
              // Délai minimal uniquement si nécessaire (50-100ms)
              await new Promise(resolve => setTimeout(resolve, 50 + Math.random() * 50));
            }
          } catch (error: any) {
            const duration = Date.now() - pathStartTime;
            const urlObj = new URL(url);
            const displayPath = urlObj.pathname || '/';
            const isSubdomain = urlObj.hostname !== domain;
            const displayName = isSubdomain ? `${urlObj.hostname}${displayPath}` : displayPath;
            console.log(`  [${domain}] ❌ ${displayName} - Error: ${error.message} (${duration}ms)`);
            results.push({
              success: false,
              domain_id: '',
              url,
              error: error.message,
            });
          }
        }
      } finally {
        // Fermer les pages à la fin de toutes les URLs
        await fastPage.close();
        // Mode humain désactivé - pas de humanPage à fermer
      }
    } else {
      // Batch crawling with limited concurrency
      let shouldStop = false;
      for (let i = 0; i < allUrls.length && !shouldStop; i += maxConcurrent) {
        const batch = allUrls.slice(i, i + maxConcurrent);
        const batchPromises = batch.map(async (url, batchIndex) => {
          const pathStartTime = Date.now();
          const globalIndex = i + batchIndex;
          
          try {
            // Extract display name for logging
            const urlObj = new URL(url);
            const displayPath = urlObj.pathname || '/';
            const isSubdomain = urlObj.hostname !== domain;
            const displayName = isSubdomain ? `${urlObj.hostname}${displayPath}` : displayPath;
            
            // Show special indicator for working paths
            const isWorkingPath = htmlWorkingUrls.includes(url);
            const prefix = isWorkingPath ? '🎯' : '';
            console.log(`  [${domain}] ${prefix} Testing ${globalIndex + 1}/${allUrls.length}: ${displayName}`);
            
            // Fast crawl (headless, ~1 seconde max)
            // Mode humain désactivé - utiliser uniquement le mode rapide
            let result = await this.crawlUrlFast(url);
            
            // Si antibot détecté après tentative de bypass
            if (result.isAntibot && result.antibotConfidence && result.antibotConfidence >= 30) {
              console.log(`  [${domain}] 🛡️  Antibot still detected after bypass attempt (${result.antibotConfidence}%) - ${result.antibotReason || 'bypass failed'}`);
            }
            
            const duration = Date.now() - pathStartTime;
            
            this.logPathResult(domain, displayName, result, duration);
            
            // Si c'est une page d'erreur, continuer sans délai
            if (result.isError) {
              console.log(`  [${domain}] ⏭️  Error page detected - skipping to next URL`);
              // Pas de délai supplémentaire pour les pages d'erreur
            }
            
            // Note: On teste TOUS les working paths même si le premier est pertinent
            // (pour avoir plusieurs snapshots et vérifier la cohérence)
            
            return result;
          } catch (error: any) {
            const duration = Date.now() - pathStartTime;
            const urlObj = new URL(url);
            const displayPath = urlObj.pathname || '/';
            const isSubdomain = urlObj.hostname !== domain;
            const displayName = isSubdomain ? `${urlObj.hostname}${displayPath}` : displayPath;
            console.log(`  [${domain}] ❌ ${displayName} - Error: ${error.message} (${duration}ms)`);
            return {
              success: false,
              domain_id: '',
              url,
              error: error.message,
            };
          }
        });
        
        const batchResults = await Promise.all(batchPromises);
        results.push(...batchResults);
        
        // Si on a trouvé un working path pertinent, on s'arrête
        if (shouldStop) {
          break;
        }
        
        // Random delay between batches (human-like, 5-10 seconds)
        if (i + maxConcurrent < allUrls.length && !shouldStop) {
          const delay = Math.random() * 5000 + 5000; // 5-10 seconds
          await new Promise(resolve => setTimeout(resolve, delay));
        }
      }
    }

    const totalDuration = Date.now() - startTime;
    const successCount = results.filter(r => r.success).length;
    const relevantCount = results.filter(r => r.success && r.relevance).length;
    console.log(`  [${domain}] Completed: ${successCount}/${allUrls.length} URLs successful, ${relevantCount} relevant (${totalDuration}ms total)`);

    return results;
  }
}
