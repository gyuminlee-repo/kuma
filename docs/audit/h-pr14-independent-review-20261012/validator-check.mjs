import { registerHooks } from 'node:module';
import { existsSync,readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
registerHooks({resolve(specifier, context, nextResolve) {
 if(specifier.startsWith('.') && context.parentURL) {
  const url=new URL(specifier+'.ts',context.parentURL);
  if(existsSync(url))return nextResolve(url.href,context);
 }
 return nextResolve(specifier,context);
}});
const v=await import('./source/src/types/validators.ts');
const data=JSON.parse(readFileSync(new URL('./fixtures/csv-result.json',import.meta.url),'utf8'));
console.log('exports',Object.keys(v));
const valid=v.getRpcResultValidator('load_evolvepro_csv');
assert.equal(valid(data),true);console.log('PASS actual CSV result accepted by actual TS validator');
for(const [name,mutate] of [
 ['invalid threshold',x=>x.strict_spatial.coordinate_confidence.threshold=49],
 ['incorrect exclusion count',x=>x.strict_spatial.coordinate_confidence.excluded_variant_count=0],
 ['old universe',x=>x.strict_spatial.comparison.universe='eligible-variants-after-budget-and-cap-policy'],
 ['missing secondary baseline',x=>delete x.strict_spatial.comparison.representative_top_n],
]){const x=structuredClone(data);mutate(x);assert.equal(valid(x),false);console.log('PASS rejects',name)}
