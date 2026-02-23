import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { join, extname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const DIST = join(__dirname, 'dist')
const API = 'http://127.0.0.1:8000'
const PORT = 3080

const MIME = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.eot': 'application/vnd.ms-fontobject',
}

createServer(async (req, res) => {
  // Proxy /api to backend
  if (req.url.startsWith('/api')) {
    try {
      const url = API + req.url
      const headers = { ...req.headers, host: '127.0.0.1:8000' }
      const proxyRes = await fetch(url, {
        method: req.method,
        headers,
        body: ['POST', 'PUT', 'PATCH'].includes(req.method) ? req : undefined,
        duplex: 'half',
      })
      res.writeHead(proxyRes.status, Object.fromEntries(proxyRes.headers))
      const buf = Buffer.from(await proxyRes.arrayBuffer())
      res.end(buf)
    } catch (e) {
      res.writeHead(502)
      res.end('Bad Gateway')
    }
    return
  }

  // Static files
  let filePath = join(DIST, req.url === '/' ? 'index.html' : req.url.split('?')[0])
  try {
    const data = await readFile(filePath)
    const ext = extname(filePath)
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' })
    res.end(data)
  } catch {
    // SPA fallback
    const index = await readFile(join(DIST, 'index.html'))
    res.writeHead(200, { 'Content-Type': 'text/html' })
    res.end(index)
  }
}).listen(PORT, '0.0.0.0', () => {
  console.log(`CRM server running on http://0.0.0.0:${PORT}`)
})
