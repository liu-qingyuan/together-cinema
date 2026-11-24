import {build} from 'esbuild';
import {readFileSync} from 'node:fs';
const license = readFileSync('../../LICENSES/comfort-motion.txt', 'utf8');
await build({entryPoints:['entry.mjs'], bundle:true, minify:true, format:'esm', target:'es2020',
  banner:{js:'/*!\n'+license.replaceAll('*/','* /')+'\n*/'},
  outfile:'../assets/comfort-motion-1.js'});
