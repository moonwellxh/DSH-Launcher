/**
 * fix-comments-r2.mjs - task: create agent preset `standard-default`.
 *
 * Round-2 review fix (新1, graded severe): the round-1 wording asserted that
 * "the shipped host skill-filesystem and skill-badge rows are disabled". That
 * holds only for the web-app variant this machine runs: patches/base leaves
 * the host skill-filesystem row ENABLED (packages/bundle/base/cordis.patch.yml
 * has exactly two `disabled: true`, one of them skill-badge at L281), while
 * packages/bundle/web-app/cordis.patch.yml L402-L406 disables it. The comment
 * therefore now scopes the empty-catalog observation to this deployment.
 *
 * Anchors are counted; a file already carrying the round-2 marker is skipped.
 * Reads/writes UTF-8 WITHOUT BOM.
 *
 * Usage: node fix-comments-r2.mjs <path-to-agent.cordis.yml>
 */

import { readFileSync, writeFileSync } from 'node:fs'

const R2_MARKER = "THIS machine's web deployment because"
const target = process.argv[2]
if (target === undefined) {
  console.error('usage: node fix-comments-r2.mjs <path-to-agent.cordis.yml>')
  process.exit(2)
}

const original = readFileSync(target, 'utf8')
if (original.charCodeAt(0) === 0xFEFF) {
  console.error('FAIL: source carries a UTF-8 BOM; refusing to guess the intended encoding')
  process.exit(1)
}
if (original.includes(R2_MARKER)) {
  console.log('SKIP: round-2 comment fix already applied')
  process.exit(0)
}

const from = `    # FROZEN (standard-default): THIS provider scans no roots - project roots
    # (<projectRoot>/.dsh/skills, <projectRoot>/.agents/skills), user roots
    # (<dshHome>/skills, ~/.agents/skills), bundledSkillDir and customSkillDirs
    # are all off. The merged catalog is host+per-scope layered, so a
    # deployment-registered GLOBAL provider would still contribute to this
    # preset; the shipped host skill-filesystem and skill-badge rows are
    # disabled, so with this file the catalog is empty. Set customSkillDirs, or
    # restore includeDefaultRoots, to opt skills back in.
`

const to = `    # FROZEN (standard-default): THIS provider scans no roots - project roots
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
`

const occurrences = original.split(from).length - 1
if (occurrences !== 1) {
  console.error(`FAIL: expected exactly 1 anchor, found ${String(occurrences)}`)
  process.exit(1)
}

const text = original.replace(from, to)
writeFileSync(target, text, 'utf8')
const bytes = readFileSync(target)
console.log(`OK: ${target}`)
console.log(`  ${String(original.length)} chars -> ${String(text.length)} chars; on-disk ${String(bytes.length)} bytes`)
console.log(`  BOM present: ${String(bytes[0] === 0xEF && bytes[1] === 0xBB && bytes[2] === 0xBF)}`)
