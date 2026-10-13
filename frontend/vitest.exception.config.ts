import { defineConfig, mergeConfig } from 'vitest/config';
import baseConfig from './vite.config';

export default mergeConfig(baseConfig, defineConfig({
  test: {
    include: ['src/exception/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      all: true,
      include: ['src/exception/**/*.{ts,tsx}'],
      exclude: ['src/exception/**/*.test.{ts,tsx}', 'src/exception/types/**'],
      reporter: ['text', 'lcov', 'json'],
      branches: 95,
      functions: 95,
      lines: 95,
      statements: 95,
    },
  },
}));
