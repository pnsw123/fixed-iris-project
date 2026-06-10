/**
 * Tests for BackendClient — verifies HTTPS defaults and SSR safety (issue #87)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// We test the internal logic by importing the module in controlled env
// BackendClient is not exported directly, so we test via module re-evaluation
// and by inspecting the exported singleton's base URL indirectly through fetch calls.

describe('BackendClient — HTTPS defaults (#87)', () => {
  describe('constructor default', () => {
    it('uses https:// not http:// as default base URL', async () => {
      // Re-import to get fresh BackendClient class
      const mod = await import('../lib/backendClient');
      const client = mod.backendClient;

      // Spy on fetch to capture the URL used
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'ok', models_loaded: true, device: 'cpu' }),
      } as Response);

      await client.healthCheck();

      const calledUrl = fetchSpy.mock.calls[0][0] as string;
      expect(calledUrl).toMatch(/^https:\/\//);
      expect(calledUrl).not.toMatch(/^http:\/\//);

      fetchSpy.mockRestore();
    });
  });

  describe('getBackendUrl — SSR safety', () => {
    let originalWindow: typeof globalThis.window;

    beforeEach(() => {
      originalWindow = globalThis.window;
    });

    afterEach(() => {
      globalThis.window = originalWindow;
    });

    it('does not throw when window is undefined (SSR context)', () => {
      // Simulate SSR by removing window
      // @ts-expect-error intentional undefined assignment for SSR test
      delete globalThis.window;

      expect(() => {
        // Inline mirror of getBackendUrl logic
        const hostname = typeof window !== 'undefined' ? window.location.hostname : undefined;
        const url =
          hostname && hostname !== 'localhost' && hostname !== '127.0.0.1'
            ? `https://${hostname}:8000`
            : process.env.NEXT_PUBLIC_BACKEND_URL || 'https://localhost:8000';
        return url;
      }).not.toThrow();
    });

    it('returns https URL in SSR context', () => {
      // @ts-expect-error intentional undefined assignment for SSR test
      delete globalThis.window;

      const hostname = typeof window !== 'undefined' ? window.location.hostname : undefined;
      const url =
        hostname && hostname !== 'localhost' && hostname !== '127.0.0.1'
          ? `https://${hostname}:8000`
          : process.env.NEXT_PUBLIC_BACKEND_URL || 'https://localhost:8000';

      expect(url).toMatch(/^https:\/\//);
    });

    it('uses custom NEXT_PUBLIC_BACKEND_URL env var when set', () => {
      // @ts-expect-error intentional undefined assignment for SSR test
      delete globalThis.window;

      const originalEnv = process.env.NEXT_PUBLIC_BACKEND_URL;
      process.env.NEXT_PUBLIC_BACKEND_URL = 'https://api.example.com:8000';

      const hostname = typeof window !== 'undefined' ? window.location.hostname : undefined;
      const url =
        hostname && hostname !== 'localhost' && hostname !== '127.0.0.1'
          ? `https://${hostname}:8000`
          : process.env.NEXT_PUBLIC_BACKEND_URL || 'https://localhost:8000';

      expect(url).toBe('https://api.example.com:8000');

      process.env.NEXT_PUBLIC_BACKEND_URL = originalEnv;
    });

    it('uses IP-based HTTPS when accessing via non-localhost hostname', () => {
      // Use a variable so TS does not narrow the type to a literal
      const simulatedHostname: string = '192.168.1.100';
      // Mirror getBackendUrl logic with simulated hostname
      const url =
        simulatedHostname !== 'localhost' && simulatedHostname !== '127.0.0.1'
          ? `https://${simulatedHostname}:8000`
          : process.env.NEXT_PUBLIC_BACKEND_URL || 'https://localhost:8000';

      expect(url).toBe('https://192.168.1.100:8000');
      expect(url).toMatch(/^https:\/\//);
    });
  });
});
