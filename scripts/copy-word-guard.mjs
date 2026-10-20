#!/usr/bin/env node
/**
 * Copy the vendored Python word_guard module next to the compiled plugin.
 *
 * tsc only compiles TypeScript, but the runtime resolves the CLI as
 * PLUGIN_DIR/word_guard/cli.py where PLUGIN_DIR is the directory holding
 * lib/index.js. So the Python sources must be mirrored to lib/word_guard on
 * every build; committing them by hand is how they drift out of sync.
 *
 * This runs as part of `pnpm build` (and therefore `pnpm test` via pretest).
 */
import { existsSync, mkdirSync, cpSync, rmSync, readdirSync, statSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const PLUGIN_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const SOURCE = join(PLUGIN_ROOT, 'src', 'word_guard')
const DEST = join(PLUGIN_ROOT, 'lib', 'word_guard')

if (!existsSync(SOURCE)) {
  console.error(`[copy-word-guard] source not found: ${SOURCE}`)
  process.exit(1)
}

rmSync(DEST, { recursive: true, force: true })
mkdirSync(DEST, { recursive: true })
cpSync(SOURCE, DEST, {
  recursive: true,
  force: true,
  // Bytecode caches are machine-specific and must never ship.
  filter: (src) => !src.includes('__pycache__') && !src.endsWith('.pyc'),
})

// Defensive sweep: cpSync filters directories by path, but a stray cache can
// still appear if it was created between the filter check and the copy.
function stripPycache(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (entry === '__pycache__') {
      rmSync(full, { recursive: true, force: true })
      continue
    }
    if (statSync(full).isDirectory()) stripPycache(full)
  }
}
stripPycache(DEST)

console.log(`[copy-word-guard] ${SOURCE} -> ${DEST}`)
