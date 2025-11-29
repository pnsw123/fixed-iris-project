'use client';

import { useSearchParams } from 'next/navigation';

export function useDebugMode(): boolean {
    const searchParams = useSearchParams();
    return searchParams.get('debug') === 'true';
}
