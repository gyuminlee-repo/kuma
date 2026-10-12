# ���� SHA ���� �ȳ�

�� ������ ���� ������ ���� �����̸� �Խ� �ܰ迡���� �Ʒ� ��ǰ �˻縦 �ٽ� �������� �ʾҴ�.

���� scratch ���͸��� �� ������ ���� ���� ������ �����ϰ� �� ���͸� �Ʒ� source��� �� checkout�� �����. ���� main���� ���� ��� ������ ��� ���ԵǾ� �ִٰ� �������� �ʴ´�.

```sh
git clone --no-checkout --single-branch --branch feat/strict-spatial-confidence-topn-20261012 https://github.com/gyuminlee-repo/kuma.git source
git -C source checkout --detach 0b5fb940ad9effc4eb9b9cb1f4bf96819c574efa
python -X utf8 synthetic_checks.py
node validator-check.mjs
```

���� ���� ȯ���� Python 3.12.14�� Node.js 24.14.0�̴�. Python ��ũ��Ʈ�� remote source ����� ���� import�ϸ� dependency stub�� ������� �ʴ´�. Pydantic�� typing_extensions�� �ʿ��ϴ�. Node ��ũ��Ʈ�� ���� TypeScript ����� Ȯ���� resolve hook�� ����Ѵ�. ��ü tsc�� React/Vitest �˻縦 ��ü���� �ʴ´�.

���� �׽�Ʈ ����� tests/test_strict_confidence_topn.py, tests/test_strict_spatial.py, tests/test_strict_variant_budget.py��. pytest ����� ������� �ʾҴ�. strict ����Ʈ 6������ logs/strict-six.log�� command �迭�� �����Ѵ�. �ʱ� �������� �ʴ� ipc.strictSpatial.test.ts ��δ� ���� ��õ����� inputSlice.helpers.test.ts�� �����ߴ�. Vitest ��ü�� ���� ��� �õ��� �׽�Ʈ �������� �������� �ʾҴ�.

�α��� `<local>`�� �������� ���ſ� ġȯ���̴�. ���� exit code�� �����ߴ�. �ռ� 26��, TS validator 5�� �� ���� ��ǥ 2���� ���� PASS�� ���ܵ� ���� �˻縦 �����Ѵ�. ���� PDB ������ �Խ����� ������ public-results.json�� ��ó URL�� content SHA256�� �����Ѵ�. 18ȸ assay bench, construct, Windows Tauri �Ϸ� ������ �������� �ʾҴ�.
