# H: kuma PR #14 ���� ���� ����

����: ���� ������ �ٽ� ��ο��� �� ������ �������� ���ߴ�. ���� Python �׽�Ʈ�� ����Ʈ �׽�Ʈ �� ��ü Ÿ�� �˻簡 ������ �������� ���ܵǾ� ������ �����̳� ��ü PASS�� �ο����� �ʴ´�.

- PR: https://github.com/gyuminlee-repo/kuma/pull/14
- ���� head: `0b5fb940ad9effc4eb9b9cb1f4bf96819c574efa`
- ���� base: `c857b3560f45d2c5fd132b51bfd0920c25043983`
- head branch: `feat/strict-spatial-confidence-topn-20261012`
- base branch: `feat/variant-budget-residue-mapping-20261009`
- ������: 2026-10-12 UTC. ���� �� GitHub PR API �� git ls-remote�� Ȯ���ߴ�. ���� �� ���� �� SHA�� �������� �ٽ� Ȯ���ߴ�.
- ���� head�� �ֽ� head�� ����. ���� PASS�� �������� �ʾҴ�. main���� base�� �������� �ʾҴ�.
- ���� ��� �� �ݸ� checkout: `source`. ���� HTTPS clone�� ����ߴ�. ���� checkout�̳� ���� �� locale �� ��ȭ ������ ������� �ʾҴ�. ���� �� `git status --porcelain` ����� ��� �ִ�.

## ���� �� ����

PR ������ base...head ���� ���� 25���� ���� Ȯ���ߴ�. ��Ʈ �� kuma_core, python-core, src, tests�� AGENTS.md�� ����� verify-kuma SKILL.md�� �о���. �˻� ������ ���ŷ� ��ǥ�� ���� �������� �Ÿ� ��꿡�� �����Ǵ���, �ĺ� ����� �����Ǵ���, ���� ���� �� �ڵ� ��ҳ� ���� �Ÿ� ��ü�� ������, raw Top-N�� site ��ǥ Top-N�� �����ϴ���, �Է� �ܱ� ��ȣ�� ���� ��ǥ�� ��Ȯ�� �����ϴ�����.

����: PR�� ���� AlphaFold TITLE �ĺ� ��Ģ�� pLDDT < 50 ��å�� ���Ѵ�. �������� ȿ���� ���� ���� ���� ������ �����ϴ� �۾��� �ƴϴ�. ���� ���� ���� ������ ��ġ ������ ���� �ռ� ������. ���� assay �������� �ؼ��ϸ� �� �ȴ�.

����� GUI ��ų�� ������ ��ġ ��ħ�� ������� ��ġ ������ �켱�Ѵ�. GUI ������ ����� �������� �ʾҴ�. �ڵ� ���� ���� H ������ ���� ���� ��ũ��Ʈ�� �ۼ��ߴ�.

## ���

| �˻� | ���� | �ٰ� |
|---|---|---|
| ���� SHA ���� �� locale ���� ���� | PASS | publication-state.json, logs/remote-refs-final.log, logs/locale-tree.log |
| ���� Python ���ñ� �� CSV �δ� ���� �ռ� 26�� | PASS | synthetic_checks.py, synthetic-results.json, logs/synthetic.log |
| ���� AlphaFold v6 ��ǥ 2�� | PASS | public_checks.py, public-results.json, logs/public.log |
| ���� Python CSV ��� �� ���� TS validator 5�� | PASS | validator-check.mjs, logs/validator.log |
| i18n-lint | PASS | exit 0, strictSpatial ��Ȯ��/�̻�� Ű 0 |
| i18n-parity | PASS | exit 0, ���� untranslated baseline ������ �Բ� ��µ� |
| sync-check-groups | PASS with warnings | exit 0, 80 passed / 6 warned / 0 failed. ����� ������ ���� commit�� �Ϻ� ���ú��� ���� ���� �˻� |
| sync-check | FAIL / ȯ�� ���� ���� | Python ���� �� 92 passed / 2 failed. NOTICE.md ����� json2ts ���� |
| ���� Python pytest 3���� | BLOCKED | exit 1, No module named pytest |
| RPC handler import �� ���� JSON-RPC ��ü ȣ�� | BLOCKED | exit 1, No module named Bio |
| strict ����Ʈ 6���� Vitest | BLOCKED | exit 1, node_modules/vitest/vitest.mjs ���� |
| ��ü TypeScript tsc | BLOCKED | exit 1, node_modules/typescript/bin/tsc ���� |
| generated model ����� ��ġ �˻� | BLOCKED | Python ��θ� �����ص� json2ts ���� ���� ���� |

## �ٽ� ���� ���

1. pLDDT 49.99 ��ǥ�� ���ܵǰ� 50�� ���Եȴ�. ���� ���� ������ ���ŷ� ������ �־ FPS �������� ������ �ʴ´�. ���� ���ŷ��� �Է��� `Strict spatial count 1 exceeds 0 eligible unique sites`�� �źεȴ�. ��ȿ ��ǥ 2���� count 3�� �źεȴ�.
2. NaN ��ǥ�� `missing_or_nonfinite_coordinate`�� �и��ȴ�. ��ǥ ���� ������ count ������ ����. ���� CA ���ڵ尡 ���� ��ȣ�� �ҿ����̸� PDB ��ü�� �ź��Ѵ�. CA�� ������ ��ǥ�� ������ ���� ���� ��ȣ ������ ��å�� �ٸ��� �ڵ�� �̸� ���������� ó���Ѵ�.
3. AlphaFold TITLE�� �ִ� ��� �� pLDDT, -1, 101, NaN, inf�� �ź��Ѵ�. ���� ���� TITLE�� B-factor�� pLDDT�� ���͸����� ������ confidence unavailable�� �����Ѵ�. �ĺ��� ���� TITLE�� ALPHAFOLD�� PREDICTION�� �����Ѵ�. ��ǥ�� ���� ������ �ŷڵ��� �����ϴ� ����� ����.
4. `MACDE` ������ ����� ���� `ACDE`�� �ָ� �Է� 1..4�� ���� 2..5�� �����Ѵ�. �߸��� WT �ܱ�, ���� �ʰ�, ���� ����, �ݺ��� reference placement�� �ź��Ѵ�.
5. raw Top-N�� ��ȿ��/��ǥ/�ŷڵ� ���� ���� ��ü eligible variant pool�� ���� ����Ѵ�. ���ŷ� variant���� ������ ���� ���� ��ü Top-N�� ������ �ʴ´�. site ��ǥ���� cap ���� ���̶�� PR �ǵ��� ������ ��ġ�Ѵ�. �ռ� ������ raw Top-N�� A2C/A2D�̰� ��ǥ Top-N�� A2C/A3C��. ���� ������ A2C/A5C�̸� asc/desc ��� ��� ���� �ս� 1.5�� ��� coverage distance 0.5�� ���� ���� ��ġ�Ѵ�.
6. distinct-variant ��忡�� 5�� site�� 95�� ���̸� count 95�� ��� �����Ѵ�. count 96�� �ź��Ѵ�. cap 1�̸� capacity 5�̸� count 6�� �ź��Ѵ�. 95�� site�� �߸� �������� �ʴ´�.
7. ���� CSV �δ����� ���ŷ� A2G/C3G�� pool_variants�� ���� ���� ����� D4G/E5G��. start position ���� 1�ǰ� �ߺ� ���� 1���� ���� �����ȴ�. ���� �ĺ� CSV�� ��ȯ JSON�� fixtures�� �����ߴ�.
8. annotation_status�� Pydantic Literal�� TS validator�� `error`, `no_matching_features`, `present`�� ��ġ�Ѵ�.
9. Node 24�� ���� TypeScript ����� Ȯ���� resolve hook�� ����Ͽ� ���� validator�� �״�� �����ߴ�. ���� CSV ����� ���ư� threshold 49, �߸��� ���� ��, ���� universe, ������ secondary baseline�� �źεƴ�. �� 5���� tsc�� React/Vitest�� ��ü ��� ������ �ƴϴ�.

## ���� �ڷ� Ȯ��

- AF-Q9AR86-F1-model_v6.pdb: 595 �ܱ�, pLDDT < 50 �ܱ� 52��. ��ġ 1�� �ռ� �ĺ����� ���������Ƿ� ���� �ĺ� ���� ���� 51����. ������ 24�� ��� pLDDT >= 50�̴�.
  SHA256: `59e17a5ebc8bd204ea150a7887edc5b76f17e5c289fdafd935f9c1fe270f08c5`
- AF-P42212-F1-model_v6.pdb: 238 �ܱ�, pLDDT < 50 �ܱ� 0��. ������ 24�� ��� pLDDT >= 50�̴�.
  SHA256: `abfe2191b8474977143b60b866077b97526fa71c9d3c657304b348e21397323f`
- �ٿ�ε� URL�� ����� public-results.json�� �ִ�. AlphaFold DB ���� ��ǥ�� ������ �纻�� �����ߴ�. �� ��ó AlphaFold DB �� �ش� �ܹ��� accession�� ǥ���ϸ� CC BY 4.0 ��ó ��å�� �� PR�� README���� Ȯ�εȴ�.

## �̰��� �� ���� ����

- BLOCKED_DEPENDENCY: pytest, Biopython, Vitest, TypeScript, json2ts ����. ��ġ���� �ʾҴ�. pytest ���� ȸ�� ��ü�� full RPC, React store/component ��Ÿ��, ��ü Ÿ�� �� generated-model drift�� �̰����̴�.
- FAIL_GENERATED_RESOURCE: `src-tauri/resources/NOTICE.md` ���簡 sync-check���� �����ȴ�. PR �������� �˷��� ����� ���õȴ�. PR #14 diff�� ���� ������ �ƴϹǷ� �̹� ���濡�� ���Ե� �������� ������� �ʴ´�. ��ü gate�� ����� �ƴϴ�.
- SKIP_LOCAL_RECORDING: verify-kuma MOCK_MODE�� ����ϴ� scripts/real-data.json �� scripts/mame-real-data.json�� ���ݿ� ���Ե��� �ʴ� ���� ��ȭ �ڷ��. ���� checkout���� �������� �ʾҴ�. React/native UI �� drag-and-drop�� Ȯ������ �ʾҴ�.
- SKIP_SCOPE: 18ȸ assay ��ġ, construct ����, Windows Tauri ����/�Ϸ� ������ �������� �ʾҴ�.
- NETWORK: �⺻ Git schannel�� SEC_E_NO_CREDENTIALS�� �����ߴ�. ���� �б� ���ɿ��� `-c http.sslBackend=openssl`�� ����� �����ߴ�. ���� �� ���� � ������ �������� �ʾҴ�. ���� AlphaFold �ٿ�ε�� ���������Ƿ� ��Ʈ��ũ SKIP���� ó������ �ʴ´�.
- PRIVATE: ��� ����ҿ� ����� AlphaFold ������ ���� �ڷ��. ����� ������ ������ ���Ƿ� �������� �ʾҴ�.

## �Խ� ���� ���� �� �ؼ� ����

������ �Խÿ� �� �귣ġ�� �������� main `9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4`�̴�. ���� ����� ������ PR #14 head `0b5fb940ad9effc4eb9b9cb1f4bf96819c574efa` �� base `c857b3560f45d2c5fd132b51bfd0920c25043983`�̴�. PR #14�� base�� main���� �ٲ��� �ʴ´�. �Խ� ���� PR #14�� open draft�̸� head/base�� ���� ������ ����. ��ü 14�� PR ��Ͽ��� H ���� ���� �ߺ� �Խø� ã�� ���ߴ�.

�Խ� ���� main AGENTS.md�� NOTICE.md�� `scripts/build-notice.mjs`�� ���� ������ ���� �� �����Ǵ� gitignore ����̶�� �����Ѵ�. �� ��ü checkout���� ������ �������̸� �κ� ������ ���� ������ PR #14 �ű� ���� ������ �ƴϴ�. ���� strict sync-check�� 92 PASS / 2 FAIL ����� �����Ѵ�. �ٸ� ������ json2ts ����� generated-model �˻縦 �����Ѵ�. ���� �Ǵ� pre-push wrapper�� �������� �ʾҴ�.

���� ���� ����� �Խ��ϴ� ���� PR�̴�. �Խ� �ܰ迡���� ��ǰ �׽�Ʈ�� ��������� �ʴ´�. ���� �����ϴ� ������ �Խ� ���� ���������� ���/��� ���ϡ�JSON��Python ���� �˻�� ���� PR/head/CI ��ȸ���̴�. �� ����� ���� ��ǰ �˻��� �߰� PASS�� �������� �ʴ´�.

## ���� ���� �ڷ�

synthetic_checks.py, validator-check.mjs �� ���� �ռ� CSV/JSON�� �����Ѵ�. ���� source ZIP, ���� PDB ����, ���� ���, Library �ĺ���, � �����ʹ� �������� �ʴ´�. �α��� ���� ��θ� `<local>`�� ġȯ�ߴ�. �α׿� ���� ���� �˻� ���ɰ� �����ڵ�� �Խ� �� ������� �ǹ����� �ʴ´�. ���� PR metadata�� ���� locale ���� ����� publication-state.json�� ���� �α׿� ����ߴ�.

�ʱ� harness�� �⺻ ���ڵ��� validator export �̸� ������ ���� �� �����Ǿ� ����� ���̴�. �ش� �ʱ� ���� �α׵� �����Ѵ�. ��ǰ �ڵ�� �������� �ʾҴ�. ��� ��ġ�� 2026-10-12�� ���� ���� SHA�� �����ȴ�.
