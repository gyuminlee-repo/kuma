import { describe, it, expect } from "vitest";
import { isExportBlockedError, isStrictFrameMismatchError, describeRpcError } from "../errors";

describe("isStrictFrameMismatchError", () => {
  it("reads the sidecar's frame-mismatch code, not its wording", () => {
    expect(isStrictFrameMismatchError("[-32010] anything the sidecar says")).toBe(true);
    expect(isStrictFrameMismatchError("[-32602] Strict spatial selection requires a unique exact reference placement")).toBe(false);
  });
});

describe("isExportBlockedError", () => {
  it("detects -32004 in message", () => {
    expect(isExportBlockedError("RPC error -32004: Export blocked")).toBe(true);
  });
  it("detects Export blocked prefix", () => {
    expect(isExportBlockedError("Export blocked by policy")).toBe(true);
  });
  it("returns false for unrelated message", () => {
    expect(isExportBlockedError("some other error")).toBe(false);
  });
});

describe("describeRpcError", () => {
  it("maps -32601 Method not found for mame to i18n key", () => {
    const result = describeRpcError(
      { code: -32601, message: "Method not found: generate_mame_package" },
      "mame",
    );
    expect(result).toBe("errors.sidecar.methodNotFound.mame");
  });

  it("maps -32601 for kuro", () => {
    const result = describeRpcError(
      { code: -32601, message: "Method not found: design_primers" },
      "kuro",
    );
    expect(result).toBe("errors.sidecar.methodNotFound.kuro");
  });

  it("detects -32601 from string message without code field", () => {
    const result = describeRpcError(
      "RPC error -32601: Method not found: generate_mame_package",
      "mame",
    );
    expect(result).toBe("errors.sidecar.methodNotFound.mame");
  });

  it("returns original message for unrelated errors", () => {
    const result = describeRpcError(
      { code: -32000, message: "something else" },
      "mame",
    );
    expect(result).toBe("something else");
  });

  it("handles unknown error shape", () => {
    expect(describeRpcError(null, "mame")).toBeTypeOf("string");
  });
});
