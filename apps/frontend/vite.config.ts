import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const repoRoot = path.resolve(__dirname, '../..');
  const env = loadEnv(mode, repoRoot, '');
  const apiTarget = env.VITE_API_TARGET || 'http://localhost:8000';
  return {
    envDir: repoRoot,
    server: {
      port: 3000,
      host: '0.0.0.0',
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
        '@shared': path.resolve(__dirname, '../../packages/shared/src'),
      }
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: './vitest.setup.ts',
      pool: 'forks',
      poolOptions: {
        forks: {
          singleFork: true
        }
      },
      coverage: {
        provider: 'v8',
        reporter: ['text', 'json', 'html'],
        exclude: ['node_modules/', 'vitest.setup.ts']
      }
    }
  };
});
