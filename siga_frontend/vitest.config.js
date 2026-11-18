import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    // Este proyecto corre en máquinas con pocos recursos: sin estos valores
    // los tests se vuelven flaky (timeouts de 5s y workers que no arrancan).
    testTimeout: 20000,
    hookTimeout: 20000,
    teardownTimeout: 10000,
    pool: 'forks',
    minWorkers: 1,
    maxWorkers: 1,
    fileParallelism: false,
  },
})
