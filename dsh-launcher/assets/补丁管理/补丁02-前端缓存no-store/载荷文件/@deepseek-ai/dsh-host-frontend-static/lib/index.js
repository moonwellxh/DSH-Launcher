import { readFile, stat } from "node:fs/promises";
import { basename, dirname, extname, join, normalize, resolve, sep } from "node:path";
import z from "@deepseek-ai/schemastery";
//#region lib/types/index.js
/**
* @deepseek-ai/dsh-host-frontend-static — SPA dist server over the webserver
* fallback seat: serves the built frontend directory with explicit index
* entry points. A readable index renders at the dist root and configured index
* path; missing paths return 404, traversal outside the dist root is 403,
* unknown extensions ship as octet-stream, and non-GET/HEAD is 405. Every
* index response first passes Connection's browser authentication, then the
* webserver's index render (structured injection rows, then raw taps).
* Non-index assets stay public. A rendered document is served `no-store`
* because it embeds the boot graph of the process that rendered it, a
* content-addressed file is immutable, and every other file revalidates
* against a size/mtime validator. The dist location is workspace knowledge of
* the composing application, so `distIndex` is typically supplied through a
* `!!js` expression, never hardcoded by a deployment.
* @module @deepseek-ai/dsh-host-frontend-static
*/
/** Stable Cordis plugin name. */
const name = "frontend-static";
/** Services required before the authenticated fallback seat can be claimed. */
const inject = ["webServer", "connection"];
const Config = z.object({ distIndex: z.string().required() });
const HTML_MIME = "text/html; charset=utf-8";
/**
* The rendered document embeds the boot graph composed by the running host, so
* reusing a stored copy after a restart, an upgrade, or a rebuild pairs that
* document with client artifacts it was not rendered for. It is also small and
* generated per request. Never let a browser reuse it.
*/
const INDEX_CACHE = "no-store";
/**
* Bundler output names carry a content hash, so a given name can only ever
* describe one byte sequence: a stored copy can never be stale.
*/
const IMMUTABLE_CACHE = "public, max-age=31536000, immutable";
/**
* Everything else (favicon, web manifest, any unhashed file) keeps its stored
* copy but must revalidate, which the validator below answers with a 304.
*/
const REVALIDATE_CACHE = "no-cache";
/**
* Vite's `[name]-[hash][extname]` output convention. Only names matching it may
* claim immutability; a shorter or differently spelled hash degrades to
* revalidation, never to a stored copy a rebuild cannot replace.
*/
const CONTENT_ADDRESSED_NAME = /-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+$/u;
const MIME = {
	".html": HTML_MIME,
	".js": "text/javascript; charset=utf-8",
	".css": "text/css; charset=utf-8",
	".svg": "image/svg+xml",
	".json": "application/json",
	".map": "application/json",
	".webmanifest": "application/manifest+json",
	".gz": "application/gzip"
};
const STATIC_MISS_CODES = new Set([
	"ENOENT",
	"EISDIR",
	"ENOTDIR"
]);
/**
* Serve one GET/HEAD static request from the dist root.
* @param pathname - decoded URL pathname of the request.
* @param res - the node:http response to write.
* @param distRoot - absolute dist root directory (resolved by the caller).
* @param distIndex - absolute path of index.html inside distRoot.
* @param authorizeIndex - authenticates an index response before its bytes are read.
* @param renderIndex - produces the index.html body (structured injection
* rendering) for the dist root and configured index path.
* @param ifNoneMatch - the request's `if-none-match` header, compared against
* the validator a stored file response carries.
*/
async function serveStatic(pathname, res, distRoot, distIndex, authorizeIndex, renderIndex, ifNoneMatch) {
	const target = resolve(normalize(join(distRoot, pathname)));
	if (target !== distRoot && !target.startsWith(distRoot + sep)) {
		res.writeHead(403);
		res.end();
		return;
	}
	let body;
	let type;
	let isIndex = false;
	let etag;
	try {
		if (target === distRoot || target === distIndex) {
			if (!authorizeIndex()) return;
			body = await renderIndex();
			type = HTML_MIME;
			isIndex = true;
		} else {
			const info = await stat(target);
			body = await readFile(target);
			type = MIME[extname(target)] ?? "application/octet-stream";
			etag = `W/"${String(info.size)}-${String(Math.trunc(info.mtimeMs))}"`;
		}
	} catch (error) {
		if (!STATIC_MISS_CODES.has(error.code)) throw error;
		res.writeHead(404);
		res.end();
		return;
	}
	if (isIndex) {
		res.writeHead(200, {
			"content-type": type,
			"cache-control": INDEX_CACHE
		});
		res.end(body);
		return;
	}
	const cacheControl = CONTENT_ADDRESSED_NAME.test(basename(target)) ? IMMUTABLE_CACHE : REVALIDATE_CACHE;
	const headers = {
		"content-type": type,
		"cache-control": cacheControl
	};
	if (etag !== void 0) headers.etag = etag;
	if (etag !== void 0 && ifNoneMatch === etag) {
		res.writeHead(304, headers);
		res.end();
		return;
	}
	res.writeHead(200, headers);
	res.end(body);
}
/**
* Claim the webserver fallback seat and serve the dist.
* @param ctx - plugin context carrying the webServer service.
* @param config - validated {@link Config}.
*/
function apply(ctx, config) {
	const distIndex = config.distIndex;
	const distRoot = dirname(distIndex);
	const renderIndex = async () => {
		return ctx.webServer.renderIndex(await readFile(distIndex, "utf8")).replace(/<head(?:\s[^>]*)?>/i, (open) => `${open}<base href="/">`);
	};
	ctx.effect(() => ctx.webServer.registerFallback(async (req, res) => {
		if (req.method !== "GET" && req.method !== "HEAD") {
			res.writeHead(405);
			res.end();
			return;
		}
		/* v8 ignore next -- node:http always sets url on server requests */
		const rawPath = new URL(req.url ?? "/", "http://x").pathname;
		await serveStatic(decodeURIComponent(rawPath), res, distRoot, distIndex, () => ctx.connection.authorizeIndex(req, res), renderIndex, req.headers["if-none-match"]);
	}), "frontend-static: fallback seat");
}
//#endregion
export { Config, apply, inject, name, serveStatic };
