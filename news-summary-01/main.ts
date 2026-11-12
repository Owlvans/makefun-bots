// news-summary-01 entry (Node 22, standard library only): copies the summary stored in this repository
// (summary.txt, a summary of the world's news of Wednesday 11 November 2026, 1,997 characters, inside
// the gate's 1-2,000) to /output/entry.txt. Outside the grader's container, MAKEFUN_OUTPUT_DIR stands
// in for /output:   MAKEFUN_OUTPUT_DIR=out node main.ts
// The summary is ranked by importance, one story per line, each closing with its named source.

import { copyFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUTPUT_DIR = process.env.MAKEFUN_OUTPUT_DIR ?? '/output';
const HERE = dirname(fileURLToPath(import.meta.url));

mkdirSync(OUTPUT_DIR, { recursive: true });
copyFileSync(join(HERE, 'summary.txt'), join(OUTPUT_DIR, 'entry.txt'));
