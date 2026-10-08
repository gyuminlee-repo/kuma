/**
 * The contact email EBI Job Dispatcher (BLAST, InterProScan) asks every
 * submitter for. It is sent to EBI and nowhere else.
 *
 * Only a shape check: something, one @, a dotted domain. The sidecar applies
 * the same pattern (`_EMAIL_SHAPE` in python-core/sidecar_kuro/core.py) and
 * treats anything else as absent, so the two must agree or a saved address
 * would be asked for again.
 */
const EMAIL_SHAPE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function isValidContactEmail(value: string): boolean {
  return EMAIL_SHAPE.test(value.trim());
}
