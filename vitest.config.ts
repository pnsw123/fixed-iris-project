import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
    test: {
        environment: 'node',
        globals: false,
        include: ['src/tests/**/*.test.ts', 'src/tests/**/*.test.tsx'],
        exclude: ['node_modules', '.next'],
    },
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
});
