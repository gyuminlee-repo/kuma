import { invoke } from "@tauri-apps/api/core";
import type { MergedRow, MergeStats, PlateMeta } from "@/types/mame/activity";

export type SidecarKind = "kuro" | "mame";

function hasTauriBridge(): boolean {
  return typeof (globalThis as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ !== "undefined";
}

export async function rpc<T = unknown>(
  kind: SidecarKind,
  method: string,
  params: unknown = {},
): Promise<T> {
  if (!hasTauriBridge()) {
    throw new Error("Tauri bridge unavailable");
  }
  return invoke("sidecar_rpc", { kind, method, params }) as Promise<T>;
}

export async function killSidecar(kind: SidecarKind): Promise<void> {
  if (!hasTauriBridge()) {
    return;
  }
  await invoke("sidecar_kill", { kind });
}

export async function isSidecarRunning(kind: SidecarKind): Promise<boolean> {
  if (!hasTauriBridge()) {
    return false;
  }
  return invoke("sidecar_is_running", { kind }) as Promise<boolean>;
}

// ─── MAME activity RPC client functions ──────────────────────────────────────

/**
 * 활성 데이터 파일 업로드.
 * MAME sidecar activity.upload 호출.
 */
export async function activityUpload(
  round_id: string,
  file_path: string,
  format: "long_csv" | "long_xlsx",
): Promise<{ records: unknown[]; plate_meta: PlateMeta }> {
  return rpc("mame", "activity.upload", { round_id, file_path, format });
}

/**
 * WT 웰 / 컨트롤 웰 메타 설정.
 * MAME sidecar activity.set_plate_meta 호출.
 */
export async function activitySetPlateMeta(
  round_id: string,
  plate_meta: PlateMeta,
): Promise<void> {
  return rpc("mame", "activity.set_plate_meta", { round_id, plate_meta });
}

/**
 * KURO 디자인 + 활성 데이터 병합.
 * MAME sidecar activity.merge 호출.
 */
export async function activityMerge(
  round_id: string,
): Promise<{ merged: MergedRow[]; stats: MergeStats }> {
  return rpc("mame", "activity.merge", { round_id });
}

/**
 * EVOLVEpro CSV 내보내기.
 * MAME sidecar activity.export_evolvepro_csv 호출.
 */
export async function activityExportEvolveproCsv(
  round_id: string,
  path: string,
): Promise<{ path: string }> {
  return rpc("mame", "activity.export_evolvepro_csv", { round_id, path });
}

/**
 * EVOLVEpro xlsx 내보내기 (혜민 연구원 spec v0.3 §2.4 준수).
 * MAME sidecar activity.export_evolvepro_xlsx 호출.
 */
export async function activityExportEvolveproXlsx(
  round_id: string,
  path: string,
): Promise<{ path: string }> {
  return rpc("mame", "activity.export_evolvepro_xlsx", { round_id, path });
}
