import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptsDir = path.dirname(fileURLToPath(import.meta.url));
const webDir = path.resolve(scriptsDir, '..');
const repoDir = path.resolve(webDir, '..');
const sourcePath = path.join(webDir, 'public', 'ui-visibility.json');
const targetPath = path.join(
  repoDir,
  'packages',
  'dbgpt-app',
  'src',
  'dbgpt_app',
  'static',
  'web',
  'ui-visibility.json',
);

const source = JSON.parse(fs.readFileSync(sourcePath, 'utf8'));
if (source.version !== 1) throw new Error('Unsupported ui-visibility.json version');
const normalized = `${JSON.stringify(source, null, 2)}\n`;
const current = fs.existsSync(targetPath) ? fs.readFileSync(targetPath, 'utf8') : '';

if (process.argv.includes('--check')) {
  if (current !== normalized) {
    console.error(`Static UI visibility config is out of date: ${targetPath}`);
    process.exitCode = 1;
  } else {
    console.log('UI visibility configs are synchronized.');
  }
} else if (current !== normalized) {
  fs.writeFileSync(targetPath, normalized, 'utf8');
  console.log(`Synchronized ${path.relative(repoDir, targetPath)}`);
} else {
  console.log('UI visibility configs are already synchronized.');
}
