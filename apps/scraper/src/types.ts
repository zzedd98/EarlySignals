export interface Domain {
  id: string;
  domain: string;
  org_id: string | null;
  status: string;
  last_crawled_at: string | null;
}

export interface Snapshot {
  domain_id: string;
  url: string;
  status_code: number;
  html: string;
  hash: string;
  extracted_json?: Record<string, any>;
}

export interface CrawlResult {
  success: boolean;
  domain_id: string;
  url: string;
  status_code?: number;
  error?: string;
  html?: string;
  hash?: string;
  // Relevance analysis
  relevance?: boolean;
  relevanceScore?: number;
  relevanceReasons?: string[];
  isEmpty?: boolean;
  isError?: boolean;
  // Antibot detection
  isAntibot?: boolean;
  antibotConfidence?: number;
  antibotReason?: string;
}
