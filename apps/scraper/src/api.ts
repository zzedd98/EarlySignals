import axios from 'axios';
import { config } from './config';
import { Snapshot } from './types';

const apiClient = axios.create({
  baseURL: config.apiUrl,
  headers: {
    'Content-Type': 'application/json',
  },
});

let accessToken: string | null = null;

/**
 * Authenticate with the API and get an access token
 */
export async function authenticate(): Promise<void> {
  try {
    console.log(`  → Connecting to ${config.apiUrl}/api/v1/auth/login...`);
    const response = await apiClient.post('/api/v1/auth/login', {
      email: config.apiEmail,
      password: config.apiPassword,
    }, {
      timeout: 10000, // 10 second timeout
    });
    accessToken = response.data.access_token;
    // Set default authorization header
    apiClient.defaults.headers.common['Authorization'] = `Bearer ${accessToken}`;
    console.log('  ✅ Authenticated successfully');
  } catch (error: any) {
    if (error.code === 'ECONNREFUSED') {
      console.error('  ❌ Connection refused - Is the API running on', config.apiUrl, '?');
    } else if (error.code === 'ETIMEDOUT' || error.message.includes('timeout')) {
      console.error('  ❌ Authentication timeout - API not responding');
    } else {
      console.error('  ❌ Authentication failed:', error.response?.data || error.message);
    }
    throw new Error('Failed to authenticate with API');
  }
}

/**
 * Ensure we have a valid token, authenticate if needed
 */
async function ensureAuthenticated(): Promise<void> {
  if (!accessToken) {
    await authenticate();
  }
}

export interface DomainCountResult {
  total: number;
  active: number;
}

export interface GetDomainsOptions {
  skip?: number;
  limit?: number;
  statusFilter?: string;
}

export async function getDomainCount(): Promise<DomainCountResult> {
  await ensureAuthenticated();
  const response = await apiClient.get('/api/v1/domains/count', { timeout: 10000 });
  return response.data as DomainCountResult;
}

export async function getDomainsToCrawl(options: GetDomainsOptions = {}): Promise<any[]> {
  const maxRetries = 3;
  let lastError: any = null;
  const skip = options.skip ?? 0;
  const limit = options.limit ?? config.batchSize;
  const statusFilter = options.statusFilter ?? 'active';

  console.log(`  → Fetching domains from API (skip=${skip}, limit=${limit})...`);
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      if (attempt > 1) {
        console.log(`  → Retry attempt ${attempt}/${maxRetries}...`);
      }
      await ensureAuthenticated();
      const response = await apiClient.get('/api/v1/domains', {
        params: {
          status_filter: statusFilter,
          skip,
          limit,
        },
        timeout: 10000, // 10 second timeout
      });
      console.log(`  ✅ Received ${response.data.length} domain(s)`);
      return response.data;
    } catch (error: any) {
      lastError = error;
      
      // If 401, try to re-authenticate
      if (error.response?.status === 401) {
        console.log('Token expired, re-authenticating...');
        accessToken = null;
        try {
          await authenticate();
          continue; // Retry the request
        } catch (authError) {
          console.error('Re-authentication failed:', authError);
          return [];
        }
      }

      // If connection error, wait and retry
      if (error.code === 'ECONNRESET' || error.code === 'ECONNREFUSED' || !error.response) {
        if (attempt < maxRetries) {
          console.log(`  ⚠️  Connection error (attempt ${attempt}/${maxRetries}), retrying in 2s...`);
          if (error.code === 'ECONNREFUSED') {
            console.log(`  → Is the API running on ${config.apiUrl}?`);
          }
          await new Promise(resolve => setTimeout(resolve, 2000));
          continue;
        }
      }

      // For other errors, log and return empty
      if (attempt === maxRetries) {
        console.error('  ❌ Error fetching domains after retries:', error.message || error);
        if (error.response) {
          console.error('  → API response:', error.response.status, error.response.statusText);
        }
        return [];
      }
    }
  }

  console.error('  ❌ Error fetching domains:', lastError?.message || lastError);
  return [];
}

/**
 * Get latest snapshots for given domain IDs (for cache - efficient batch loading)
 * Returns a map: (domain_id, url) -> hash
 */
export async function getLatestSnapshotsByDomains(domainIds: string[]): Promise<Map<string, string>> {
  if (domainIds.length === 0) {
    return new Map();
  }

  const maxRetries = 3;
  let lastError: any = null;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      if (attempt > 1) {
        console.log(`  → Retry loading snapshots cache (attempt ${attempt}/${maxRetries})...`);
      }
      await ensureAuthenticated();
      
      // Batch load: get latest snapshot per (domain_id, url) for these domains
      const response = await apiClient.get('/api/v1/snapshots', {
        params: {
          domain_ids: domainIds.join(','),
          limit: 1000, // Get up to 1000 latest snapshots across all domains
        },
        timeout: 30000, // 30 second timeout for batch load
      });

      // Build map: (domain_id, url) -> hash
      // Only keep the latest snapshot per (domain_id, url) (API returns ordered by fetched_at DESC)
      const snapshotMap = new Map<string, string>();
      const seen = new Set<string>();

      for (const snapshot of response.data) {
        const key = `${snapshot.domain_id}|${snapshot.url}`;
        if (!seen.has(key)) {
          seen.add(key);
          snapshotMap.set(key, snapshot.hash);
        }
      }

      return snapshotMap;
    } catch (error: any) {
      lastError = error;
      
      if (error.response?.status === 401) {
        accessToken = null;
        try {
          await authenticate();
          continue; // Retry
        } catch (authError) {
          console.error('Re-authentication failed:', authError);
          return new Map(); // Return empty cache on auth failure
        }
      }

      if (attempt < maxRetries && (error.code === 'ECONNRESET' || error.code === 'ECONNREFUSED' || !error.response)) {
        console.log(`  ⚠️  Connection error loading cache (attempt ${attempt}/${maxRetries}), retrying in 2s...`);
        await new Promise(resolve => setTimeout(resolve, 2000));
        continue;
      }
    }
  }

  console.warn('  ⚠️  Failed to load snapshot cache, continuing without cache:', lastError?.message || lastError);
  return new Map(); // Return empty cache on failure (scraper will still work, just less efficient)
}

export async function saveSnapshot(snapshot: Snapshot): Promise<void> {
  try {
    await ensureAuthenticated();
    await apiClient.post('/api/v1/snapshots', snapshot);
  } catch (error: any) {
    if (error.response?.status === 401) {
      accessToken = null;
      await authenticate();
      // Retry once
      await apiClient.post('/api/v1/snapshots', snapshot);
      return;
    }
    console.error('Error saving snapshot:', error.response?.data || error.message);
    throw error;
  }
}

/**
 * Save multiple snapshots in chunked bulk requests (évite 500 payload too large).
 * Returns the total number of snapshots actually saved.
 */
export async function saveSnapshotsBulk(
  snapshots: Snapshot[],
  chunkSize: number = 20,
): Promise<number> {
  if (snapshots.length === 0) {
    return 0;
  }

  const size = Math.max(1, chunkSize);
  let totalSaved = 0;
  const totalChunks = Math.ceil(snapshots.length / size);

  for (let i = 0; i < snapshots.length; i += size) {
    const chunk = snapshots.slice(i, i + size);
    const chunkIndex = Math.floor(i / size) + 1;
    console.log(
      `  📤 Bulk chunk ${chunkIndex}/${totalChunks} (${chunk.length} snapshot(s))...`,
    );
    const saved = await saveSnapshotsBulkOnce(chunk);
    totalSaved += saved;
  }

  return totalSaved;
}

async function saveSnapshotsBulkOnce(snapshots: Snapshot[]): Promise<number> {
  if (snapshots.length === 0) {
    return 0;
  }

  const maxRetries = 3;
  let lastError: any = null;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      if (attempt > 1) {
        console.log(`  → Retry bulk save (attempt ${attempt}/${maxRetries})...`);
      }
      await ensureAuthenticated();

      const response = await apiClient.post(
        '/api/v1/snapshots/bulk',
        { snapshots },
        { timeout: 120000 },
      );

      const savedCount =
        typeof response.data?.saved_count === 'number'
          ? response.data.saved_count
          : Array.isArray(response.data)
            ? response.data.length
            : 0;
      const failedCount =
        typeof response.data?.failed_count === 'number' ? response.data.failed_count : 0;
      if (failedCount > 0) {
        console.warn(
          `  ⚠️  Bulk chunk: ${savedCount} saved, ${failedCount} row(s) skipped (invalid content)`,
        );
      }
      return savedCount;
    } catch (error: any) {
      lastError = error;

      if (error.response?.status === 401) {
        accessToken = null;
        try {
          await authenticate();
          continue;
        } catch (authError) {
          console.error('Re-authentication failed:', authError);
          throw new Error('Failed to authenticate for bulk save');
        }
      }

      if (
        attempt < maxRetries &&
        (error.code === 'ECONNRESET' || error.code === 'ECONNREFUSED' || !error.response)
      ) {
        console.log(
          `  ⚠️  Connection error during bulk save (attempt ${attempt}/${maxRetries}), retrying in 2s...`,
        );
        await new Promise((resolve) => setTimeout(resolve, 2000));
        continue;
      }

      if (attempt === maxRetries) {
        const detail = error.response?.data
          ? JSON.stringify(error.response.data)
          : error.message;
        console.error('  ❌ Error saving snapshots in bulk:', detail);
        throw error;
      }
    }
  }

  throw lastError || new Error('Failed to save snapshots in bulk');
}

export async function updateDomainCrawlTime(domainId: string): Promise<void> {
  try {
    await ensureAuthenticated();
    await apiClient.patch(`/api/v1/domains/${domainId}`, {
      last_crawled_at: new Date().toISOString(),
    });
  } catch (error: any) {
    if (error.response?.status === 401) {
      accessToken = null;
      await authenticate();
      // Retry once
      await apiClient.patch(`/api/v1/domains/${domainId}`, {
        last_crawled_at: new Date().toISOString(),
      });
      return;
    }
    console.error('Error updating domain crawl time:', error);
  }
}

export async function markDomainError(domainId: string, error: string): Promise<void> {
  try {
    await ensureAuthenticated();
    // First get current error_count, then increment
    const domainResponse = await apiClient.get(`/api/v1/domains/${domainId}`);
    const currentErrorCount = domainResponse.data.error_count || 0;
    
    await apiClient.patch(`/api/v1/domains/${domainId}`, {
      error_count: currentErrorCount + 1,
      last_error: error,
    });
  } catch (err: any) {
    if (err.response?.status === 401) {
      accessToken = null;
      await authenticate();
      // Retry once
      try {
        const domainResponse = await apiClient.get(`/api/v1/domains/${domainId}`);
        const currentErrorCount = domainResponse.data.error_count || 0;
        await apiClient.patch(`/api/v1/domains/${domainId}`, {
          error_count: currentErrorCount + 1,
          last_error: error,
        });
        return;
      } catch (retryErr) {
        console.error('Error marking domain error after re-auth:', retryErr);
      }
    }
    console.error('Error marking domain error:', err);
  }
}

export async function updateDomainWorkingPaths(domainId: string, workingPaths: string[]): Promise<void> {
  try {
    await ensureAuthenticated();
    await apiClient.patch(`/api/v1/domains/${domainId}`, {
      working_paths: workingPaths,
    }, { timeout: 10000 });
  } catch (error: any) {
    if (error.response?.status === 401) {
      accessToken = null;
      await authenticate();
      // Retry once
      await apiClient.patch(`/api/v1/domains/${domainId}`, {
        working_paths: workingPaths,
      }, { timeout: 10000 });
      return;
    }
    console.error('  ❌ Error updating domain working paths:', error.response?.data || error.message);
    // Don't throw - this is not critical
  }
}
