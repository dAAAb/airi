import path from 'node:path'
import process from 'node:process'

import { mkdir } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

async function main() {
  const root = path.dirname(fileURLToPath(import.meta.url))
  const repo = path.resolve(root, '../../..')
  const webRequire = createRequire(path.join(repo, 'apps/stage-web/package.json'))
  const viteRequire = createRequire(webRequire.resolve('vite'))
  const { build } = viteRequire('esbuild')
  await mkdir(path.join(root, '.compiled'), { recursive: true })

  // Bundle the existing workspace Eventa dependency. The sandboxed preload exposes
  // fixed desktop commands and never exposes ipcRenderer or Node to the page.
  for (const [entry, platform, output] of [
    ['main.cjs', 'node', 'main.cjs'],
    ['preload.mjs', 'browser', 'preload.cjs'],
  ]) {
    await build({
      absWorkingDir: repo,
      entryPoints: [path.join(root, entry)],
      outfile: path.join(root, '.compiled', output),
      bundle: true,
      platform,
      format: 'cjs',
      target: 'es2022',
      external: ['electron'],
      nodePaths: [path.join(repo, 'apps/stage-web/node_modules')],
      sourcemap: false,
      legalComments: 'eof',
    })
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
