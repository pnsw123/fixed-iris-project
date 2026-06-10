'use client';

import { useEffect } from 'react';

export default function GlobalSafetyGuards() {
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const w = window as typeof window & Record<string, unknown>;

    // Stub Firefox-specific globals some extensions expect
    if (typeof w.__firefox__ !== 'object' || w.__firefox__ === null) {
      w.__firefox__ = {};
    }
    const firefox = w.__firefox__ as Record<string, unknown>;
    const ensureNoop = (key: string) => {
      if (typeof firefox[key] !== 'function') {
        firefox[key] = () => {};
      }
    };
    ['reader', 'playlistLongPressed', 'playlistLongPressed_4EF4B7DBEAC9443494EFE28374491B42'].forEach(
      ensureNoop,
    );
    if (typeof w.firefox !== 'object') {
      w.firefox = {};
    }

    // Stub ethereum provider if absent so code that touches selectedAddress doesn't crash
    if (typeof w.ethereum === 'undefined') {
      w.ethereum = { selectedAddress: undefined };
    } else if (w.ethereum && typeof w.ethereum === 'object' && !('selectedAddress' in w.ethereum)) {
      (w.ethereum as Record<string, unknown>).selectedAddress = undefined;
    }
  }, []);

  return null;
}
