#!/usr/bin/env node
/**
 * Post-install script for dsh-plugin-writing-guard.
 *
 * Two things happen here:
 * 1. The writing-guard skill is copied to DSH_HOME/skills/writing-guard, where
 *    DSH discovers skills.
 * 2. The Python word_guard module is mirrored to PLUGIN_ROOT/lib/word_guard.
 *    The runtime resolves the CLI as PLUGIN_DIR/word_guard/cli.py, and
 *    PLUGIN_DIR is the directory holding lib/index.js — so the module must live
 *    next to the built plugin, not under DSH_HOME.
 *
 * This script NEVER throws — failures are logged as warnings so npm install
 * does not fail. The plugin works without the skill/Python files; they just
 * enable natural-language triggering and Word editing.
 */
import { existsSync, mkdirSync, cpSync, chmodSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'

const __dirname = dirname(fileURLToPath(import.meta.url))
const PLUGIN_ROOT = join(__dirname, '..')

// DSH home directory — handle Windows, macOS, Linux
function getDshHome() {
  if (process.env.DSH_HOME) return process.env.DSH_HOME
  // Windows: USERPROFILE, Unix: HOME
  const home = process.env.USERPROFILE || process.env.HOME
  if (!home) return null
  return join(home, '.dsh')
}

function copyDir(src, dest) {
  if (!existsSync(src)) return false
  mkdirSync(dest, { recursive: true })
  cpSync(src, dest, { recursive: true, force: true })
  return true
}

// Python interpreters to probe, most specific first. DSH_PYTHON wins; it may be
// an absolute path containing spaces, which execFileSync handles as one argv.
function getPythonCandidates() {
  const candidates = []
  if (process.env.DSH_PYTHON) candidates.push(process.env.DSH_PYTHON)
  if (process.platform === 'win32') candidates.push('python', 'python3')
  else candidates.push('python3', 'python')
  return [...new Set(candidates)]
}

// Probe python-docx. Returns { cmd, version } or null when nothing works.
function detectPythonDocx() {
  for (const cmd of getPythonCandidates()) {
    try {
      const out = execFileSync(cmd, ['-c', 'import docx; print(docx.__version__)'], {
        stdio: 'pipe',
        encoding: 'utf8',
      })
      return { cmd, version: String(out).trim() }
    } catch {
      // Not this interpreter — try the next candidate
    }
  }
  return null
}

// Main — wrapped in a top-level catch that never exits with code 1
try {
  const DSH_HOME = getDshHome()
  if (!DSH_HOME) {
    console.warn('[dsh-plugin-writing-guard] Could not determine DSH_HOME — skipping postinstall setup')
    console.warn('[dsh-plugin-writing-guard] You can manually copy skills/ and src/word_guard/ later')
    // Exit successfully — this is not a fatal error
    process.exit(0)
  }

  // 1. Copy skill files to ~/.dsh/skills/writing-guard/
  try {
    const skillSrc = join(PLUGIN_ROOT, 'skills', 'writing-guard')
    const skillDest = join(DSH_HOME, 'skills', 'writing-guard')
    if (existsSync(skillSrc)) {
      copyDir(skillSrc, skillDest)
      console.log(`[dsh-plugin-writing-guard] Skill installed to ${skillDest}`)
    }
  } catch (e) {
    console.warn(`[dsh-plugin-writing-guard] Could not install skill: ${e.message}`)
  }

  // 2. Mirror the Python word_guard module to lib/word_guard next to the built
  //    plugin. This is the path the runtime actually loads
  //    (PLUGIN_DIR/word_guard/cli.py); the old ~/.dsh/plugins/... target was
  //    never read by the plugin.
  try {
    const pySrc = join(PLUGIN_ROOT, 'src', 'word_guard')
    const pyDest = join(PLUGIN_ROOT, 'lib', 'word_guard')
    if (existsSync(pySrc)) {
      copyDir(pySrc, pyDest)
      console.log(`[dsh-plugin-writing-guard] Python module installed to ${pyDest}`)
    } else {
      console.warn(`[dsh-plugin-writing-guard] Python source not found at ${pySrc} — Word tools will not work`)
    }
  } catch (e) {
    console.warn(`[dsh-plugin-writing-guard] Could not install Python module to lib/word_guard: ${e.message}`)
    console.warn('[dsh-plugin-writing-guard] Word tools will not work until src/word_guard is copied manually')
  }

  // 3. Check python-docx availability (informational only — never fatal)
  try {
    const detected = detectPythonDocx()
    if (detected) {
      console.log(`[dsh-plugin-writing-guard] python-docx ${detected.version} detected via ${detected.cmd} ✓`)
    } else {
      console.warn('[dsh-plugin-writing-guard] python-docx not found — Word tools will not work until installed:')
      console.warn('  pip install python-docx')
      console.warn(`  (probed: ${getPythonCandidates().join(', ')}; set DSH_PYTHON to override)`)
    }
  } catch (e) {
    console.warn(`[dsh-plugin-writing-guard] python-docx probe skipped: ${e.message}`)
  }

  console.log('[dsh-plugin-writing-guard] Postinstall complete')
} catch (e) {
  // Last resort — never let postinstall fail the npm install
  console.warn(`[dsh-plugin-writing-guard] Postinstall warning: ${e.message}`)
}
