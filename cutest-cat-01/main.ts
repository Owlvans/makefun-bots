// cutest-cat-01 entry (Node 22, standard library only): copies the cat picture stored in this repository
// (cat.jpg, a white kitten with blue eyes among daisies) to /output/entry.png. The gate accepts PNG or JPEG
// bytes under that name; cat.jpg is a JPEG of 683x1024, 155 KB, inside the 1024x1024 / 1 MiB limits.
// Outside the grader's container, MAKEFUN_OUTPUT_DIR stands in for /output:
//   mkdir -p out && MAKEFUN_OUTPUT_DIR=out node main.ts

import { copyFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUTPUT_DIR = process.env.MAKEFUN_OUTPUT_DIR ?? '/output';
const HERE = dirname(fileURLToPath(import.meta.url));

mkdirSync(OUTPUT_DIR, { recursive: true });
copyFileSync(join(HERE, 'cat.jpg'), join(OUTPUT_DIR, 'entry.png'));
