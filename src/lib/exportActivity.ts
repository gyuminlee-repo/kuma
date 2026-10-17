/**
 * KURO export lease. Exports can overlap (Export All running while a benchmark
 * CSV is saved), and `isExporting` gates closing the window and restarting the
 * sidecar. Each export takes a lease; the flag drops only when the last lease
 * is returned, so the first export to finish cannot release the others.
 */
let activeExports = 0;

export function beginKuroExport(setBusy: (busy: boolean) => void): () => void {
  activeExports += 1;
  setBusy(true);
  let released = false;
  return () => {
    if (released) return;
    released = true;
    activeExports -= 1;
    setBusy(activeExports > 0);
  };
}
