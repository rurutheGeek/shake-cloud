import { build } from 'esbuild';

await build({
  entryPoints: ['src/main.js'],
  bundle: true,
  format: 'esm',
  minify: true,
  sourcemap: false,
  target: ['chrome100'],
  // 生成物はスタック直下へ置き、Ansible が portal.py と一緒に配る。
  outfile: '../portal-backup.js',
  logLevel: 'info',
});
