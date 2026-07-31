/**
 * pathRef: how an autosave snapshot stores a file path.
 *
 * The whole point is that a project folder can be copied elsewhere and still
 * open. So the round trip is pinned against a *different* project root than
 * the one that wrote the snapshot: an in-project path must follow the folder,
 * and an out-of-project path must not be silently rewritten to point inside it.
 */

import { describe, expect, it } from "vitest";
import {
  asExternalRef,
  baseName,
  fromPathRef,
  toPathRef,
  type PathRef,
} from "./pathRef";

describe("toPathRef", () => {
  it("stores a path inside the project as a relative one", () => {
    const ref = toPathRef("/proj", "/proj/design/primers.xlsx");
    expect(ref).toEqual({ kind: "project", rel: "design/primers.xlsx" });
  });

  it("stores a path outside the project as an external reference", () => {
    const ref = toPathRef("/proj", "/data/20260212_1430_MN/fastq_pass");
    expect(ref).toEqual({
      kind: "external",
      path: "/data/20260212_1430_MN/fastq_pass",
      name: "fastq_pass",
    });
  });

  it("carries size and mtime on an external reference when given", () => {
    const ref = toPathRef("/proj", "/data/run", {
      size: 1_900_000_000,
      mtime: "2026-02-12T14:30:00.000Z",
    });
    expect(ref).toMatchObject({
      kind: "external",
      size: 1_900_000_000,
      mtime: "2026-02-12T14:30:00.000Z",
    });
  });

  it("treats everything as external when there is no project (scratch)", () => {
    expect(toPathRef(null, "/anywhere/file.fasta")).toEqual({
      kind: "external",
      path: "/anywhere/file.fasta",
      name: "file.fasta",
    });
  });

  it("does not turn the project root itself into an empty relative path", () => {
    // An empty rel would restore as "is it the folder or nothing?" later.
    expect(toPathRef("/proj", "/proj")).toMatchObject({ kind: "external" });
  });

  it("matches Windows paths against a Windows project root", () => {
    const ref = toPathRef("D:\\work\\proj", "D:\\work\\proj\\design\\p.xlsx");
    expect(ref).toEqual({ kind: "project", rel: "design/p.xlsx" });
  });

  it("does not treat a sibling with a shared prefix as inside the project", () => {
    // "/proj-old" starts with "/proj" as a string but is a different folder.
    expect(toPathRef("/proj", "/proj-old/design/p.xlsx")).toMatchObject({
      kind: "external",
    });
  });
});

describe("fromPathRef", () => {
  it("resolves an in-project reference against the new project location", () => {
    const ref = toPathRef("/machine-a/proj", "/machine-a/proj/design/primers.xlsx");
    // The folder was copied to a different machine and a different path.
    expect(fromPathRef("/machine-b/lab/proj", ref)).toBe(
      "/machine-b/lab/proj/design/primers.xlsx",
    );
  });

  it("returns an external reference unchanged", () => {
    const ref = toPathRef("/machine-a/proj", "/data/run");
    expect(fromPathRef("/machine-b/proj", ref)).toBe("/data/run");
  });

  it("accepts a bare string from an older snapshot", () => {
    expect(fromPathRef("/proj", "/legacy/abs/path.fasta")).toBe(
      "/legacy/abs/path.fasta",
    );
  });

  it("returns an empty string for a missing value", () => {
    expect(fromPathRef("/proj", null)).toBe("");
    expect(fromPathRef("/proj", undefined)).toBe("");
    expect(fromPathRef("/proj", "")).toBe("");
  });

  it("cannot resolve an in-project reference with no project open", () => {
    const ref: PathRef = { kind: "project", rel: "design/p.xlsx" };
    expect(fromPathRef(null, ref)).toBe("");
  });
});

describe("asExternalRef", () => {
  it("picks out external references only", () => {
    expect(asExternalRef({ kind: "project", rel: "a.xlsx" })).toBeNull();
    expect(asExternalRef("/legacy/abs")).toBeNull();
    expect(asExternalRef(null)).toBeNull();
    expect(asExternalRef({ kind: "external", path: "/d/run", name: "run" })).toEqual({
      kind: "external",
      path: "/d/run",
      name: "run",
    });
  });
});

describe("baseName", () => {
  it("names files and folders, including trailing separators and Windows paths", () => {
    expect(baseName("/data/run/fastq_pass")).toBe("fastq_pass");
    expect(baseName("/data/run/")).toBe("run");
    expect(baseName("D:\\work\\GC data.xlsx")).toBe("GC data.xlsx");
  });
});
