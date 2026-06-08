import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-evolvepro", () => ({
  condaDetect: vi.fn(),
  condaDetectEnv: vi.fn(),
  condaInstallRemovePrefix: vi.fn(),
  condaVerifyEnv: vi.fn(),
}));

import {
  condaDetect,
  condaDetectEnv,
  condaVerifyEnv,
} from "@/lib/ipc-evolvepro";
import type { CondaStatus, EnvStatus } from "@/types/models.evolvepro";
import { useCondaSetupStore } from "./condaSetupStore";

const condaInstalled = {
  installed: true,
  conda_exe: "/tmp/conda",
  version: "24.1.0",
} satisfies CondaStatus;

const completePackages = {
  evolvepro: "1.0.0",
  esm: "2.0.0",
  Bio: "1.85",
  numpy: "2.0.0",
  pandas: "2.2.0",
  openpyxl: "3.1.0",
  sklearn: "1.5.0",
  sklearn_extra: "0.3.0",
  scipy: "1.14.0",
  xgboost: "2.1.0",
  matplotlib: "3.9.0",
  seaborn: "0.13.0",
  torch: "2.4.0",
};

function envStatus(packages: EnvStatus["packages"]): EnvStatus {
  return {
    exists: true,
    env_path: "/tmp/envs/evolvepro",
    packages,
  };
}

describe("useCondaSetupStore", () => {
  beforeEach(() => {
    useCondaSetupStore.getState().reset();
    vi.clearAllMocks();
  });

  it("skips duplicate verify during detect when package probing is complete", async () => {
    vi.mocked(condaDetect).mockResolvedValue(condaInstalled);
    vi.mocked(condaDetectEnv).mockResolvedValue(envStatus(completePackages));

    await useCondaSetupStore.getState().detect();

    expect(condaVerifyEnv).not.toHaveBeenCalled();
    expect(useCondaSetupStore.getState().stage).toBe("done");
  });

  it("keeps the verify fallback during detect when package probing is incomplete", async () => {
    vi.mocked(condaDetect).mockResolvedValue(condaInstalled);
    vi.mocked(condaDetectEnv).mockResolvedValue(
      envStatus({ ...completePackages, torch: null }),
    );
    vi.mocked(condaVerifyEnv).mockResolvedValue({ ok: false, error: "missing torch" });

    await useCondaSetupStore.getState().detect();

    expect(condaVerifyEnv).toHaveBeenCalledWith("evolvepro", "/tmp/conda");
    expect(useCondaSetupStore.getState().stage).toBe("needs_repair");
  });

  it("skips duplicate verify during runAuto when package probing is complete", async () => {
    vi.mocked(condaDetect).mockResolvedValue(condaInstalled);
    vi.mocked(condaDetectEnv).mockResolvedValue(envStatus(completePackages));

    await useCondaSetupStore.getState().runAuto();

    expect(condaVerifyEnv).not.toHaveBeenCalled();
    expect(useCondaSetupStore.getState().stage).toBe("done");
  });
});
