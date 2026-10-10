/** Extensions de fichiers non-HTML à exclure du crawl / snapshots. */
const NON_HTML_ASSET_PATTERN =
  /\.(pdf|zip|doc|docx|xls|xlsx|ppt|pptx|png|jpe?g|gif|webp|svg|ico|mp4|mp3|woff2?|ttf|eot|csv|rss|atom)($|[?#])/i;

/** Strip bytes invalid in PostgreSQL UTF-8 text columns. */
export function sanitizeTextForStorage(text: string): string {
  if (!text) return '';
  return text.replace(/\x00/g, '');
}

/** URL pointant vers un asset binaire (PDF, image, etc.) — ne pas crawler ni snapshotter. */
export function isNonHtmlAssetUrl(url: string): boolean {
  try {
    const pathname = new URL(url).pathname;
    return NON_HTML_ASSET_PATTERN.test(pathname);
  } catch {
    return NON_HTML_ASSET_PATTERN.test(url);
  }
}

/** Garde uniquement les URLs HTML crawlables. */
export function filterHtmlWorkingPaths(urls: string[]): string[] {
  return urls.filter((url) => !isNonHtmlAssetUrl(url));
}

export function isNonHtmlBinaryContent(
  body: string,
  url: string,
  contentType?: string,
): boolean {
  if (isNonHtmlAssetUrl(url)) {
    return true;
  }
  const ct = (contentType || '').toLowerCase();
  if (
    ct.includes('application/pdf') ||
    ct.includes('application/octet-stream') ||
    ct.includes('application/zip') ||
    ct.startsWith('image/') ||
    ct.startsWith('video/') ||
    ct.startsWith('audio/')
  ) {
    return true;
  }
  const head = body.slice(0, 512);
  if (head.startsWith('%PDF')) {
    return true;
  }
  // NUL byte = binaire reçu comme texte
  if (body.includes('\x00')) {
    return true;
  }
  return false;
}

/** Résultat HTTP eligible pour un snapshot HTML. */
export function isSnapshotableHtml(
  body: string,
  url: string,
  contentType?: string,
): boolean {
  return !isNonHtmlBinaryContent(body, url, contentType);
}
