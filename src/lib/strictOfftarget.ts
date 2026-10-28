/**
 * Marker the design engine puts at the front of a failure reason that the
 * strict off-target check alone caused.
 *
 * The reason string is engine prose shown verbatim, so this prefix is the only
 * machine-readable part of it. It must stay equal to
 * `STRICT_OFFTARGET_FAILURE_MARKER` in `kuma_core/kuro/sdm_engine.py`; the
 * `kuro-strict-offtarget-marker` group in `.cross-layer-sync.json` is what
 * notices if one side moves.
 */
export const STRICT_OFFTARGET_FAILURE_MARKER = "strict off-target";
