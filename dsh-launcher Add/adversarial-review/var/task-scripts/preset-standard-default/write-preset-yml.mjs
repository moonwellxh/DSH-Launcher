/**
 * write-preset-yml.mjs - task: create agent preset `standard-default`.
 *
 * Writes the preset's display metadata using the SAME renderer options the
 * product itself uses (js-yaml dump, lineWidth -1 - see
 * packages/preset/agent-presets/src/metadata.ts), so the file the GUI would
 * have produced and this file are formatted identically.
 *
 * Round-1 review fix (R1/R2): the description no longer claims the
 * composition is line-for-line identical to the shipped one and now states
 * that a frozen copy does not follow harness upgrades.
 * Round-2 review fix (新2): "行序" was ambiguous (plugin ROW order vs physical
 * line order).
 * Rename (2026-09-12): the display name was 「标准模式（默认）」, which collided
 * BYTE-FOR-BYTE with the plugin-inventory surface's generated default label
 * `presetOptionDefault: '{name}（默认）'` once `standard` is the default
 * (packages/client/ui-settings-plugin-inventory/src/client/locales.ts:16,
 * PluginInventorySettingsTab.tsx:80-87). It is now 「标准模式（初始状态）」,
 * which states the same intent without colliding.
 * Wording fix (2026-09-12, review 轻微 1/2/3): the description no longer
 * (a) says the preset "scans no skill roots" without scoping that to THIS
 * provider, (b) claims identity of "injected prompt text" (which is resolved
 * at runtime from {{cwd}}/{{model}}), or (c) says "apart from two isolation
 * changes, every row matches" - which contradicted itself, since those two
 * rows ARE the differences. It now names the two rows and scopes each claim.
 *
 * Usage: node write-preset-yml.mjs <preset-dir> <harness-package-dir>
 *
 * The second argument is the installed harness's agent-presets package
 * directory; js-yaml is resolved from there so this script needs no
 * node_modules of its own.
 */

import { readFileSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { join } from 'node:path'

const dir = process.argv[2]
const harnessPackageDir = process.argv[3]
if (dir === undefined || harnessPackageDir === undefined) {
  console.error('usage: node write-preset-yml.mjs <preset-dir> <harness-package-dir>')
  process.exit(2)
}

const yaml = createRequire(join(harnessPackageDir, 'package.json'))('js-yaml')

const NAME = '标准模式（初始状态）'
const DESCRIPTION = '出厂「标准模式」的冻结副本：除 agent-instructions 与 skill-filesystem 两行外，其余行连同它们携带的提示词模板文字，均与出厂逐字段一致；该两行改为不加载全局与工作区记忆、本 provider 不扫描技能根。不随 DSH 升级更新。'

const path = join(dir, 'preset.yml')
const text = yaml.dump({ name: NAME, description: DESCRIPTION }, { lineWidth: -1 })
writeFileSync(path, text, 'utf8')

const readBack = yaml.load(readFileSync(path, 'utf8'))
const bytes = readFileSync(path)
const ok = readBack.name === NAME && readBack.description === DESCRIPTION
console.log(`written: ${path}`)
console.log(`  bytes ${String(bytes.length)}; BOM ${String(bytes[0] === 0xEF && bytes[1] === 0xBB && bytes[2] === 0xBF)}`)
console.log(`  round-trip name/description exact: ${String(ok)}`)
console.log(`  name === "标准模式（初始状态）": ${String(readBack.name === '标准模式（初始状态）')}`)
if (!ok) process.exit(1)
