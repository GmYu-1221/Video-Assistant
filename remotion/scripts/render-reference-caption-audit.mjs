import {readFile, rm} from 'node:fs/promises';
import path from 'node:path';
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';

const [, , propsPath, firstFramePath, settledFramePath] = process.argv;

if (!propsPath || !firstFramePath || !settledFramePath) {
  throw new Error('Usage: render-reference-caption-audit.mjs <props> <frame-0-output> <frame-30-output>');
}

const inputProps = {
  ...JSON.parse(await readFile(path.resolve(propsPath), 'utf8')),
  auditEnabled: true,
};
const serveUrl = await bundle({
  entryPoint: path.resolve('src/index.ts'),
  onProgress: () => undefined,
});

try {
  const composition = await selectComposition({
    serveUrl,
    id: 'ReferenceCaptionV1',
    inputProps,
    logLevel: 'error',
  });

  for (const [frame, output] of [[0, firstFramePath], [30, settledFramePath]]) {
    await renderStill({
      serveUrl,
      composition,
      inputProps,
      frame,
      output: path.resolve(output),
      imageFormat: 'png',
      overwrite: true,
      logLevel: 'error',
      onBrowserLog: (log) => process.stderr.write(`[browser:${log.type}] ${log.text}\n`),
      onArtifact: (artifact) => {
        if (artifact.filename.startsWith('reference-caption-audit-')) {
          process.stdout.write(`[REFERENCE_CAPTION_AUDIT]${String(artifact.content)}\n`);
        }
      },
    });
  }
} finally {
  await rm(serveUrl, {recursive: true, force: true});
}
