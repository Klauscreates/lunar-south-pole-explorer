/** Session-scoped, bounded cache. Only fulfilled, validated resources are retained.
 * One panel closing must not cancel a request another panel is waiting on.
 */
export function sharedResource<T>(limit = 5) {
  const entries = new Map<string, Promise<T>>();
  return (key: string, load: () => Promise<T>, signal: AbortSignal): Promise<T> => {
    if (signal.aborted) return Promise.reject(signal.reason);
    let pending = entries.get(key);
    if (!pending) {
      pending = Promise.resolve().then(load);
      entries.set(key, pending);
      const current = pending;
      void pending.catch(() => { if (entries.get(key) === current) entries.delete(key); });
      if (entries.size > limit) entries.delete(entries.keys().next().value!);
    }
    const result = pending;
    return new Promise<T>((resolve, reject) => {
      const aborted = () => { cleanup(); reject(signal.reason); };
      const cleanup = () => signal.removeEventListener("abort", aborted);
      signal.addEventListener("abort", aborted, { once: true });
      result.then(value => { cleanup(); resolve(value); }, error => { cleanup(); reject(error); });
    });
  };
}
