/** Shared validation rules for export options and the final export action. */
export const PLATE_NAME_RE = /^[A-Za-z0-9_-]{1,20}$/;
export const PROJECT_NAME_RE = /^[A-Za-z0-9\uAC00-\uD7A3_\-]{0,40}$/;

/** Message for each reason a round cannot be exported yet. */
export const ROUND_ISSUE_KEYS = {
  plateUnpicked: "phaseC.export.all.rounds.choosePlate",
  quadrantUnpicked: "phaseC.export.all.rounds.chooseFirst",
  duplicate: "phaseC.export.all.rounds.duplicate",
  quadrantAlreadyUsed: "phaseC.export.all.placementBlocked.quadrantAlreadyUsed",
} as const;
