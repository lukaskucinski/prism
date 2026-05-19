import fs from "node:fs";
const cat = JSON.parse(fs.readFileSync("modal/prism/config/layers_config.json", "utf8"));
const seen = new Map();
for (const e of cat) {
  const k = `${e.name}|${e.url}|${e.layer_id}`;
  seen.set(k, (seen.get(k) || 0) + 1);
}
const dupes = [...seen.entries()].filter(([_, n]) => n > 1);
console.log("Catalog size:", cat.length);
console.log("Distinct (name,url,layer_id):", seen.size);
console.log("Duplicate rows:", dupes.length, "(total extra:", dupes.reduce((s,[_,n]) => s + (n-1), 0), ")");
console.log("\nFirst 5 duplicates:");
for (const [k, n] of dupes.slice(0, 5)) console.log(`  ${n}x  ${k}`);
