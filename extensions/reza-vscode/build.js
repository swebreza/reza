// Build script: copies webview assets to dist/
const fs = require('fs');
const path = require('path');

const src = path.join(__dirname, 'src', 'webview');
const dst = path.join(__dirname, 'dist', 'webview');

fs.mkdirSync(dst, { recursive: true });

for (const file of fs.readdirSync(src)) {
  fs.copyFileSync(path.join(src, file), path.join(dst, file));
  console.log(`Copied ${file} → dist/webview/${file}`);
}
