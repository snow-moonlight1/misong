// usage: node hajimi_node.mjs enc|dec  < stdin(utf8, one trailing newline stripped)
import { translate } from './ref-bundle.mjs'
const mode = process.argv[2]
const chunks = []
for await (const c of process.stdin) chunks.push(c)
let input = Buffer.concat(chunks).toString('utf8')
if (input.endsWith('\n')) input = input.slice(0, -1)
const res = translate(input, mode === 'enc' ? 'human' : 'hachimi')
if (!res.ok) { console.error('FAIL ' + res.error); process.exit(1) }
process.stdout.write(res.output)
