"""
04_cost_model.py  (3단계-B: 진입 비용 계산, 실측 IT 투자액 기준)

핵심 지표
  IT 예산 증가율 = A 연간 비용 ÷ 실측 IT 투자액
  → CBAM 대응 시스템은 필수 지출(유지 성격)이라 기존 예산에서 빼기보다 IT 예산을 늘려 감당한다고 보고,
    "이 시스템 때문에 IT 예산을 몇 % 늘려야 하나"로 읽는다. 별도 비율 가정이 없는 지표.

진입 경로 4개
  A. 온라인 버전(SaaS)          : 공개 가격으로 연간 비용 계산
  B. 신규 설치 (Fusion HCI 등)   : 가격 비공개 → 비용 계산 불가, 기준선만 제시
  C. 기존 OpenShift 위 추가      : 가격 비공개 → 기준선 + VPC당 허용 단가
  D. BYOC (고객 클라우드에 설치) : 가격 비공개 → 기준선만 제시

IT 투자액: KISA 정보보호 공시 '정보기술부문 투자액' (2025년 실적, 없으면 2024년) - 실측 기업만 계산
공개 가격 (IBM watsonx.data 가격 페이지, 2026-09 확인)
  - 1 RU = 1 USD, Presto 엔진 Starter 2.00 / Small 11.20 / Medium 19.60 RU/시간
  - 계정당 기본 지원 비용 3.00 RU/시간 (엔진 정지 시 과금 여부 미확인 → 두 경우 모두 계산)
  - 설치형: 32코어 워커 1대당 20 VPC
  - 저장소 비용 제외, 정가 기준

참고 비교 (기업이 새 프로젝트로 취급할 경우)
  - 새 프로젝트 비중 15% (Deloitte 2020 글로벌 기술 리더십 조사), 21% (Deloitte 2023, transform)
  - B·C·D 기준선 = 새 프로젝트 예산 전액 (가장 관대한 가정 → '이 이상이면 불가'의 상한선)

입력  data/interim/it_spend_matched.csv
출력  data/processed/cost_by_company.csv, data/processed/cost_summary.csv
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"

EOK = 100_000_000
MAN = 10_000
FX = 1366                       # 원/달러 (2026-09-21)
SUPPORT_RU_PER_HOUR = 3.0
HOURS_BUSINESS = 22 * 10 * 12   # 업무시간: 월 22일 × 하루 10시간
HOURS_ALWAYS = 24 * 365
NEW_PROJECT_SHARES = {"15%(Deloitte 2020)": 0.15, "21%(Deloitte 2023)": 0.21}
VPC_MIN = 20                    # 워커 1대분

A_SCENARIOS = [                 # (이름, 엔진 RU/시간, 연간 가동 시간)
    ("소형·업무시간", 2.00, HOURS_BUSINESS),
    ("소형·상시", 2.00, HOURS_ALWAYS),
    ("중형·업무시간", 11.20, HOURS_BUSINESS),
    ("중형·상시", 11.20, HOURS_ALWAYS),
    ("대형·상시", 19.60, HOURS_ALWAYS),
]
SUPPORT_MODES = {"지원비 상시": True, "지원비 가동시간만": False}
KEY_SCENARIOS = [("소형·업무시간", "지원비 가동시간만"), ("소형·업무시간", "지원비 상시"),
                 ("중형·상시", "지원비 상시"), ("대형·상시", "지원비 상시")]
GROUP_ORDER = ["대기업", "중견 전체", "중견-1차(2027)", "중견-2차(2028)", "중견-2차 후보", "중견-비대상"]


def a_cost_krw(engine_ru, hours, support_always):
    support_hours = HOURS_ALWAYS if support_always else hours
    return (engine_ru * hours + SUPPORT_RU_PER_HOUR * support_hours) * FX


def assign_group(r):
    if r["size_class"] == "대기업":
        return "대기업"
    if r["size_class"] != "중견":
        return None
    w = r["wave_group_reviewed"]
    if w == "1차(2027)":
        return "중견-1차(2027)"
    if w in ("2차(2028)", "2차(2028, 제품명 확인)"):
        return "중견-2차(2028)"
    if w == "2차 후보(확인 필요)":
        return "중견-2차 후보"
    return "중견-비대상"


def group_masks(frame):
    masks = {g: (frame["group"] == g) for g in GROUP_ORDER if g != "중견 전체"}
    masks["중견 전체"] = frame["size_class"] == "중견"
    return masks


def main():
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(INTERIM / "it_spend_matched.csv", dtype=str)
    df["is_holding"] = df["is_holding"].str.lower().eq("true")
    df["it_spend"] = pd.to_numeric(df["it_spend"], errors="coerce")
    df = df[~df["is_holding"]].copy()
    df["group"] = df.apply(assign_group, axis=1)

    all_mid = (df["size_class"] == "중견").sum()
    df = df[df["group"].notna() & (df["it_spend"] > 0)].copy()
    measured_mid = (df["size_class"] == "중견").sum()

    a_tab = pd.DataFrame([{"A_scenario": n, "support": s, "A_cost": a_cost_krw(e, h, al)}
                          for n, e, h in A_SCENARIOS for s, al in SUPPORT_MODES.items()])

    long = df.merge(a_tab, how="cross")
    long["it_increase"] = long["A_cost"] / long["it_spend"]            # 핵심 지표
    for label, share in NEW_PROJECT_SHARES.items():
        long[f"A_share_newproj_{label}"] = long["A_cost"] / (long["it_spend"] * share)
    long.to_csv(PROCESSED / "cost_by_company.csv", index=False, encoding="utf-8-sig")

    summ = []
    for g, mk in group_masks(long).items():
        for (an, sm), s in long[mk].groupby(["A_scenario", "support"]):
            row = {"group": g, "A_scenario": an, "support": sm, "n": len(s),
                   "it_median_eok": s["it_spend"].median() / EOK,
                   "it_increase_median_pct": s["it_increase"].median() * 100,
                   "it_increase_p75_pct": s["it_increase"].quantile(0.75) * 100}
            for label in NEW_PROJECT_SHARES:
                col = f"A_share_newproj_{label}"
                row[f"newproj_{label}_median_pct"] = s[col].median() * 100
                row[f"newproj_{label}_over_pct"] = (s[col] > 1).mean() * 100
            summ.append(row)
    summ = pd.DataFrame(summ)
    summ.to_csv(PROCESSED / "cost_summary.csv", index=False, encoding="utf-8-sig")

    # ---------------- 출력
    pd.set_option("display.width", 220)
    print(f"실측 IT 투자액 보유: 중견 {measured_mid}곳 / 전체 중견 {all_mid}곳 "
          f"(측정 불가 {all_mid - measured_mid}곳), 대기업 {(df['group'] == '대기업').sum()}곳")

    print("\n===== A. 온라인 버전 연간 비용 (만 원, 정가, 저장소 제외) =====")
    piv = a_tab.pivot(index="A_scenario", columns="support", values="A_cost") / MAN
    print(piv.reindex([s[0] for s in A_SCENARIOS]).round(0).to_string())

    print("\n===== 핵심: A 도입 시 IT 예산 증가율 (그룹별 중앙값, %) =====")
    base = summ[(summ["A_scenario"] == KEY_SCENARIOS[0][0]) & (summ["support"] == KEY_SCENARIOS[0][1])]
    out = pd.DataFrame({"회사 수": base.set_index("group")["n"],
                        "IT투자액 중앙값(억)": base.set_index("group")["it_median_eok"].round(1)})
    for an, sm in KEY_SCENARIOS:
        t = summ[(summ["A_scenario"] == an) & (summ["support"] == sm)].set_index("group")
        out[f"{an}/{sm.replace('지원비 ', '지원비')}"] = t["it_increase_median_pct"].round(1)
    print(out.reindex(GROUP_ORDER).to_string())

    print("\n===== 핵심 보조: 증가율 상위 25% 지점 (부담이 큰 쪽 기업, %) =====")
    out2 = pd.DataFrame(index=GROUP_ORDER)
    for an, sm in KEY_SCENARIOS:
        t = summ[(summ["A_scenario"] == an) & (summ["support"] == sm)].set_index("group")
        out2[f"{an}/{sm.replace('지원비 ', '지원비')}"] = t["it_increase_p75_pct"].round(1)
    print(out2.to_string())

    print("\n===== 참고: 새 프로젝트 예산으로 취급할 경우 (A 비용 ÷ 새 프로젝트 예산, 중앙값 %) =====")
    for an, sm in [KEY_SCENARIOS[1], KEY_SCENARIOS[2]]:
        t = summ[(summ["A_scenario"] == an) & (summ["support"] == sm)].set_index("group").reindex(GROUP_ORDER)
        ref = pd.DataFrame(index=GROUP_ORDER)
        for label in NEW_PROJECT_SHARES:
            ref[f"비중 {label}: 중앙값(%)"] = t[f"newproj_{label}_median_pct"].round(0)
            ref[f"비중 {label}: 전액 초과 기업(%)"] = t[f"newproj_{label}_over_pct"].round(1)
        print(f"\n[{an}, {sm}]")
        print(ref.to_string())

    print("\n===== B·C·D 기준선 (가격 비공개, 그룹별 중앙값) =====")
    rows = []
    b = long[(long["A_scenario"] == A_SCENARIOS[0][0]) & (long["support"] == "지원비 상시")]
    for g, mk in group_masks(b).items():
        s = b[mk]["it_spend"]
        if s.empty:
            continue
        row = {"group": g, "회사 수": len(s),
               "IT예산 1%에 해당하는 금액(만원)": round(s.median() * 0.01 / MAN, 0)}
        for label, share in NEW_PROJECT_SHARES.items():
            row[f"새 프로젝트 예산 {label}(억)"] = round(s.median() * share / EOK, 2)
            row[f"C: VPC당 연 상한(만원, {label})"] = round(s.median() * share / VPC_MIN / MAN, 0)
        rows.append(row)
    print(pd.DataFrame(rows).set_index("group").reindex(GROUP_ORDER).to_string())

    print("\n결과: data/processed/cost_by_company.csv, data/processed/cost_summary.csv")


if __name__ == "__main__":
    main()