/**
 * Simple concurrency limiter (replacement for p-limit in CommonJS)
 */
export class ConcurrencyLimiter {
  private queue: Array<() => Promise<void>> = [];
  private running = 0;
  private limit: number;

  constructor(limit: number) {
    this.limit = limit;
  }

  async add<T>(fn: () => Promise<T>): Promise<T> {
    return new Promise((resolve, reject) => {
      this.queue.push(async () => {
        try {
          const result = await fn();
          resolve(result);
        } catch (error) {
          reject(error);
        } finally {
          this.running--;
          this.processQueue();
        }
      });
      this.processQueue();
    });
  }

  private processQueue(): void {
    if (this.running >= this.limit || this.queue.length === 0) {
      return;
    }

    this.running++;
    const task = this.queue.shift();
    if (task) {
      task();
    }
  }
}

export function createLimit(concurrency: number) {
  const limiter = new ConcurrencyLimiter(concurrency);
  return <T>(fn: () => Promise<T>) => limiter.add(fn);
}
