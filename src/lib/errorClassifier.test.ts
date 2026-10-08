import { describe, expect, it } from "vitest";

import { classifyError } from "./errorClassifier";

describe("classifyError", () => {
  it("TLS 인증서 검증 실패를 network 로 분류한다", () => {
    const raw =
      "UniProt search error: URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] " +
      "certificate verify failed: unable to get local issuer certificate>";
    expect(classifyError(raw).kind).toBe("network");
  });

  it("사이드카가 붙인 CA 안내 문구만으로도 network 로 분류한다", () => {
    // TLS_REMEDY 본문 그대로. OpenSSL 문구가 뒤에 붙지 않아도 분류되어야 한다.
    // macOS·Windows 네이티브 검증기는 CERTIFICATE_VERIFY_FAILED 를 쓰지 않을 수 있다.
    const raw =
      "TLS certificate verification failed. This network may run a TLS inspection " +
      "proxy whose CA kuma does not trust. Install that CA in the operating system " +
      "trust store (macOS Keychain, the Windows certificate store, or " +
      "update-ca-certificates on Linux). If that is not possible, export the CA as " +
      "a PEM file and set KURO_CA_BUNDLE=<path> or add " +
      '"ca_bundle": "<path>" to ~/.kuma/kuro/config.json. Restart kuma afterwards.';
    const classified = classifyError(raw);
    expect(classified.kind).toBe("network");
    expect(classified.message).toContain("KURO_CA_BUNDLE");
  });

  it("OpenSSL 처럼 ssl 이 단어 일부인 문자열은 network 로 오분류하지 않는다", () => {
    expect(classifyError("built against OpenSSL 3.0.2").kind).toBe("unknown");
  });

  it("기존 분류는 그대로 유지한다", () => {
    expect(classifyError("[-32603] RuntimeError: boom").kind).toBe("sidecar");
    expect(classifyError("[-32602] invalid input").kind).toBe("validation");
    expect(classifyError("connection timeout").kind).toBe("network");
  });
});
