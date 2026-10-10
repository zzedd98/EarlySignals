/**
 * HTML normalization utilities for stable hashing
 * Removes dynamic content that changes between requests but doesn't affect the actual content
 */

/**
 * Normalize HTML by removing dynamic/temporary content:
 * - Timestamps (dates, times)
 * - Random IDs, nonces, CSRF tokens
 * - Session IDs
 * - Analytics/tracking IDs
 * - Cache busters
 * - Dynamic counters
 */
export function normalizeHtml(html: string): string {
  if (!html) return '';

  let normalized = html;

  // Remove random IDs and nonces (common patterns) - DO THIS FIRST
  // Cloudflare email protection (data-cfemail) - normalize to constant value
  normalized = normalized.replace(/data-cfemail=["'][a-f0-9]+["']/gi, 'data-cfemail="[CF_EMAIL]"');
  // Other data-* attributes with random-looking values
  normalized = normalized.replace(/data-[a-z-]+="[a-f0-9]{8,}"/gi, '');
  normalized = normalized.replace(/data-[a-z-]+='[a-f0-9]{8,}'/gi, '');
  // CSRF tokens
  normalized = normalized.replace(/csrf[_-]?token=["'][^"']+["']/gi, 'csrf-token="[TOKEN]"');
  normalized = normalized.replace(/<input[^>]*name=["']csrf[_-]?token["'][^>]*>/gi, '');
  // Nonces
  normalized = normalized.replace(/nonce=["'][^"']+["']/gi, 'nonce="[NONCE]"');
  // Session IDs
  normalized = normalized.replace(/session[_-]?id=["'][^"']+["']/gi, 'session-id="[SESSION]"');
  normalized = normalized.replace(/PHPSESSID=[a-z0-9]+/gi, 'PHPSESSID=[SESSION]');
  
  // ---------------------------------------------------------------------------
  // Generic ID normalization (site-agnostic) - DO THIS BEFORE TIMESTAMPS
  // ---------------------------------------------------------------------------
  // Normalize ALL IDs in HTML attributes BEFORE normalizing timestamps
  // This ensures IDs containing timestamps are normalized correctly
  
  // 1) Tous les attributs id="..." (avec ou sans espaces avant)
  // Pattern: id="..." ou id='...' (fonctionne même si id est le premier attribut)
  normalized = normalized.replace(/\bid\s*=\s*["']([^"']+)["']/gi, 'id="[ID]"');

  // 2) Références vers ces IDs via des ancres / attributs ARIA
  normalized = normalized.replace(
    /(href|for|aria-controls|aria-labelledby)\s*=\s*["']#[^"']+["']/gi,
    '$1="#[ID]"',
  );

  // 3) data-id / data-*id* qui contiennent des identifiants internes
  normalized = normalized.replace(
    /data-[a-z0-9_-]*id[a-z0-9_-]*\s*=\s*["'][^"']+["']/gi,
    (m) => m.replace(/=\s*["'][^"']+["']/, '="[DATA_ID]"'),
  );

  // Remove analytics/tracking IDs
  normalized = normalized.replace(/data-[a-z-]*track[^=]*=["'][^"']+["']/gi, '');
  normalized = normalized.replace(/data-[a-z-]*analytics[^=]*=["'][^"']+["']/gi, '');
  normalized = normalized.replace(/data-[a-z-]*gtm[^=]*=["'][^"']+["']/gi, '');
  normalized = normalized.replace(/data-[a-z-]*ga[^=]*=["'][^"']+["']/gi, '');

  // Remove cache busters in URLs
  normalized = normalized.replace(/[?&]_=\d+/g, '');
  normalized = normalized.replace(/[?&]cache[_-]?buster=\d+/gi, '');
  normalized = normalized.replace(/[?&]v=\d+/g, '');

  // Remove dynamic counters (visitors online, etc.)
  normalized = normalized.replace(/\d+ (?:visiteur|visiteurs|visitor|visitors) (?:en ligne|online)/gi, '[COUNTER] visitors online');
  normalized = normalized.replace(/\d+ (?:personne|personnes|people) (?:en ligne|online)/gi, '[COUNTER] people online');

  // Remove random UUIDs (but keep structure)
  normalized = normalized.replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, '[UUID]');

  // Remove timestamps in various formats - DO THIS AFTER ID NORMALIZATION
  // YYYY-MM-DD HH:MM:SS
  normalized = normalized.replace(/\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?/g, '[TIMESTAMP]');
  // Unix timestamps (10 or 13 digits) - but NOT inside already normalized IDs
  normalized = normalized.replace(/\b\d{10,13}\b/g, '[TIMESTAMP]');
  // ISO dates
  normalized = normalized.replace(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?/g, '[TIMESTAMP]');
  // Relative times like "il y a 5 minutes"
  normalized = normalized.replace(/il y a \d+ (?:seconde|secondes|minute|minutes|heure|heures|jour|jours)/gi, '[RELATIVE_TIME]');
  normalized = normalized.replace(/\d+ (?:second|seconds|minute|minutes|hour|hours|day|days) ago/gi, '[RELATIVE_TIME]');

  // Normalize IDs and dynamic values in script tags BEFORE removing them
  // This ensures HubSpot form IDs and other dynamic IDs in scripts are normalized
  normalized = normalized.replace(/<script[^>]*>([\s\S]*?)<\/script>/gi, (match, scriptContent) => {
    // Keep script tags with src (external scripts) - just remove content
    if (match.includes('src=')) {
      return match.replace(/<script([^>]*src=[^>]*)>[\s\S]*?<\/script>/gi, '<script$1></script>');
    }
    
    // For inline scripts, normalize ALL ID references
    let normalizedContent = scriptContent;
    
    // Normalize ALL target attributes pointing to IDs (format: target: "#any-id")
    normalizedContent = normalizedContent.replace(/target:\s*["']#[^"']+["']/gi, 'target: "#[ID]"');
    
    // Normalize ALL string references to IDs (format: "#any-id" or '#any-id')
    normalizedContent = normalizedContent.replace(/["']#([^"']+)["']/gi, '"#[ID]"');
    
    // Remove the normalized script content entirely (after normalization)
    return '';
  });

  // Remove style tags with inline styles (can contain dynamic values)
  normalized = normalized.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '<style></style>');

  // Normalize whitespace (multiple spaces -> single space, normalize line breaks)
  normalized = normalized.replace(/\s+/g, ' ').trim();

  return normalized;
}

/**
 * Extract stable content from HTML using CSS selectors
 * Focuses on main content areas, ignoring headers, footers, sidebars, ads
 */
export function extractStableContent(html: string): string {
  if (!html) return '';

  try {
    // Simple regex-based extraction (no external dependencies)
    // We'll extract common content selectors
    
    let content = '';

    // Priority selectors for main content (in order of preference)
    const contentSelectors = [
      'main',
      'article',
      '[role="main"]',
      '.content',
      '.main-content',
      '#content',
      '#main',
      '.post',
      '.page-content',
      'section',
    ];

    // Try to find main content area
    for (const selector of contentSelectors) {
      // Simple regex matching (not perfect but works for most cases)
      const patterns = [
        new RegExp(`<main[^>]*>([\\s\\S]*?)<\\/main>`, 'i'),
        new RegExp(`<article[^>]*>([\\s\\S]*?)<\\/article>`, 'i'),
        new RegExp(`<div[^>]*role=["']main["'][^>]*>([\\s\\S]*?)<\\/div>`, 'i'),
        new RegExp(`<div[^>]*class=["'][^"']*content[^"']*["'][^>]*>([\\s\\S]*?)<\\/div>`, 'i'),
        new RegExp(`<div[^>]*id=["']content["'][^>]*>([\\s\\S]*?)<\\/div>`, 'i'),
        new RegExp(`<div[^>]*id=["']main["'][^>]*>([\\s\\S]*?)<\\/div>`, 'i'),
        new RegExp(`<section[^>]*>([\\s\\S]*?)<\\/section>`, 'i'),
      ];

      for (const pattern of patterns) {
        const match = html.match(pattern);
        if (match && match[1] && match[1].trim().length > 100) {
          // Found substantial content, use it
          content = match[1];
          break;
        }
      }
      if (content) break;
    }

    // If no main content found, extract body but remove common dynamic areas
    if (!content || content.length < 100) {
      // Extract body
      const bodyMatch = html.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
      if (bodyMatch) {
        let bodyContent = bodyMatch[1];
        
        // Remove common dynamic/non-content areas
        const removePatterns = [
          /<header[^>]*>[\s\S]*?<\/header>/gi,
          /<footer[^>]*>[\s\S]*?<\/footer>/gi,
          /<nav[^>]*>[\s\S]*?<\/nav>/gi,
          /<aside[^>]*>[\s\S]*?<\/aside>/gi,
          /<div[^>]*class=["'][^"']*(?:header|footer|nav|sidebar|ad|advertisement|banner|cookie)[^"']*["'][^>]*>[\s\S]*?<\/div>/gi,
          /<script[^>]*>[\s\S]*?<\/script>/gi,
          /<style[^>]*>[\s\S]*?<\/style>/gi,
        ];

        for (const pattern of removePatterns) {
          bodyContent = bodyContent.replace(pattern, '');
        }

        content = bodyContent;
      } else {
        // Fallback: use entire HTML
        content = html;
      }
    }

    // Clean up: remove HTML tags, keep only text content
    // But preserve structure for better comparison
    // Remove script/style/comment tags
    content = content.replace(/<!--[\s\S]*?-->/g, '');
    content = content.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
    content = content.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');

    // Normalize whitespace
    content = content.replace(/\s+/g, ' ').trim();

    return content;
  } catch (error) {
    // If extraction fails, return normalized full HTML
    return normalizeHtml(html);
  }
}

/**
 * Process HTML for stable hashing:
 * - Optionally normalize (remove dynamic content)
 * - Optionally extract stable content (main content only)
 */
export function processHtmlForHashing(
  html: string,
  options: {
    normalize: boolean;
    extractStableContent: boolean;
  }
): string {
  if (!html) return '';

  let processed = html;

  // Normalize FIRST to remove all dynamic IDs, timestamps, etc.
  // This ensures IDs are normalized before content extraction
  if (options.normalize) {
    processed = normalizeHtml(processed);
  }

  // Extract stable content AFTER normalization
  // This focuses on main content areas, ignoring headers/footers/ads
  if (options.extractStableContent) {
    processed = extractStableContent(processed);
  }

  return processed;
}
