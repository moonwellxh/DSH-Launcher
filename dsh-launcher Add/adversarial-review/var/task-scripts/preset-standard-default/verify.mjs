/**
 * verify.mjs - task: create agent preset `standard-default`.
 *
 * Deterministic verification with no model judgement in the assertions:
 *   V1 real discovery health - calls the product's own `discoverPresets`.
 *   V2 the copy is the shipped standard composition plus EXACTLY the two
 *      intended departures (full canonical row comparison, every field).
 *   V3 value-level assertions on the two isolation knobs, with the source
 *      lines carrying the semantics cited in the labels. This script does not
 *      instantiate any preset plugin, so it cannot observe injection or skill
 *      resolution behaviour; those claims rest on those source citations.
 *   V4 the preset is NOT the new-session default: no layer that can decide the
 *      default - the user settings document, or the user's own profile patch
 *      (highest precedence) - points at it, while the deployment layer still
 *      declares `standard`. Picking another preset by hand stays green.
 *      (Requirement reversed after delivery: the preset stays selectable but
 *      must not become what new sessions run.)
 *      NOTE: on this machine the checked deployment patch is reached through
 *      node_modules junctions into the source checkout, like
 *      `SHIPPED_PRESET_ROOT` below; the printed path makes that visible.
 *   V5 encodings, directory contents, display metadata.
 *
 * What DOES execute here (round-2 review 新3): `discoverPresets` - the product's
 * real discovery, which parses both compositions with the loader's own YAML
 * dialect and resolves every row's module against the harness base, plus
 * `entryListSchema` from the installed package. So V1/V2 exercise product code
 * paths, not a private re-implementation; only the plugin *behaviour* claims
 * are source-level.
 *
 * Known assumptions (round-2 review 新4, wording corrected in round 3):
 *   - V2 trusts that `entryListSchema` preserves unknown keys, so "every field"
 *     means every field the parse retained. The installed dialect is
 *     `yaml.JSON_SCHEMA.extend(JsExpr)` (not strict); should it ever become
 *     strict, V2 would silently degrade to "every recognised field" and this
 *     check would not notice.
 *   - The baseline is the composition shipped inside the agent-presets package
 *     (`SHIPPED_PRESET_ROOT`). THIS deployment links that package (junction,
 *     then symlink) into the source checkout, so the baseline physically
 *     resolves to the checkout tree - the printed path and sha256 make that
 *     visible instead of silent.
 *
 * Usage: node verify.mjs <dsh-home> <harness-base-dir> <harness-agent-presets-pkg-dir>
 *
 * <harness-base-dir> is the directory whose node_modules holds the INSTALLED
 * @deepseek-ai packages - on this machine `C:\Users\雍远\.dsh\profiles`, NOT
 * the source checkout: discovery resolves a row's package name by walking
 * node_modules upward from this base (packages/preset/agent-presets/src/
 * discovery.ts, packageInstalled), so passing the checkout root reports every
 * preset row as unresolvable (round-1 review S4).
 */

import { createHash } from 'node:crypto'
import { readFileSync, readdirSync } from 'node:fs'
import { createRequire } from 'node:module'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

const [dshHome, harnessBaseDir, pkgDir] = process.argv.slice(2)
if (dshHome === undefined || harnessBaseDir === undefined || pkgDir === undefined) {
  console.error('usage: node verify.mjs <dsh-home> <harness-base-dir> <harness-agent-presets-pkg-dir>')
  process.exit(2)
}

const requireFromPkg = createRequire(join(pkgDir, 'package.json'))
const yaml = requireFromPkg('js-yaml')
const { entryListSchema } = requireFromPkg('@deepseek-ai/cordis-plugin-include')
const presets = requireFromPkg('./lib/index.js')

const USER_ROOT = join(dshHome, '.agent-presets')
const ID = 'standard-default'
const NAME = '标准模式（初始状态）'
const targetDir = join(USER_ROOT, ID)
const shippedFile = join(presets.SHIPPED_PRESET_ROOT, 'standard', 'agent.cordis.yml')
const targetFile = join(targetDir, 'agent.cordis.yml')

let failures = 0
const check = (label, ok, detail = '') => {
  if (!ok) failures += 1
  console.log(`${ok ? 'PASS' : 'FAIL'} ${label}${detail === '' ? '' : ` -- ${detail}`}`)
}
const sha256 = path => createHash('sha256').update(readFileSync(path)).digest('hex')

/** Replace functions (the loader's `!!js` values) with a stable marker. */
const canon = (value) => {
  if (typeof value === 'function') return '<js>'
  if (Array.isArray(value)) return value.map(canon)
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, canon(value[key])]))
  }
  return value
}
/** Every parsed field of one row, order-insensitive, function values included. */
const canonRow = row => JSON.stringify(canon(row))

// ---- V1: real discovery health -------------------------------------------
const harnessBase = pathToFileURL(harnessBaseDir + '/').href
const discovered = await presets.discoverPresets([
  { path: presets.SHIPPED_PRESET_ROOT, trust: 'system' },
  { path: USER_ROOT, trust: 'user' },
], harnessBase)

const shipped = discovered.find(row => row.id === 'standard')
const target = discovered.find(row => row.id === ID)

check('V1 随包 standard 自身健康（基线）', shipped !== undefined && shipped.broken === undefined,
  shipped === undefined ? 'not discovered' : `broken=${String(shipped.broken)}`)
check('V1 standard-default 被真实发现', target !== undefined, `discovered ids: ${discovered.map(r => r.id).join(', ')}`)
if (target !== undefined) {
  check('V1 trust=user（出现在「自定义」组）', target.trust === 'user', target.trust)
  check('V1 无 broken（每一行都能解析）', target.broken === undefined, String(target.broken))
  check(`V1 显示名精确等于 ${NAME}`, target.name === NAME, JSON.stringify(target.name))
  check('V1 有描述', typeof target.description === 'string' && target.description.length > 0, JSON.stringify(target.description))
  check('V1 order 未写（自定义组按 id 排序）', target.order === undefined, String(target.order))
}
check('V1 预设组成文件名就是 agent.cordis.yml', presets.COMPOSITION_FILE === 'agent.cordis.yml', presets.COMPOSITION_FILE)
check('V1 settings 命名空间就是 agent-presets', presets.SETTINGS_NAMESPACE === 'agent-presets', presets.SETTINGS_NAMESPACE)

// ---- V2: full-row comparison against the shipped composition -------------
console.log(`INFO V2 基准（随包副本；本机经链接解析到该路径）sha256=${sha256(shippedFile)} path=${shippedFile}`)
const a = yaml.load(readFileSync(shippedFile, 'utf8'), { schema: entryListSchema })
const b = yaml.load(readFileSync(targetFile, 'utf8'), { schema: entryListSchema })
check('V2 行数一致', a.length === b.length, `${String(a.length)} vs ${String(b.length)}`)
check('V2 行 id 序列一致（组内行按树序展开）', JSON.stringify(a.map(r => String(r.id))) === JSON.stringify(b.map(r => String(r.id))))

const diffs = []
for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
  const left = a[i] === undefined ? '<missing>' : canonRow(a[i])
  const right = b[i] === undefined ? '<missing>' : canonRow(b[i])
  if (left !== right) diffs.push({ index: i, id: String((b[i] ?? a[i]).id), left, right })
}
check('V2 逐行全字段比对：恰好 2 行有差异，其余行逐字段相同',
  diffs.length === 2, `diff rows: ${diffs.map(d => d.id).join(', ')}`)
check('V2 有差异的正是这两行',
  JSON.stringify(diffs.map(d => d.id).sort()) === JSON.stringify(['agent-instructions', 'skill-filesystem']),
  JSON.stringify(diffs.map(d => d.id)))

const instr = b.find(row => row.id === 'agent-instructions')
const skills = b.find(row => row.id === 'skill-filesystem')
const instrShipped = a.find(row => row.id === 'agent-instructions')

// ---- V3: value level only (semantics cited, not executed) ---------------
check('V3 值级：agent-instructions 出厂 maxBytes=65536', instrShipped?.config?.maxBytes === 65536, String(instrShipped?.config?.maxBytes))
check('V3 值级：冻结 maxBytes=0；语义“<=0 即完全关闭指令注入”见 agent-instructions/src/index.ts:115 与 files.ts:419（本脚本不实例化插件）',
  instr?.config?.maxBytes === 0, String(instr?.config?.maxBytes))
check('V3 值级：skill-filesystem 出厂无 config', a.find(r => r.id === 'skill-filesystem')?.config === undefined)
check('V3 值级：includeDefaultRoots=false；语义“本 provider 零根”见 skill-filesystem/src/index.ts:241-261（本脚本不实例化插件）',
  skills?.config?.includeDefaultRoots === false, String(skills?.config?.includeDefaultRoots))
check('V3 值级：未设置 bundledSkillDir（否则会引入随附技能根）',
  skills?.config?.bundledSkillDir === undefined, String(skills?.config?.bundledSkillDir))
check('V3 值级：customSkillDirs 为空（否则技能根非空）',
  (skills?.config?.customSkillDirs ?? []).length === 0, JSON.stringify(skills?.config?.customSkillDirs ?? null))
check('V3 tool-skill 行仍在（目录为空不等于改装机）', b.some(row => row.id === 'tool-skill'))

// ---- V4: the preset must NOT be the new-session default ------------------
// The requirement is "new sessions do not run standard-default", NOT "the
// user layer is untouched": picking `standard` or `minimal` by hand is a
// legitimate state and must stay green. So every layer that can decide the
// default is checked for a pointer at THIS preset, and the deployment layer
// is separately required to still declare `standard`.
const settings = yaml.load(readFileSync(join(dshHome, 'settings.yaml'), 'utf8'))
check('V4 settings.yaml 可解析为映射', typeof settings === 'object' && settings !== null && !Array.isArray(settings))
check('V4 用户设置层未把本预设设为默认（agent-presets.default !== standard-default）',
  settings?.['agent-presets']?.default !== ID, `agent-presets.default=${JSON.stringify(settings?.['agent-presets']?.default ?? null)}`)
check('V4 未改动既有键（agent-default-model 仍在）', settings?.['agent-default-model']?.model === 'deepseek-flash')
check('V4 未改动既有键（permission 未被写入）', settings?.permission === undefined)

/** Every `agent-presets` row id+default reachable in a loader patch file. */
const patchDefaults = (path) => {
  let patch
  try {
    patch = yaml.load(readFileSync(path, 'utf8'), { schema: entryListSchema })
  } catch {
    return undefined
  }
  const findRow = (nodes, id) => {
    for (const node of Array.isArray(nodes) ? nodes : []) {
      if (node === null || typeof node !== 'object') continue
      if (node.id === id) return node
      for (const value of Object.values(node)) {
        const hit = findRow(value, id)
        if (hit !== undefined) return hit
      }
    }
    return undefined
  }
  return findRow(patch, 'agent-presets')?.config?.default
}

// Layer order is base -> bundle -> the user's own profile patch, last write
// winning per row (packages/bundle/base/cordis.patch.yml:2-4), so a user patch
// pointing at the preset would override everything below it.
const deploymentPatch = join(harnessBaseDir, 'node_modules', '@deepseek-ai', 'dsh-web-app', 'cordis.patch.yml')
check('V4 部署层（已安装 dsh-web-app 补丁）仍声明 agent-presets.default === standard',
  patchDefaults(deploymentPatch) === 'standard',
  `${deploymentPatch} -> ${JSON.stringify(patchDefaults(deploymentPatch) ?? null)}`)
for (const profile of ['web', 'headless']) {
  const profilePatch = join(dshHome, 'profiles', profile, 'cordis.patch.yml')
  const found = patchDefaults(profilePatch)
  check(`V4 用户补丁层 profiles/${profile}/cordis.patch.yml 未把 agent-presets.default 指向本预设`,
    found !== ID, `${profilePatch} -> ${JSON.stringify(found ?? null)}`)
}

// ---- V5: encodings, contents, display metadata ---------------------------
const noBom = (path) => {
  const bytes = readFileSync(path)
  return !(bytes[0] === 0xEF && bytes[1] === 0xBB && bytes[2] === 0xBF)
}
check('V5 agent.cordis.yml 无 BOM', noBom(targetFile))
check('V5 preset.yml 无 BOM', noBom(join(targetDir, 'preset.yml')))
const entries = readdirSync(targetDir).sort()
check('V5 预设目录只含两份文件', JSON.stringify(entries) === JSON.stringify(['agent.cordis.yml', 'preset.yml']), entries.join(', '))
const meta = yaml.load(readFileSync(join(targetDir, 'preset.yml'), 'utf8'))
check('V5 preset.yml 的 name 逐字符等于目标名', meta?.name === NAME, JSON.stringify(meta?.name))
check('V5 描述声明了“不随 DSH 升级更新”这一冻结后果',
  typeof meta?.description === 'string' && meta.description.includes('不随 DSH 升级更新'), JSON.stringify(meta?.description))

console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${String(failures)} CHECK(S) FAILED`)
process.exit(failures === 0 ? 0 : 1)
