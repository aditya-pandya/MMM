const http = require('http');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const DIST = path.join(ROOT, 'dist');
const PORT = Number(process.env.PORT || 4173);

function buildSite() {
  execFileSync(process.execPath, [path.join(__dirname, 'build.js')], {
    cwd: ROOT,
    stdio: 'inherit',
  });
}

function contentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === '.css') return 'text/css; charset=utf-8';
  if (ext === '.js') return 'text/javascript; charset=utf-8';
  if (ext === '.json') return 'application/json; charset=utf-8';
  if (ext === '.svg') return 'image/svg+xml';
  if (ext === '.png') return 'image/png';
  if (ext === '.jpg' || ext === '.jpeg') return 'image/jpeg';
  if (ext === '.webp') return 'image/webp';
  return 'text/html; charset=utf-8';
}

function resolveFile(urlPath) {
  const cleanPath = decodeURIComponent(urlPath.split('?')[0]);
  const requested = cleanPath === '/' ? '/index.html' : cleanPath;
  let filePath = path.join(DIST, requested);

  if (fs.existsSync(filePath) && fs.statSync(filePath).isDirectory()) {
    filePath = path.join(filePath, 'index.html');
  }

  if (!path.extname(filePath)) {
    filePath = path.join(filePath, 'index.html');
  }

  return filePath;
}

buildSite();

const server = http.createServer((request, response) => {
  try {
    buildSite();
    let filePath = resolveFile(request.url || '/');

    if (!fs.existsSync(filePath)) {
      filePath = path.join(DIST, 'index.html');
      response.statusCode = 404;
    }

    response.setHeader('Content-Type', contentType(filePath));
    response.end(fs.readFileSync(filePath));
  } catch (error) {
    response.statusCode = 500;
    response.setHeader('Content-Type', 'text/plain; charset=utf-8');
    response.end(`Build error:\n${error.stack}`);
  }
});

server.listen(PORT, () => {
  console.log(`MMM dev server running at http://localhost:${PORT}`);
});
