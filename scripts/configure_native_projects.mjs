import { access, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const root = new URL('../', import.meta.url).pathname;
const platform = process.argv[2];

if (platform === 'ios') {
  const plistPath = join(root, 'ios', 'App', 'App', 'Info.plist');
  await access(plistPath);
  let plist = await readFile(plistPath, 'utf8');
  if (!plist.includes('NSLocationWhenInUseUsageDescription')) {
    const metadata = [
      '\t<key>NSLocationWhenInUseUsageDescription</key>',
      '\t<string>COFish uses your location only when you ask to plan a drive or find nearby waters.</string>',
      '\t<key>ITSAppUsesNonExemptEncryption</key>',
      '\t<false/>'
    ].join('\n');
    plist = plist.replace(/\n<\/dict>\s*<\/plist>\s*$/, `\n${metadata}\n</dict>\n</plist>\n`);
    await writeFile(plistPath, plist);
  }
  console.log('Configured iOS location disclosure and export compliance metadata');
} else if (platform === 'android') {
  const manifestPath = join(root, 'android', 'app', 'src', 'main', 'AndroidManifest.xml');
  await access(manifestPath);
  let manifest = await readFile(manifestPath, 'utf8');
  if (!manifest.includes('android.permission.ACCESS_FINE_LOCATION')) {
    manifest = manifest.replace('    <!-- Permissions -->', [
      '    <!-- Permissions -->',
      '',
      '    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />',
      '    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />'
    ].join('\n'));
    await writeFile(manifestPath, manifest);
  }
  console.log('Configured Android location permissions');
} else {
  throw new Error('Pass ios or android to configure_native_projects.mjs');
}
