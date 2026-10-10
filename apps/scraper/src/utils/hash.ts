import crypto from 'crypto';
import { processHtmlForHashing } from './normalizeHtml';
import { config } from '../config';

/**
 * Hash content (HTML or text)
 * If content looks like HTML and normalization/extraction is enabled, process it first
 */
export function hashContent(content: string): string {
  if (!content) {
    return crypto.createHash('sha256').update('').digest('hex');
  }

  // Check if content is HTML (simple heuristic)
  const isHtml = content.trim().startsWith('<!') || 
                 content.includes('<html') || 
                 content.includes('<body') ||
                 (content.includes('<') && content.includes('>'));

  let contentToHash = content;

  // Apply HTML processing if enabled and content is HTML
  if (isHtml && (config.normalizeHtml || config.extractStableContent)) {
    contentToHash = processHtmlForHashing(content, {
      normalize: config.normalizeHtml,
      extractStableContent: config.extractStableContent,
    });
  }

  return crypto.createHash('sha256').update(contentToHash).digest('hex');
}
