# 판별력 픽스처

`make_fidelity_panel.py` 의 판정 집계가 실제로 결함을 잡아내는지 보인다.

```
python3 run_fixtures.py
```

6건을 검사하고 전부 맞으면 `FIXTURES_OK`, 하나라도 어긋나면 어느 검사가 무엇으로
나왔는지 찍고 exit 1 이다. 한계도 같이 찍힌다.

## 세 조건

- (a) `fixture_a_well_verdicts.csv` 는 여덟 클래스가 전부 든 입력이다. 여덟을 전부
  세고 합이 288 레코드와 같고 exit 0 이어야 한다
- (b) `fixture_b_well_verdicts.csv` 는 (a) 에 `BOGUS` 판정 하나를 심었다. exit 0 이
  아니고 실패 메시지가 `BOGUS` 를 명명해야 한다. 종료 코드만 보면 다른 이유의
  실패와 구분되지 않으므로 메시지까지 요구한다
- (c) 음성 대조. 수정 전 스크립트를 `git show 7cd1c1a7:` 로 꺼내 같은 두 입력에
  물린다. 다르게 행동해야 수정이 의미가 있다

두 입력을 한 파일에 담지 않았다. 어휘 밖 판정 거부는 fail-first 라 한 파일이면
(b) 가 먼저 죽어 (a) 를 볼 수 없다.

## 실측 (2026-09-14)

수정 전 스크립트는 (a) 에서 exit 0 이고 합이 284 다. 심어 둔 MIXED, FRAMESHIFT,
LOWDEPTH, NO_CALL 네 레코드가 조용히 총계에서 빠졌다. (b) 에서도 exit 0 이고
`BOGUS` 를 한 번도 언급하지 않는다. 이것이 이 작업이 다루는 결함이고 exit 0 으로
지나간다는 점이 요점이다. 수정 후는 (a) 에서 여덟 클래스를 전부 세고 합 288,
(b) 에서 exit 1 과 `BOGUS` 를 명명한 메시지다.

## 왜 실제 CSV 를 깎아 만들었나

`build()` 가 96행을 assert 하고(`../make_fidelity_panel.py:183`) 데이터에서 유도한
비-clean 집합이 `AUDIT_CLASS` 와 같은지 assert 한다(`:190`). 작은 합성 플레이트는
집계에 닿기 전에 둘 다에서 걸린다. 픽스처를 실제 `well_verdicts.csv` 에서
`PASS|PASS|PASS` 인 웰을 골라 두 번째나 세 번째 replicate 슬롯만 고쳐 썼다. 첫
슬롯은 그대로라 `clean_from_data` 가 여전히 True 를 내고 감사 집합이 흔들리지
않는다. 심은 네 클래스는 이 실행이 낸 적 없는 것들이고 옛 네 키 목록이 버렸을
바로 그 클래스들이다.

기대 수치는 손으로 적었다. 알려진 답이라 파일에서 유도하면 검사가 자기를 검사한다.
`make_fixtures.py` 가 계산하는 값은 sha256 뿐이고 그것은 답이 아니라 체크섬이다.

## 재생성

```
python3 make_fixtures.py
```

원본 CSV 에서 다시 깎고 spec json 을 다시 쓴다. 심을 슬롯이 `PASS` 가 아니면
세지 않고 abort 한다. 재생성했으면 CSV 와 spec 을 같이 커밋한다.
