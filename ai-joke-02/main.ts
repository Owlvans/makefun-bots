// ai-joke-02 entry (Node 22, standard library only): writes one one-liner about AI coding agents to
// /output/entry.txt. The joke: an agent that never admits doubt, it just says "Certainly!" and invents an API.
// Outside the grader's container, MAKEFUN_OUTPUT_DIR stands in for /output:
//   MAKEFUN_OUTPUT_DIR=out node main.ts

import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

const OUTPUT_DIR = process.env.MAKEFUN_OUTPUT_DIR ?? '/output';

mkdirSync(OUTPUT_DIR, { recursive: true });
writeFileSync(join(OUTPUT_DIR, 'entry.txt'), 'My coding agent never says "I don\'t know." It says "Certainly!" and invents an API with total confidence.');
