import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const scriptDir = dirname(fileURLToPath(import.meta.url));
const legacy = process.env.FC02_LEGACY_CHECKER;
const pin = process.env.FC02_PIN_LEGACY === '1';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const cases = [
  ['valid2line', () => {}, null],
  ['duplicate-inventory', f => f.inventory.push({ ...f.inventory[0] }), 'duplicate-inventory-path'],
  ['checks-string', f => { f.receipts[0].checks = 'x'; }, 'invalid-receipt'],
  ['triple-range', f => { f.receipts[0].reviewed_ranges = [[1, 2, 999]]; }, 'invalid-receipt'],
  ['leading-gap', f => { f.receipts[0].reviewed_ranges = [[2, 2]]; }, 'invalid-full-read-receipt'],
  ['wrong-receipt-hash', f => { f.receipts[0].sha256 = '0'.repeat(64); }, 'receipt-hash-drift'],
  ['wrong-inventory-hash', f => { f.inventory[0].sha256 = '0'.repeat(64); }, 'inventory-hash-drift'],
  ['duplicate-receipt', f => f.receipts.push({ ...f.receipts[0] }), 'duplicate-receipt'],
  ['missing-receipt', f => { f.receipts = []; }, 'missing'],
  ['outside-inventory', f => f.receipts.push({ ...f.receipts[0], path: 'other.js' }), 'receipt-outside-inventory'],
  ['overlap', f => { f.receipts[0].reviewed_ranges = [[1, 2], [2, 2]]; }, null],
  ['empty-file', f => { f.bytes = ''; f.receipts[0].reviewed_ranges = []; }, null],
  ['no-final-newline', f => { f.bytes = 'one\ntwo'; }, null],
  ['range-past-end', f => { f.receipts[0].reviewed_ranges = [[1, 3]]; }, 'invalid-full-read-receipt'],
  ['hook-exception', f => { f.inventory[0].path = f.receipts[0].path = '.githooks/pre-push'; f.inventory[0].category = 'asset'; f.receipts = []; }, 'missing'],
  ['inventory-object', f => { f.inventory = {}; }, 'invalid-inventory'],
  ['inventory-null-row', f => { f.inventory = [null]; }, 'invalid-inventory-entry'],
  ['receipts-object', f => { f.receipts = {}; }, 'invalid-receipts'],
  ['receipt-null-row', f => { f.receipts = [null]; }, 'invalid-receipt'],
];
for (const [field, values] of Object.entries({
  path: [null, 1, {}, '', '../source.js', './source.js'],
  sha256: [null, 1, {}, ''],
  category: [null, 1, {}, '', 'unknown'],
  batch: [null, 1, {}],
  lines: [null, '2', -1, 1.5],
  status: [null, 1, {}],
})) {
  for (const value of values) cases.push([
    `inventory-${field}-${JSON.stringify(value)}`,
    f => { f.inventory[0][field] = value; }, 'invalid-inventory-entry',
  ]);
}
for (const [field, values] of Object.entries({
  path: [null, 1, {}, ''], sha256: [null, 1, {}, ''], status: [null, 1, {}, ''],
  checks: [null, {}, [], [1], [' ']],
  reviewed_ranges: [null, {}, '12', ['12'], [[1]], [[1, '2']], [[1, 1.5]]],
})) {
  for (const value of values) cases.push([
    `receipt-${field}-${JSON.stringify(value)}`,
    f => { f.receipts[0][field] = value; }, 'invalid-receipt',
  ]);
}

test('review coverage through the real CLI', async t => {
  const temporary = mkdtempSync(join(tmpdir(), 'fc02-'));
  console.log(`fixture: ${temporary}`);
  try {
    const root = join(temporary, 'repo');
    // Reuse HEAD objects without creating commits or staging fixture files.
    execFileSync('git', ['clone', '--shared', '--no-checkout', resolve(scriptDir, '..'), root], { stdio: 'pipe' });
    const reportDir = join(root, '.omo', 'reports', 'fixture');
    mkdirSync(reportDir, { recursive: true });
    const inventoryPath = join(reportDir, legacy ? 'inventory.json' : 'custom-inventory.json');
    const checker = legacy ? join(reportDir, 'coverage-check.mjs') : join(scriptDir, 'check-review-coverage.mjs');
    if (legacy) {
      const bytes = readFileSync(resolve(legacy));
      writeFileSync(checker, bytes);
      console.log(`legacy-sha256: ${hash(bytes)}`);
    }
    const selected = pin ? cases.slice(0, 6) : cases;
    for (const [name, mutate, issue] of selected) {
      await t.test(name, () => {
        const f = {
          bytes: 'one\ntwo\n',
          inventory: [{ path: 'source.js', sha256: hash('one\ntwo\n'), category: 'source', lines: 2, status: 'pending', batch: 'fixture' }],
          receipts: [{ path: 'source.js', sha256: hash('one\ntwo\n'), status: 'reviewed', reviewed_ranges: [[1, 2]], checks: ['full read'] }],
        };
        mutate(f);
        if (f.bytes !== 'one\ntwo\n') {
          f.inventory[0].sha256 = f.receipts[0].sha256 = hash(f.bytes);
          f.inventory[0].lines = f.bytes === '' ? 0 : 2;
        }
        const source = join(root, Array.isArray(f.inventory) && typeof f.inventory[0]?.path === 'string' && f.inventory[0].path.startsWith('.githooks/') ? f.inventory[0].path : 'source.js');
        mkdirSync(dirname(source), { recursive: true });
        writeFileSync(source, f.bytes);
        writeFileSync(inventoryPath, JSON.stringify(f.inventory));
        writeFileSync(join(reportDir, 'fixture.review.json'), JSON.stringify(f.receipts));
        const args = legacy ? [checker] : [checker, '--root', root, '--report-dir', reportDir, '--inventory', inventoryPath];
        const result = spawnSync(process.execPath, args, { cwd: temporary, encoding: 'utf8' });
        assert.ifError(result.error);
        const knownBypass = ['duplicate-inventory', 'checks-string', 'triple-range'].includes(name);
        const expected = issue && !(pin && knownBypass) ? 1 : 0;
        console.log(JSON.stringify({ name, command: [process.execPath, ...args], expected, status: result.status, stdout: result.stdout, stderr: result.stderr }));
        assert.equal(result.status, expected, `${name}: expected CLI exit ${expected}, got ${result.status}`);
        const output = JSON.parse(result.stdout);
        if (expected === 0) {
          assert.equal(output.reviewed, pin && name === 'duplicate-inventory' ? 2 : 1);
          assert.equal(output.reviewedLines, f.bytes === '' ? 0 : pin && name === 'duplicate-inventory' ? 4 : 2);
          assert.deepEqual(output.issues, []);
        } else if (issue === 'missing') assert.equal(output.remaining, 1);
        else assert.ok(output.issues.some(entry => entry.issue === issue), `missing issue ${issue}`);
      });
    }
  } finally {
    rmSync(temporary, { recursive: true, force: true });
    assert.equal(existsSync(temporary), false);
    console.log(`cleanup: removed ${temporary}; exists=false`);
  }
});
