import { mkdir, writeFile, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

const modPath = 'C:/Users/雍远/deepseek-harness/packages/host/frontend-static/lib/index.js'
const { serveStatic } = await import(pathToFileURL(modPath).href)

const dist = join(process.env.TEMP, 'dsh-fe-static-test')
await rm(dist, { recursive: true, force: true })
await mkdir(join(dist, 'assets'), { recursive: true })
await writeFile(join(dist, 'index.html'), '<html><head></head><body>x</body></html>')
await writeFile(join(dist, 'assets', 'index-9f2ab81c.js'), 'console.log(1)')
await writeFile(join(dist, 'favicon.svg'), '<svg/>')

function fakeRes() {
  const r = { status: 0, headers: null, body: null }
  r.writeHead = (s, h) => { r.status = s; r.headers = h || null }
  r.end = (b) => { r.body = b ?? null }
  return r
}

const distIndex = join(dist, 'index.html')
let pass = 0
let fail = 0
function check(name, cond, detail) {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name} :: ${detail}`) }
}

// 1) index → no-store
{
  const res = fakeRes()
  await serveStatic('/', res, dist, distIndex, () => true, async () => '<html>boot</html>')
  check('index 200 no-store', res.status === 200 && res.headers['cache-control'] === 'no-store', JSON.stringify(res))
}

// 2) content-addressed asset → immutable
{
  const res = fakeRes()
  await serveStatic('/assets/index-9f2ab81c.js', res, dist, distIndex, () => true, async () => '')
  check('hashed asset immutable', res.status === 200 && res.headers['cache-control'] === 'public, max-age=31536000, immutable', JSON.stringify(res.headers))
}

// 3) plain asset → no-cache + etag, then 304 on match
{
  const res = fakeRes()
  await serveStatic('/favicon.svg', res, dist, distIndex, () => true, async () => '')
  const okHeaders = res.status === 200 && res.headers['cache-control'] === 'no-cache' && typeof res.headers.etag === 'string'
  check('plain asset no-cache + etag', okHeaders, JSON.stringify(res.headers))

  const res2 = fakeRes()
  await serveStatic('/favicon.svg', res2, dist, distIndex, () => true, async () => '', res.headers.etag)
  check('conditional revalidate 304', res2.status === 304 && res2.body === null, JSON.stringify({ s: res2.status }))

  const res3 = fakeRes()
  await serveStatic('/favicon.svg', res3, dist, distIndex, () => true, async () => '', 'W/"stale"')
  check('stale etag still 200', res3.status === 200, JSON.stringify({ s: res3.status }))
}

// 4) traversal still 403, missing still 404
{
  const res = fakeRes()
  await serveStatic('/../outside.txt', res, dist, distIndex, () => true, async () => '')
  check('traversal 403', res.status === 403, JSON.stringify(res))
  const res2 = fakeRes()
  await serveStatic('/nope.txt', res2, dist, distIndex, () => true, async () => '')
  check('missing 404', res2.status === 404, JSON.stringify(res2))
}

console.log(`\nRESULT pass=${pass} fail=${fail}`)
await rm(dist, { recursive: true, force: true })
process.exit(fail === 0 ? 0 : 1)
