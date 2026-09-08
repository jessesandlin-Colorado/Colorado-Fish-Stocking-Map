import { cp, mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import { extname, join } from 'node:path';

const root = new URL('../', import.meta.url).pathname;
const output = join(root, 'mobile-web');
const webExtensions = new Set([
  '.css', '.html', '.ico', '.jpeg', '.jpg', '.js', '.json', '.png', '.svg',
  '.txt', '.webmanifest', '.xml'
]);
const excludedFiles = new Set(['package.json', 'package-lock.json', 'capacitor.config.ts']);
const webDirectories = ['assets', 'config', 'data'];

await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });

for (const entry of await readdir(root, { withFileTypes: true })) {
  if (!entry.isFile() || excludedFiles.has(entry.name) || !webExtensions.has(extname(entry.name))) continue;
  await cp(join(root, entry.name), join(output, entry.name));
}
for (const directory of webDirectories) {
  await cp(join(root, directory), join(output, directory), { recursive: true });
}

await mkdir(join(output, 'vendor', 'leaflet', 'images'), { recursive: true });
await cp(join(root, 'node_modules', 'leaflet', 'dist', 'leaflet.js'), join(output, 'vendor', 'leaflet', 'leaflet.js'));
await cp(join(root, 'node_modules', 'leaflet', 'dist', 'leaflet.css'), join(output, 'vendor', 'leaflet', 'leaflet.css'));
await cp(join(root, 'node_modules', 'leaflet', 'dist', 'images'), join(output, 'vendor', 'leaflet', 'images'), { recursive: true });

const indexPath = join(output, 'index.html');
let index = await readFile(indexPath, 'utf8');
index = index
  .replace('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css', 'vendor/leaflet/leaflet.css')
  .replace('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js', 'vendor/leaflet/leaflet.js');
index = index.replace('</head>', '<script src="native-bridge.js"></script></head>');
await writeFile(indexPath, index);

await writeFile(join(output, 'mobile-build.json'), JSON.stringify({
  generated_at: new Date().toISOString(),
  source: 'COFish repository mobile package'
}, null, 2));

console.log(`Prepared Capacitor web assets in ${output}`);
