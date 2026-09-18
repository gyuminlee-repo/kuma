"""Read-only incremental review planner. This is NOT a test-result cache.

An unchanged recorded scope is a reuse CANDIDATE, not a passing test or an
approval. Unrecorded changes require impact review; full CI remains mandatory.
Uses Git snapshots, explicit watch paths and transitive cross-layer groups.
It does not claim to construct a complete call graph or measure biological truth.
"""
from __future__ import annotations

import argparse
from fnmatch import fnmatchcase
from functools import lru_cache
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any

REGISTRY = "docs/audit/registry.json"
GROUPS = ".cross-layer-sync.json"
WARNING = (
    "Review plan only: reuse_candidate is not PASS. Review unrecorded changes "
    "and dependency-map completeness before narrowing manual review. Run current "
    "regression tests and full CI before merge; never reuse an old green check."
)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)


def paths(value: Any, label: str, *, exact: bool = False) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty path list")
    for item in value:
        if (not isinstance(item, str) or not item or item.startswith(("/", "-"))
                or "\\" in item or "\x00" in item or ".." in PurePosixPath(item).parts
                or ":" in item):
            raise ValueError(f"Invalid repository path in {label}: {item!r}")
        if exact and any(char in item for char in "*?[{}"):
            raise ValueError(f"{label} requires concrete paths, not globs: {item}")
    if len(set(value)) != len(value):
        raise ValueError(f"Duplicate path in {label}")
    return value


def text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def commit_id(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError("Reviewed revisions must be immutable full Git commit SHAs")
    return value


def validate_registry(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported audit registry schema")
    commit_id(value.get("comparison_base"))
    paths(value.get("global_inputs"), "global_inputs")
    records = value.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("Registry must have explicitly reviewed records")
    identifiers: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Invalid audit record")
        key = text(record.get("id"), "id")
        if key in identifiers:
            raise ValueError(f"Duplicate audit id: {key}")
        identifiers.add(key)
        commit_id(record.get("reviewed_commit"))
        text(record.get("scope"), "scope")
        text(record.get("limitations"), "limitations")
        paths(record.get("files"), "files", exact=True)
        paths(record.get("tests"), "tests", exact=True)
        paths(record.get("watch"), "watch")
        evidence = record.get("evidence")
        if not isinstance(evidence, dict) or evidence.get("kind") != "regression":
            raise ValueError("Records require explicitly bounded regression evidence")
        commit_id(evidence.get("tested_commit"))
        text(evidence.get("pull_request"), "pull_request")
        text(evidence.get("ci_run"), "ci_run")
    pending = value.get("unverified")
    if not isinstance(pending, list):
        raise ValueError("Registry must explicitly enumerate remaining unverified work")
    for item in pending:
        if not isinstance(item, dict):
            raise ValueError("Invalid unverified item")
        key = text(item.get("id"), "unverified id")
        if key in identifiers:
            raise ValueError(f"Duplicate audit id: {key}")
        identifiers.add(key)
        text(item.get("reason"), "unverified reason")
    return value


@lru_cache(maxsize=8192)
def expand_pattern(pattern: str) -> list[str]:
    """Brace alternatives and zero-directory **/ in addition to fnmatch syntax.

    fnmatch's * may cross a slash, deliberately over-approximating impact rather
    than silently under-matching dependencies. All comparisons are case-sensitive.
    """
    match = re.search(r"\{([^{}]+)\}", pattern)
    if match:
        result: list[str] = []
        for option in match.group(1).split(","):
            result.extend(expand_pattern(pattern[:match.start()] + option + pattern[match.end():]))
        return result
    if "{" in pattern or "}" in pattern:
        raise ValueError(f"Unsupported dependency glob: {pattern}")
    results = [pattern]
    if "**/" in pattern:
        results.extend(expand_pattern(pattern.replace("**/", "", 1)))
    return results


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatchcase(path, variant) for pattern in patterns for variant in expand_pattern(pattern))


def validate_groups(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or not isinstance(value.get("groups"), list):
        raise ValueError("Cross-layer dependency groups are missing or invalid")
    result = value["groups"]
    identifiers: set[str] = set()
    for group in result:
        if not isinstance(group, dict):
            raise ValueError("Invalid dependency group")
        key = text(group.get("id"), "group id")
        if key in identifiers:
            raise ValueError(f"Duplicate group id: {key}")
        identifiers.add(key)
        for pattern in paths(group.get("files"), "group files"):
            expand_pattern(pattern)
    return result


def impact_closure(changed: set[str], universe: set[str], groups: list[dict[str, Any]]) -> tuple[set[str], list[str]]:
    impacted = set(changed)
    triggered: set[str] = set()
    while True:
        previous = len(impacted)
        for group in groups:
            if any(matches(item, group["files"]) for item in impacted):
                triggered.add(group["id"])
                impacted.update(item for item in universe if matches(item, group["files"]))
        if len(impacted) == previous:
            return impacted, sorted(triggered)


class Repository:
    def __init__(self, root: Path, *, committed_only: bool = False):
        self.root = root.resolve()
        self.committed_only = committed_only
        self.head = self.git("rev-parse", "--verify", "HEAD^{commit}").decode().strip()
        self._trees: dict[str, dict[str, str]] = {}
        self._changes: dict[str, set[str]] = {}
        self.local_changes: set[str] = set()
        if not committed_only:
            # Inspect the index and worktree separately. A staged edit followed
            # by restoring the worktree to HEAD cancels out in git diff HEAD,
            # but the staged content could still be committed.
            self.local_changes = self.names("diff", "--cached", "--name-only", "--no-renames", "-z", "HEAD", "--")
            self.local_changes |= self.names("diff", "--name-only", "--no-renames", "-z", "--")
            self.local_changes |= self.names("ls-files", "--others", "--exclude-standard", "-z")

    def git(self, *args: str) -> bytes:
        result = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, timeout=45, check=False)
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace").strip()[:500]
            raise ValueError(f"Git evidence unavailable ({args[0]}): {detail or result.returncode}")
        return result.stdout

    def names(self, *args: str) -> set[str]:
        return {item.decode("utf-8") for item in self.git(*args).split(b"\x00") if item}

    def read(self, path: str) -> bytes:
        paths([path], "input", exact=True)
        if self.committed_only:
            return self.git("show", f"{self.head}:{path}")
        return (self.root / path).read_bytes()

    def tree(self, revision: str) -> dict[str, str]:
        commit_id(revision)
        if revision not in self._trees:
            entries: dict[str, str] = {}
            for line in self.git("ls-tree", "-r", "-z", revision).split(b"\x00"):
                if line:
                    meta, name = line.split(b"\t", 1)
                    # Keep file mode as well as object identity (including symlinks).
                    entries[name.decode("utf-8")] = meta.decode("ascii")
            self._trees[revision] = entries
        return self._trees[revision]

    def changes(self, baseline: str) -> set[str]:
        commit_id(baseline)
        if baseline not in self._changes:
            self.git("merge-base", "--is-ancestor", baseline, self.head)
            self._changes[baseline] = self.names("diff", "--name-only", "--no-renames", "-z", baseline, self.head, "--") | self.local_changes
        return self._changes[baseline]


def plan(repo: Repository, registry: dict[str, Any], groups: list[dict[str, Any]], *, base: str | None = None) -> dict[str, Any]:
    registry = validate_registry(registry)
    groups = validate_groups({"groups": groups})
    comparison_base = commit_id(base or registry["comparison_base"])
    changed = repo.changes(comparison_base)
    current_tree = repo.tree(repo.head)
    records = []
    errors = []
    impact_cache: dict[str, tuple[set[str], list[str]]] = {}
    for item in registry["records"]:
        row = {key: item[key] for key in ("id", "scope", "reviewed_commit", "evidence", "tests", "limitations")}
        row.update(status="review_required", trigger_paths=[], dependency_groups=[], fingerprints={})
        try:
            original = repo.tree(item["reviewed_commit"])
            changes = repo.changes(item["reviewed_commit"])
            universe = set(current_tree) | set(original) | changes
            if item["reviewed_commit"] not in impact_cache:
                impact_cache[item["reviewed_commit"]] = impact_closure(changes, universe, groups)
            impacted, group_ids = impact_cache[item["reviewed_commit"]]
            watched = item["files"] + item["tests"] + item["watch"]
            relevant = sorted(path for path in impacted if matches(path, watched))
            global_changes = sorted(path for path in changes if matches(path, registry["global_inputs"]))
            missing_original = [path for path in item["files"] + item["tests"] if path not in original]
            missing_tests = [path for path in item["tests"] if path not in current_tree or (not repo.committed_only and not (repo.root / path).is_file())]
            row["fingerprints"] = {path: {"reviewed": original.get(path), "head": current_tree.get(path)} for path in item["files"] + item["tests"]}
            row["trigger_paths"] = sorted(set(relevant + global_changes))
            row["dependency_groups"] = group_ids if relevant else []
            if missing_original:
                raise ValueError(f"Recorded files absent at reviewed commit: {missing_original}")
            if missing_tests:
                row.update(status="unverified", reason="regression evidence removed", missing_tests=missing_tests)
            elif relevant or global_changes:
                row["reason"] = "reviewed code, tests, declared dependencies or validation environment changed"
            else:
                row.update(status="reuse_candidate", reason="recorded scope and declared context unchanged; impact review and current CI still required")
        except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
            row["reason"] = str(exc)
            errors.append(f"{item['id']}: {exc}")
        records.append(row)
    all_watches = list(registry["global_inputs"])
    for item in registry["records"]:
        all_watches.extend(item["files"] + item["tests"] + item["watch"])
    unrecorded = sorted(path for path in changed if not matches(path, all_watches))
    pending = [{**item, "status": "unverified"} for item in registry["unverified"]]
    return {
        "schema_version": 1, "head_commit": repo.head, "comparison_base": comparison_base,
        "working_tree_included": not repo.committed_only,
        "working_tree_changes": sorted(repo.local_changes),
        "notice": WARNING, "plan_complete": not errors, "errors": errors,
        "changed_files": sorted(changed), "unrecorded_changes": unrecorded,
        "manual_impact_review_required": bool(unrecorded),
        "counts": {status: sum(row["status"] == status for row in records) for status in ("reuse_candidate", "review_required", "unverified")},
        "records": records, "unverified_work": pending,
        "full_ci_required": True, "automatic_test_skipping": False,
    }


def markdown(report: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["# Incremental audit plan", "", WARNING, "",
             f"Head: `{report['head_commit']}`", f"Comparison base: `{report['comparison_base']}`", "",
             "| Scope | Review decision | Why |", "|---|---|---|"]
    for item in report["records"]:
        lines.append(f"| {cell(item['id'])} | {item['status']} | {cell(item['reason'])} |")
        if item["trigger_paths"]:
            lines.append(f"| | Affected paths | {cell(', '.join(item['trigger_paths']))} |")
    lines += ["", "## Changes without a recorded audit scope", ""]
    lines += [f"- `{cell(path)}`: review the change and its impact before reusing any candidate." for path in report["unrecorded_changes"]] or ["None in the selected comparison range. This does not mean the entire repository was audited."]
    lines += ["", "## Still unverified (never automatically promoted)", ""]
    lines += [f"- **{cell(item['id'])}**: {cell(item['reason'])}" for item in report["unverified_work"]]
    if report["errors"]:
        lines += ["", "## Evidence errors: broaden review; do not reuse affected records", ""]
        lines += [f"- {cell(error)}" for error in report["errors"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--registry", default=REGISTRY)
    parser.add_argument("--base", help="Full SHA for the change inventory only; never overrides per-scope reviewed commits")
    parser.add_argument("--committed-only", action="store_true", help="Read committed registry/groups and ignore worktree edits; intended for CI")
    parser.add_argument("--json", type=Path, dest="json_path")
    parser.add_argument("--markdown", type=Path, dest="markdown_path")
    args = parser.parse_args(argv)
    try:
        repo = Repository(args.repo_root, committed_only=args.committed_only)
        registry_bytes, groups_bytes = repo.read(args.registry), repo.read(GROUPS)
        report = plan(repo, read_json(registry_bytes), validate_groups(read_json(groups_bytes)), base=args.base)
        report["registry_sha256"] = hashlib.sha256(registry_bytes).hexdigest()
        report["dependency_groups_sha256"] = hashlib.sha256(groups_bytes).hexdigest()
        rendered = markdown(report)
        for destination, content in (
            (args.json_path, json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"),
            (args.markdown_path, rendered),
        ):
            if destination is not None:
                # Refuse to overwrite a tracked file (the planner is not an editor).
                resolved = destination.resolve()
                if resolved.is_relative_to(repo.root) and resolved.relative_to(repo.root).as_posix() in repo.tree(repo.head):
                    raise ValueError(f"Report destination is a tracked file: {destination}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")
        print(rendered)
        return 0 if report["plan_complete"] else 1
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"Audit evidence unavailable; require full review, not an automatic pass: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
