import { readFileSync } from 'node:fs'

const file = process.env.USERPROFILE + '\\.dsh\\profiles\\web\\plugins\\model-menu-opaque\\client.js'
const src = readFileSync(file, 'utf8')

let captured = null
const styles = []
const el = () => ({ setAttribute() {}, appendChild() {}, remove() {}, textContent: '', id: '', tagName: '' })
globalThis.window = {
  __ModuleLoader__: { load: (mod) => { captured = mod } },
}
globalThis.document = {
  head: { appendChild: (n) => styles.push(n), querySelector: () => null },
  getElementById: () => null,
  createElement: () => el(),
  addEventListener() {},
}
globalThis.matchMedia = () => ({ matches: false, addEventListener() {} })

// 以模块脚本方式求值（与浏览器内一致：文件本身就是 load({...}) 调用）
new Function(src)()

const results = []
const check = (name, ok, extra) => results.push({ name, ok: !!ok, extra })

check('注册发生', captured !== null)
check('id 正确', captured && captured.id === 'local-model-menu-opaque', captured && captured.id)
check('factory 可调用', typeof (captured && captured.factory) === 'function')

let exportsObj = null
try {
  exportsObj = captured.factory(() => { throw new Error('unexpected require') })
} catch (e) {
  check('factory 执行', false, e.message)
}
if (exportsObj) {
  check('导出 apply', typeof exportsObj.apply === 'function')
  const effects = []
  try {
    exportsObj.apply({ effect: (fn) => { effects.push(fn); fn() } })
    check('apply 不抛错', true)
  } catch (e) {
    check('apply 不抛错', false, e.message)
  }
  check('注册了 effect', effects.length > 0, String(effects.length))
  const css = styles.map((s) => s.textContent || '').join('')
  check('注入了样式', css.length > 0, String(css.length))
  check('样式含中文菜单名', css.includes('模型与推理等级'))
  check('样式含英文菜单名', css.includes('Model and reasoning effort'))
  check('样式为不透明', /opaque|#fff|#2c2c2e|background/i.test(css))
}

for (const r of results) console.log(`${r.ok ? 'PASS' : 'FAIL'} ${r.name}${r.extra ? ' :: ' + r.extra : ''}`)
const failed = results.filter((r) => !r.ok).length
console.log(`\nRESULT pass=${results.length - failed} fail=${failed}`)
process.exit(failed === 0 ? 0 : 1)
