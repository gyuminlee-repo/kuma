/**
 * Fixed string the design engine puts inside a failure reason that the strict
 * off-target check alone caused.
 *
 * The reason is engine prose shown verbatim and the string does not sit at a
 * fixed offset in it, so it is found by substring search (`includes`) rather
 * than by a prefix test. It must stay equal to
 * `STRICT_OFFTARGET_FAILURE_MARKER` in `kuma_core/kuro/sdm_engine.py`; the
 * `kuro-strict-offtarget-marker` group in `.cross-layer-sync.json` is what
 * notices if one side moves.
 */
export const STRICT_OFFTARGET_FAILURE_MARKER = "strict off-target";
