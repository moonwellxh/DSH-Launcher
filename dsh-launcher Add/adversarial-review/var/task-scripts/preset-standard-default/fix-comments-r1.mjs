/**
 * fix-comments-r1.mjs - task: create agent preset `standard-default`.
 *
 * Round-1 review fix. Rewrites the two frozen-config comment blocks in the
 * copied composition so they state exactly what the product guarantees
 * (review S1: the "catalog is empty" claim read as an unconditional property
 * of the preset, while the merged catalog is host+per-scope layered) and so
 * the silent-disable behaviour of a non-positive cap is documented where a
 * later reader will look for it (review S5).
 *
 * Anchors are counted; a file already carrying the round-1 markers is skipped.
 * Reads/writes UTF-8 WITHOUT BOM.
 *
 * Usage: node fix-comments-r1.mjs <path-to-agent.cordis.yml>
 */

import { readFileSync, writeFileSync } from 'node:fs'

const R1_MARKER = 'this provider scans no roots'
const target = process.argv[2]
if (target === undefined) {
  console.error('usage: node fix-comments-r1.mjs <path-to-agent.cordis.yml>')
  process.exit(2)
}

const original = readFileSync(target, 'utf8')
if (original.charCodeAt(0) === 0xFEFF) {
  console.error('FAIL: source carries a UTF-8 BOM; refusing to guess the intended encoding')
  process.exit(1)
}
if (original.includes(R1_MARKER)) {
  console.log('SKIP: round-1 comment fixes already applied')
  process.exit(0)
}

/** @type {[string, string, string][]} */
const edits = [
  [
    'agent-instructions comment',
    `    # FROZEN (standard-default): maxBytes 0 disables instruction loading
    # entirely, so neither the user-global <dshHome>/AGENTS.md nor any
    # workspace AGENTS.md / AGENTS.local.md / CLAUDE.md reaches this agent.
    # Restore 65536 to get the shipped standard behavior back.
`,
    `    # FROZEN (standard-default): a non-positive maxBytes disables instruction
    # loading entirely, so neither the user-global <dshHome>/AGENTS.md nor any
    # workspace AGENTS.md / AGENTS.local.md / CLAUDE.md reaches this agent. The
    # disable is silent by design - the plugin returns before any file read and
    # logs nothing - so this file, not a log, is the evidence. Restore 65536 to
    # get the shipped standard behavior back.
`,
  ],
  [
    'skill-filesystem comment',
    `    # FROZEN (standard-default): project roots (<projectRoot>/.dsh/skills,
    # <projectRoot>/.agents/skills) and user roots (<dshHome>/skills,
    # ~/.agents/skills) stay unscanned, and no bundledSkillDir is set, so the
    # skill catalog for this preset is empty. Set customSkillDirs, or restore
    # includeDefaultRoots, to opt skills back in.
`,
    `    # FROZEN (standard-default): THIS provider scans no roots - project roots
    # (<projectRoot>/.dsh/skills, <projectRoot>/.agents/skills), user roots
    # (<dshHome>/skills, ~/.agents/skills), bundledSkillDir and customSkillDirs
    # are all off. The merged catalog is host+per-scope layered, so a
    # deployment-registered GLOBAL provider would still contribute to this
    # preset; the shipped host skill-filesystem and skill-badge rows are
    # disabled, so with this file the catalog is empty. Set customSkillDirs, or
    # restore includeDefaultRoots, to opt skills back in.
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

writeFileSync(target, text, 'utf8')
const bytes = readFileSync(target)
console.log(`OK: ${target}`)
console.log(`  ${String(original.length)} chars -> ${String(text.length)} chars; on-disk ${String(bytes.length)} bytes`)
console.log(`  BOM present: ${String(bytes[0] === 0xEF && bytes[1] === 0xBB && bytes[2] === 0xBF)}`)
for (const [label] of edits) console.log(`  applied: ${label}`)
