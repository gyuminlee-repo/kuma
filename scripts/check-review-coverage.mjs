import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import { parseArgs } from 'node:util';

// Successor to the historical kuma-exhaustive-20260914/coverage-check.mjs.
const note = 'Receipt validation is not an independent source review. Generated/config/asset/document validation is not counted as manual review. Classification, untracked-file completeness, non-source dispositions and expected HEAD approval are not verified.';
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = value => typeof value === 'string' && value.trim().length > 0;
const pathName = value => text(value) && !value.includes('\\') && !value.includes('\0')
  && !value.includes(':') && value.split('/').every(part => part !== '' && part !== '.' && part !== '..');
const sha256 = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const optional = (entry, key, valid) => !Object.hasOwn(entry, key) || valid(entry[key]);
const stringArray = value => Array.isArray(value) && value.every(text);
const inventoryEntry = item => object(item) && pathName(item.path) && sha256(item.sha256)
  && ['source', 'asset', 'config', 'document'].includes(item.category)
  && optional(item, 'batch', value => typeof value === 'string')
  && optional(item, 'status', text)
  && optional(item, 'lines', value => Number.isInteger(value) && value >= 0);
const receiptEntry = receipt => object(receipt) && pathName(receipt.path) && sha256(receipt.sha256)
  && text(receipt.status) && stringArray(receipt.checks) && receipt.checks.length > 0
  && Array.isArray(receipt.reviewed_ranges)
  && receipt.reviewed_ranges.every(range => Array.isArray(range) && range.length === 2 && range.every(Number.isInteger))
  && optional(receipt, 'findings', stringArray) && optional(receipt, 'limitations', stringArray);

function main() {
  const { values } = parseArgs({ options: {
    root: { type: 'string' }, 'report-dir': { type: 'string' }, inventory: { type: 'string' }, help: { type: 'boolean' },
  } });
  if (values.help) {
    console.log('Usage: node scripts/check-review-coverage.mjs --root <git-root> --report-dir <receipts-dir> [--inventory <json-file>]\nPaths resolve from cwd. Inventory defaults to <receipts-dir>/inventory.json. Reads *.review.json.\n' + note);
    return;
  }
  if (!text(values.root) || !text(values['report-dir']) || (values.inventory !== undefined && !text(values.inventory))) {
    throw new Error('--root and --report-dir are required; paths must be nonempty');
  }
  const root = resolve(values.root);
  const reportDir = resolve(values['report-dir']);
  const inventory = JSON.parse(readFileSync(values.inventory === undefined ? resolve(reportDir, 'inventory.json') : resolve(values.inventory), 'utf8'));
  const receipts = new Map();
  const issues = [];
  const inventoryPaths = new Set();
  if (!Array.isArray(inventory)) {
    console.log(JSON.stringify({ note, issues: [{ issue: 'invalid-inventory' }] }, null, 2));
    process.exitCode = 1;
    return;
  }
  for (const [index, item] of inventory.entries()) {
    if (!inventoryEntry(item)) {
      issues.push({ issue: 'invalid-inventory-entry', index });
      continue;
    }
    if (inventoryPaths.has(item.path)) issues.push({ path: item.path, issue: 'duplicate-inventory-path' });
    inventoryPaths.add(item.path);
  }
  for (const name of readdirSync(reportDir).filter(name => name.endsWith('.review.json')).sort()) {
    const entries = JSON.parse(readFileSync(resolve(reportDir, name), 'utf8'));
    if (!Array.isArray(entries)) {
      issues.push({ issue: 'invalid-receipts', artifact: name });
      continue;
    }
    for (const [index, receipt] of entries.entries()) {
      if (!receiptEntry(receipt)) {
        issues.push({ issue: 'invalid-receipt', artifact: name, index });
        continue;
      }
      if (receipts.has(receipt.path)) issues.push({ path: receipt.path, issue: 'duplicate-receipt', artifact: name });
      const entries = receipts.get(receipt.path) ?? [];
      entries.push(receipt);
      receipts.set(receipt.path, entries);
    }
  }
  const executableExceptions = new Set(['.githooks/post-commit', '.githooks/pre-push']);
  const batches = new Map();
  const missing = [];
  const counted = new Set();
  let reviewed = 0;
  let sourceCount = 0;
  let reviewedLines = 0;
  for (const item of inventory) {
    if (!inventoryEntry(item) || counted.has(item.path)) continue;
    counted.add(item.path);
    const path = resolve(root, item.path);
    if (!existsSync(path)) {
      issues.push({ path: item.path, issue: 'missing-file' });
      continue;
    }
    const bytes = readFileSync(path);
    const hash = createHash('sha256').update(bytes).digest('hex');
    if (hash !== item.sha256) issues.push({ path: item.path, issue: 'inventory-hash-drift' });
    if (item.category !== 'source' && !executableExceptions.has(item.path)) continue;
    sourceCount++;
    const lines = bytes.length === 0 ? 0 : bytes.toString('utf8').split('\n').length - Number(bytes.at(-1) === 10);
    let covered = false;
    for (const receipt of receipts.get(item.path) ?? []) {
      if (receipt.sha256 !== hash) {
        issues.push({ path: item.path, issue: 'receipt-hash-drift' });
        continue;
      }
      if (receipt.status !== 'reviewed') continue;
      let next = 1;
      let valid = true;
      for (const [start, end] of receipt.reviewed_ranges) {
        if (!Number.isInteger(start) || !Number.isInteger(end) || start > next || start < 1 || end < start || end > lines) valid = false;
        next = Math.max(next, end + 1);
      }
      if (valid && next === lines + 1 && receipt.checks.length > 0) covered = true;
      else issues.push({ path: item.path, issue: 'invalid-full-read-receipt' });
    }
    const batch = item.batch || 'executable-exceptions';
    const counts = batches.get(batch) ?? { batch, total: 0, reviewed: 0 };
    counts.total++;
    if (covered) {
      reviewed++;
      reviewedLines += lines;
      counts.reviewed++;
    } else missing.push(item.path);
    batches.set(batch, counts);
  }
  const tracked = execFileSync('git', ['ls-files', '-z'], { cwd: root, encoding: 'utf8' }).split('\0').filter(Boolean);
  for (const path of tracked) if (!inventoryPaths.has(path)) issues.push({ path, issue: 'tracked-not-in-inventory' });
  for (const path of receipts.keys()) if (!inventoryPaths.has(path)) issues.push({ path, issue: 'receipt-outside-inventory' });
  console.log(JSON.stringify({
    head: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
    inventoryFiles: inventory.length, trackedFiles: tracked.length,
    sourceCount, reviewed, reviewedLines, remaining: missing.length,
    note, batches: [...batches.values()], issues, missing,
  }, null, 2));
  process.exitCode = issues.length > 0 || missing.length > 0 ? 1 : 0;
}

try {
  main();
} catch (error) {
  console.log(JSON.stringify({ note, issues: [{ issue: 'input-error', message: error.message }] }, null, 2));
  process.exitCode = 1;
}
