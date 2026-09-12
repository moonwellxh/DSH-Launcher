/**
 * apply-departures.mjs - task: create agent preset `standard-default`.
 *
 * Takes a byte-identical copy of the shipped `standard` composition and
 * applies exactly the two isolation departures frozen at S0, producing the
 * DELIVERED file (comments included):
 *   1. agent-instructions.maxBytes: 65536 -> 0   (no instruction injection)
 *   2. skill-filesystem gains includeDefaultRoots: false (this provider scans
 *      no roots)
 *
 * Round-3 review fix (severe): the replacement text below is the FINAL wording.
 * Earlier revisions embedded the round-1 text, so replaying the registered
 * chain regenerated a comment that round 2 had already rejected for asserting
 * a bundle-wide fact. `fix-comments-r1.mjs` / `fix-comments-r2.mjs` are the
 * audit record of rounds 1-2 and are ALREADY absorbed here - do not run them
 * after this script.
 *
 * Idempotent: a file already carrying the marker is left untouched (the
 * delivered file does, so re-running it is a no-op).
 * Reads and writes UTF-8 WITHOUT BOM, matching the shipped file's bytes.
 *
 * Usage: node apply-departures.mjs <path-to-agent.cordis.yml>
 */

import { readFileSync, writeFileSync } from 'node:fs'

const MARKER = 'FROZEN (standard-default)'
const target = process.argv[2]
if (target === undefined) {
  console.error('usage: node apply-departures.mjs <path-to-agent.cordis.yml>')
  process.exit(2)
}

const original = readFileSync(target, 'utf8')
if (original.charCodeAt(0) === 0xFEFF) {
  console.error('FAIL: source already carries a UTF-8 BOM; refusing to guess the intended encoding')
  process.exit(1)
}

if (original.includes(MARKER)) {
  console.log('SKIP: departures already applied')
  process.exit(0)
}

/** @type {[string, string, string][]} */
const edits = [
  [
    'agent-instructions',
    "- id: agent-instructions\n  name: '@deepseek-ai/dsh-agent-instructions'\n  config:\n    maxBytes: 65536\n",
    `- id: agent-instructions
  name: '@deepseek-ai/dsh-agent-instructions'
  config:
    # FROZEN (standard-default): a non-positive maxBytes disables instruction
    # loading entirely, so neither the user-global <dshHome>/AGENTS.md nor any
    # workspace AGENTS.md / AGENTS.local.md / CLAUDE.md reaches this agent. The
    # disable is silent by design - the plugin returns before any file read and
    # logs nothing - so this file, not a log, is the evidence. Restore 65536 to
    # get the shipped standard behavior back.
    maxBytes: 0
`,
  ],
  [
    'skill-filesystem',
    "- id: skill-filesystem\n  name: '@deepseek-ai/dsh-skill-filesystem'\n",
    `- id: skill-filesystem
  name: '@deepseek-ai/dsh-skill-filesystem'
  config:
    # FROZEN (standard-default): THIS provider scans no roots - project roots
    # (<projectRoot>/.dsh/skills, <projectRoot>/.agents/skills), user roots
    # (<dshHome>/skills, ~/.agents/skills), bundledSkillDir and customSkillDirs
    # are all off. What that guarantees is only this file's contribution: the
    # merged catalog is host+per-scope layered, so a global provider registered
    # by the deployment would still reach this agent. The catalog is empty in
    # THIS machine's web deployment because the web-app bundle patch disables
    # the host skill-filesystem row (the base bundle leaves it enabled) and
    # skill-badge ships disabled - a property of the deployment, not of this
    # file. Set customSkillDirs, or restore includeDefaultRoots, to opt skills
    # back in.
    includeDefaultRoots: false
`,
  ],
]

let text = original
for (const [label, from, to] of edits) {
  const occurrences = text.split(from).length - 1
  if (occurrences !== 1) {
    console.error(`FAIL: ${label}: expected exactly 1 anchor, found ${String(occurrences)}`)
    process.exit(1)
  }
  text = text.replace(from, to)
}

if (text === original) {
  console.error('FAIL: no text changed')
  process.exit(1)
}

writeFileSync(target, text, 'utf8')
const bytes = readFileSync(target)
console.log(`OK: ${target}`)
console.log(`  bytes ${String(original.length)} chars -> ${String(text.length)} chars; on-disk ${String(bytes.length)} bytes`)
console.log(`  BOM present: ${String(bytes[0] === 0xEF && bytes[1] === 0xBB && bytes[2] === 0xBF)}`)
for (const [label] of edits) console.log(`  applied: ${label}`)
