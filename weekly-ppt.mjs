import PptxGenJS from "pptxgenjs";
const pres = new PptxGenJS();
pres.layout = "LAYOUT_WIDE";

import fs from "fs";
const W = 13.33, H = 7.5, HEADER_H = 0.71;

function pngSize(p) {
  const b = fs.readFileSync(p);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
function fitImg(slide, imagePath, x, y, maxW, maxH) {
  const { w: pw, h: ph } = pngSize(imagePath);
  const r = pw / ph;
  let iw, ih;
  if (maxW / maxH > r) { ih = maxH; iw = ih * r; }
  else { iw = maxW; ih = iw / r; }
  slide.addImage({
    path: imagePath,
    x: x + (maxW - iw) / 2, y: y + (maxH - ih) / 2,
    w: iw, h: ih,
  });
}
const FONT = "Pretendard";
const C = {
  main: "44546A", white: "FFFFFF", offWhite: "F5F6F8",
  lightGray: "E0E3E8", midGray: "8B95A5", darkText: "2D3748",
  tealAccent: "2B9E9E",
};

function header(slide, title) {
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: W, h: HEADER_H, fill: { color: C.main } });
  slide.addText(title, { x: 0.3, y: 0, w: 10, h: HEADER_H, fontSize: 22, fontFace: FONT, color: C.white, bold: true, valign: "middle", margin: 0, shrinkText: true });
}

function slideNum(slide, n) {
  slide.addText(String(n), { x: W - 1, y: H - 0.5, w: 0.7, h: 0.35, fontSize: 11, color: C.midGray, align: "right", fontFace: FONT });
}

function contribBox(slide, text) {
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 6.1, w: W - 0.8, h: 0.6, fill: { color: "E8F5F5" } });
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 6.1, w: 0.05, h: 0.6, fill: { color: C.tealAccent } });
  slide.addText([
    { text: "기여  ", options: { bold: true, fontSize: 11, color: C.tealAccent } },
    { text, options: { fontSize: 11, color: C.darkText } },
  ], { x: 0.6, y: 6.1, w: W - 1.2, h: 0.6, fontFace: FONT, valign: "middle" });
}

function bullets(slide, items, x, y, w, h) {
  const texts = items.map((t, i) => ({
    text: t,
    options: { fontSize: 12, fontFace: FONT, color: C.darkText, bullet: true, paraSpaceAfter: 4, breakLine: i < items.length - 1 },
  }));
  slide.addText(texts, { x, y, w, h, valign: "top" });
}

function sectionTitle(slide, text, x, y) {
  slide.addText(text, { x, y, w: 6, h: 0.35, fontSize: 14, fontFace: FONT, bold: true, color: C.main });
}

// === 1. 표지 ===
{
  const s = pres.addSlide();
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: W, h: 5.7, fill: { color: C.main } });
  s.addText("C1 Team Meeting", { x: 0.1, y: 0.1, w: 2.5, h: 0.4, fontSize: 14, fontFace: FONT, color: C.white, margin: 0 });
  s.addText("Weekly report", { x: 0, y: 1.5, w: W, h: 1.2, fontSize: 60, fontFace: FONT, color: C.white, bold: true, align: "center", valign: "middle", margin: 0 });
  s.addText("(260330–260403)", { x: 0, y: 2.8, w: W, h: 0.6, fontSize: 24, fontFace: FONT, color: C.white, bold: true, align: "center", margin: 0 });
  s.addText([
    { text: "2026.04.03", options: { fontSize: 20, bold: true, color: C.main, breakLine: true } },
    { text: "Gyu Min Lee", options: { fontSize: 24, bold: true, color: C.main } },
  ], { x: 0, y: 5.85, w: W, h: 1.3, fontFace: FONT, align: "center", lineSpacingMultiple: 1.5, margin: 0 });
}

// === 2. IspS 프로젝트 ===
{
  const s = pres.addSlide();
  header(s, "1. IspS — 논문화 방향 전환");

  // 계기
  sectionTitle(s, "계기", 0.5, 0.95);
  bullets(s, [
    "이혜원 박사님 주간 코멘트(3/30): 현재 데이터로는 논문 부적합, 90개 재실험 + 저비용 워크플로우 필수",
    "강혜민 연구원과 82분 미팅(4/1) — 이혜원 박사님 옵션을 하나씩 검토하며 최종 방향 정리",
  ], 0.5, 1.35, 12.0, 1.0);

  // 결정
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 2.55, w: W - 1.0, h: 0.02, fill: { color: C.lightGray } });
  sectionTitle(s, "결정", 0.5, 2.7);
  // 학명 이탤릭 처리를 위해 수동 텍스트 배열
  const items = [
    [{ text: "MEP/메탄자화균 중심으로 논문 축 전환 — MVA 단순 후속 대신 새 방향으로 서술 가능" }],
    [
      { text: "근거: 게오르기 미발표 데이터 " },
      { text: "M. capsulatus", options: { italic: true } },
      { text: " Bath에서 3,032.7 mg/L 이소프렌 확인 (Z드라이브 29,000파일 분석)" },
    ],
    [{ text: "IspS 개량은 MVA/MEP 무관 — 기존 자산을 MEP backbone에 결합하는 구조" }],
    [{ text: "Gibson Assembly 대신 CPEC 확정 — 고가 시약 제거가 저비용 어필 핵심" }],
    [
      { text: "스크리닝은 " },
      { text: "E. coli", options: { italic: true } },
      { text: " 유지, 최종 생산 확인만 메탄자화균에서 수행" },
    ],
  ];
  const texts = items.flatMap((parts, i) => {
    const last = i === items.length - 1;
    return parts.map((p, j) => ({
      text: p.text,
      options: {
        fontSize: 12, fontFace: FONT, color: C.darkText,
        ...(j === 0 ? { bullet: true } : {}),
        ...(p.options || {}),
        ...(j === parts.length - 1 && !last ? { breakLine: true, paraSpaceAfter: 4 } : {}),
      },
    }));
  });
  s.addText(texts, { x: 0.5, y: 3.1, w: 12.0, h: 2.5, valign: "top" });

  // 의미
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 5.7, w: W - 1.0, h: 0.02, fill: { color: C.lightGray } });
  s.addText("4/3 이혜원 박사님에게 메일 보고 완료 — 게오르기 데이터 검증 + KURO 구조 기반 방향 포함", {
    x: 0.5, y: 5.8, w: W - 1.0, h: 0.35, fontSize: 11, fontFace: FONT, color: C.midGray,
  });

  slideNum(s, 1);
}

// === 3. KURO — Step 3 후보 선정 전략 ===
{
  const s = pres.addSlide();
  header(s, "2. KURO — 96개 후보를 어떻게 고르는가");

  // 계기
  sectionTitle(s, "계기", 0.5, 0.95);
  bullets(s, [
    "이혜원 박사님 지시: \"96웰 전부 채워서 실험하라, 60-70개만 한 건 말이 안 됨\"",
    "혜민 연구원 기존 방식: EVOLVEpro 예측 상위 순서대로 뽑음 → 같은 위치 변이 중복, 다양성 부족",
    "KURO가 이 과정을 자동화해야 하는데, \"상위 몇 배를 후보 pool로 잡을 것인가\"에 근거가 없었음",
  ], 0.5, 1.35, 12.0, 1.5);

  // 문제
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 3.0, w: W - 1.0, h: 0.02, fill: { color: C.lightGray } });
  sectionTitle(s, "문제: 고정 pool은 데이터마다 다르게 작동", 0.5, 3.15);
  bullets(s, [
    "11개 IspS 실데이터 분석 — 고정 2x pool에서는 top48과 top96 차이가 noise 수준 (0.13~0.49\u03C3)",
    "라운드 초기(데이터 적음)에는 넓게 탐색해야 하고, 후기(데이터 충분)에는 좁혀야 함",
  ], 0.5, 3.55, 12.0, 1.0);

  // 해결
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 4.7, w: W - 1.0, h: 0.02, fill: { color: C.lightGray } });
  sectionTitle(s, "해결: \u03C3-Adaptive Pool + 3-objective Pareto (v1.27)", 0.5, 4.85);
  bullets(s, [
    "예측 신뢰도(\u03C1)가 낮으면 pool 자동 확대, 높으면 자동 축소 — 문헌 기반 수식",
    "확보된 pool 안에서 Fitness · Entropy · AlphaFold2 구조 거리 3가지를 동시에 보고 Pareto 최적해 선택",
    "프라이머 설계 실패 위치는 Position Rescue(v1.28)로 대체 후보 자동 충원 → 90개 이상 보장",
  ], 0.5, 5.25, 12.0, 1.2);

  slideNum(s, 2);
}

// === 3b. KURO — UX 단순화 ===
{
  const s = pres.addSlide();
  header(s, "2b. KURO — 비전문가도 쓸 수 있게");

  // 계기
  sectionTitle(s, "계기", 0.5, 0.95);
  bullets(s, [
    "이혜원 박사님 논문 방향: \"비전문가 온보딩 가능한 워크플로우\" — KURO 자체가 쉬워야 논문 설득력이 생김",
    "기존 DiversityOptions 패널에 ~20개 컨트롤 노출 → 혜민 연구원도 어떤 값을 넣어야 할지 모르는 상황",
  ], 0.5, 1.35, 12.0, 1.0);

  // Before → After
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 2.55, w: W - 1.0, h: 0.02, fill: { color: C.lightGray } });

  // 좌: Before
  sectionTitle(s, "Before", 0.5, 2.7);
  bullets(s, [
    "Pool multiplier, entropy weight, site limit, Grantham threshold 등 직접 입력",
    "각 값의 의미와 적정 범위를 사용자가 알아야 함",
    "잘못된 설정 → 나쁜 후보 → \"프로그램이 안 좋다\"고 오해",
  ], 0.5, 3.1, 5.8, 1.5);

  // 우: After — 텍스트 + 스크린샷
  sectionTitle(s, "After — 실제 UI", 6.8, 2.7);
  bullets(s, [
    "사용자 입력: EVOLVEpro round + size 단 2개",
    "K, entropy 자동 계산 (Auto 표시)",
    "사용자는 \"몇 번째 라운드인지\"만 알면 됨",
  ], 6.8, 3.1, 3.5, 1.2);

  // KURO UI 스크린샷 삽입
  fitImg(s, "/tmp/kuro-after.png", 10.2, 2.8, 2.8, 2.5);

  // 의미
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 5.05, w: W - 1.0, h: 0.02, fill: { color: C.lightGray } });
  sectionTitle(s, "의미", 0.5, 5.15);
  bullets(s, [
    "논문에서 \"전문 지식 없이 96-well 실험 설계 가능\" 주장의 실질적 근거",
    "기타: Echo/JANUS 매핑 CSV export (v1.24), multi-evolve 샘플 (v1.23) 등 7 릴리즈",
  ], 0.5, 5.55, 12.0, 0.8);

  slideNum(s, 3);
}

// === 5. PrimerBench ===
{
  const s = pres.addSlide();
  header(s, "4. PrimerBench — Gibson Assembly 완성");

  // 계기
  sectionTitle(s, "계기", 0.5, 0.95);
  bullets(s, [
    "이혜원 박사님 지시: Gibson 없는 저비용 클로닝 → PrimerBench에 Gibson/CPEC 프라이머 자동 설계 기능 필요",
    "혜민 연구원이 수동으로 하던 overlap 계산 + Tm 맞추기를 프로그램에서 처리해야 실험 속도 확보",
  ], 0.5, 1.35, 12.0, 1.0);

  // 해결
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 2.55, w: W - 1.0, h: 0.02, fill: { color: C.lightGray } });
  sectionTitle(s, "이번 주 구현 (v2.12 \u2192 v2.15, 4 릴리즈)", 0.5, 2.7);
  bullets(s, [
    "앱 구조 재설계 — Gibson을 기본 탭으로, Primer Analyzer는 독립 탭 분리 (v2.12)",
    "Gibson Assembly 엔진 완성 — 후보 자동 생성, KO 드래그, 프라이머 네이밍 (v2.13)",
    "UX 7건 수정 + region flexibility — 사용자가 overlap 영역 조절 가능 (v2.14)",
    "Synthesis score · CDS 자동 검색 · Tm tune 대화창 — 설계 품질 실시간 확인 (v2.15)",
  ], 0.5, 3.1, 12.0, 1.8);

  // 의미
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 5.1, w: W - 1.0, h: 0.02, fill: { color: C.lightGray } });
  sectionTitle(s, "의미", 0.5, 5.25);
  bullets(s, [
    "혜민 연구원이 GenBank 파일만 올리면 Gibson/CPEC 프라이머가 자동 설계됨 → 수동 계산 제거",
    "KURO와 연계하면 EVOLVEpro 예측 → 프라이머 설계 → 주문까지 한 흐름으로 처리 가능",
  ], 0.5, 5.65, 12.0, 0.7);

  slideNum(s, 4);
}

// === 6. 기타 ===
{
  const s = pres.addSlide();
  header(s, "5. 기타");

  // download-paper
  sectionTitle(s, "download-paper — 논문 수집 자동화", 0.5, 0.95);
  bullets(s, [
    "계기: IspS 논문화 준비 중 참고 문헌 수집에 시간 소모 → DOI만 넣으면 PDF 다운 + Zotero 등록까지 자동화",
    "Sci-Hub + Unpaywall 이중 탐색으로 접근 가능한 소스 자동 판별",
  ], 0.5, 1.35, 12.0, 1.0);

  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 2.55, w: W - 1.0, h: 0.02, fill: { color: C.lightGray } });

  // 송현 DASbox
  sectionTitle(s, "송현 — DASbox 메탄 가스 운용 조사", 0.5, 2.7);
  bullets(s, [
    "계기: 이혜원 박사님이 송현 학생 DASbox 메탄 배양 준비 지시",
    "조사: DASbox 내부 TMFC로 메탄 직접 공급 시 가연성 가스 폭발 위험 확인 (히터 가열 방식)",
    "대안: MFC + bottle direct 연결 (IV-MCB 활용) — 현실적 방안으로 정리",
    "후속: 이혜원 박사님 지시에 따라 동욱 학생과 일정 조율, MFC 사용법 전수 예정",
  ], 0.5, 3.1, 12.0, 1.5);

  slideNum(s, 5);
}

// === 7. 다음 주 계획 ===
{
  const s = pres.addSlide();
  header(s, "6. Next Week");

  s.addTable(
    [
      [
        { text: "우선순위", options: { bold: true, color: C.white, fill: { color: C.main } } },
        { text: "항목", options: { bold: true, color: C.white, fill: { color: C.main } } },
        { text: "분류", options: { bold: true, color: C.white, fill: { color: C.main } } },
      ],
      ...([
        ["P1", "KURO AlphaFold2 구조 기반 필터링 구현", "개발"],
        ["P1", "강혜민 PCR 테스트 3옵션 × 10개 지원 (프라이머 설계)", "연구지원"],
        ["P1", "Another Round vs Double 전환 기준 수치화", "연구지원"],
        ["P2", "KURO Fitness-Entropy-Structure 균형 알고리즘", "개발"],
        ["P2", "송현 + 동욱 MFC 사용법 전수 미팅 조율", "지원"],
        ["P3", "게오르기 추가 미발표 데이터 탐색 (Z드라이브)", "조사"],
      ].map((r, i) => [
        { text: r[0], options: { bold: true, color: C.main, align: "center", fill: { color: i % 2 === 0 ? C.offWhite : C.white } } },
        { text: r[1], options: { color: C.darkText, fill: { color: i % 2 === 0 ? C.offWhite : C.white } } },
        { text: r[2], options: { color: C.midGray, align: "center", fill: { color: i % 2 === 0 ? C.offWhite : C.white } } },
      ])),
    ],
    {
      x: 0.5, y: 1.1, w: W - 1.0,
      fontSize: 12, fontFace: FONT,
      border: { type: "solid", pt: 0.5, color: C.lightGray },
      colW: [1.5, 8.33, 2.5],
      rowH: [0.45, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6],
      valign: "middle",
    }
  );

  slideNum(s, 6);
}

const outPath = "/tmp/260403_weekly_report.pptx";
await pres.writeFile({ fileName: outPath });
console.log("DONE:", outPath);
