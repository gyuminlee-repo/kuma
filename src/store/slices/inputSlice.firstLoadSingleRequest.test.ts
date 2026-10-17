/**
 * A first EVOLVEpro load with fewer variants than the design count must send
 * load_evolvepro_csv once. The shrink of the design count used to go through
 * setMaxPrimers, which still saw a first load (no count, no mutation text),
 * read it as a failed load and sent the same request again.
 *
 * Runs on the real store so setMaxPrimers and its recovery path are the
 * shipped ones; a mocked setter cannot reproduce the double request.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}))
vi.mock("@tauri-apps/api/path", () => ({ resolveResource: vi.fn() }))

import { useAppStore } from "../appStore"
import { sendRequest } from "@/lib/ipc-kuro"

const mockSend = vi.mocked(sendRequest)

const TWO_VARIANTS = {
  variants: ["A2G", "K5R"],
  y_preds: [0.9, 0.5],
  total_count: 2,
  selected_count: 2,
}

function loadCalls(): number {
  return mockSend.mock.calls.filter((c) => c[0] === "load_evolvepro_csv").length
}

describe("first EVOLVEpro load", () => {
  const initial = useAppStore.getState()

  beforeEach(() => {
    mockSend.mockReset()
    mockSend.mockResolvedValue(TWO_VARIANTS as never)
    useAppStore.setState({
      mutationInputMode: "evolvepro",
      mutationText: "",
      evolveproCsvPath: "/fake/df_test.csv",
      evolveproTotalCount: 0,
      maxPrimers: 95,
    })
  })

  afterEach(() => {
    useAppStore.setState(initial, true)
  })

  it("sends one request when the file has fewer variants than the design count", async () => {
    await useAppStore.getState().loadEvolveproCsv("/fake/df_test.csv")
    // Let a recovery reload fired without await reach sendRequest.
    await Promise.resolve()
    expect(loadCalls()).toBe(1)
    expect(useAppStore.getState().maxPrimers).toBe(2)
    expect(useAppStore.getState().evolveproTotalCount).toBe(2)
  })
})
