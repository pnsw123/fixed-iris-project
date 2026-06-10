import { describe, it, expect } from 'vitest';
import { cn } from '../lib/cn';

describe('cn', () => {
    it('returns empty string for no inputs', () => {
        expect(cn()).toBe('');
    });

    it('merges single class string', () => {
        expect(cn('foo')).toBe('foo');
    });

    it('merges multiple class strings', () => {
        expect(cn('foo', 'bar')).toBe('foo bar');
    });

    it('deduplicates conflicting tailwind classes (last wins)', () => {
        // tailwind-merge: later class wins over earlier for same property
        expect(cn('p-2', 'p-4')).toBe('p-4');
    });

    it('handles undefined and null gracefully', () => {
        expect(cn(undefined, null, 'foo')).toBe('foo');
    });

    it('handles conditional classes via object syntax', () => {
        expect(cn({ 'text-red-500': true, 'text-blue-500': false })).toBe('text-red-500');
    });

    it('handles conditional classes via array syntax', () => {
        expect(cn(['foo', undefined, 'bar'])).toBe('foo bar');
    });

    it('merges bg utilities correctly', () => {
        expect(cn('bg-red-500', 'bg-blue-500')).toBe('bg-blue-500');
    });
});
