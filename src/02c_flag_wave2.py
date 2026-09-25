"""
02c_flag_wave2.py  (2단계-B: CBAM 2차 파도 업종 표시)

근거: EU 집행위 확대안 부속서 COM(2025) 989 (2025-12-17)
  - 철강 표 확대: 주조품(7325), 기타 철강제품 전체(7326), 스프링, 와이어로프·철망, 못, 주방용품
  - 복합 금속 제품 표 신설: 엔진, 펌프, 버너, 냉장고·세탁기, 크레인·컨베이어, 산업용 로봇,
    농기계, 건설기계, 전동기·변압기, 케이블, 화물차, 차체, 기어박스, 휠, 현가장치, 라디에이터,
    금속 가구 등 (2028-01-01 적용 예정, 확정 전)

판정
  해당     : 업종의 대표 제품이 확대안 목록에 있음
  일부해당 : 업종 안의 일부 제품만 목록에 있음 (사업보고서 제품명 검색으로 추가 확인 예정)

입력  data/interim/mfg_classified.csv   (02_classify.py 결과)
출력  data/interim/mfg_classified_waves.csv
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"

CBAM_WAVE2 = {
    # 철강 표 확대분
    "2431": "철강 주조품",               # ← 7325
    "2591": "단조·압형 제품",             # ← 7326 전체
    "25942": "못·기타 파스너",            # ← 7317
    "25944": "와이어로프·철망",           # ← 7312 10, 7314
    # 기계
    "2916": "크레인·컨베이어 등",         # ← 8425, 8426, 8427, 8428, 8431
    "2921": "농기계",                    # ← 8432, 8424 82
    "2923": "주조·야금 기계",             # ← 8454
    "2924": "건설·광업 기계",             # ← 8430, 8474, 8479 10
    "2928": "산업용 로봇",               # ← 8428 70
    # 전기장비
    "2811": "전동기·변압기",              # ← 8501, 8504
    "2830": "전선·케이블",               # ← 8544 (철강·알루미늄 포함분)
    "2851": "냉장고·세탁기 등",           # ← 8418 10, 8450, 8451 21
    # 자동차
    "30122": "화물자동차",               # ← 8704
    "3020": "차체·트레일러",             # ← 8706, 8707 10, 8716
    # 기타
    "32091": "금속 가구",                # ← 9401 79, 9403
}
CBAM_WAVE2_PARTIAL = {
    "25943": "스프링(일부)",              # ← 7320 일부
    "25992": "금속 주방용기(일부)",        # ← 7323 철강제만
    "25932": "일반철물(일부)",            # ← 8302
    "2911": "디젤 엔진(일부)",            # ← 8408
    "3011": "디젤 엔진(일부)",            # ← 8408 20
    "2913": "엔진용·소형 펌프(일부)",      # ← 8413 30, 8413 70 35
    "2915": "버너(일부)",                # ← 8416
    "2917": "냉동장비 부품·냉각탑(일부)",   # ← 8418 99, 8419 89
    "2919": "분사기(일부)",              # ← 8424
    "2922": "석재 가공기(일부)",          # ← 8464
    "3031": "자동차 엔진 부품(일부)",      # ← 8413 30, 8421 23 등
    "3032": "자동차 차체 부품(일부)",      # ← 목록에 거의 없음
    "3033": "기어박스(일부)",             # ← 8708 40
    "3039": "휠·현가장치·라디에이터(일부)", # ← 8708 70, 8708 80, 8708 91
    "2719": "의료기기(일부)",             # ← 9018 일부
    "2721": "가스 분석기(일부)",          # ← 9027 10 90
}
# 한국표준산업분류 번호를 공정위 파일로 직접 대조하지 못한 업종 → 잡힌 회사 이름으로 점검
UNVERIFIED = ["2915", "2923", "25943", "25944"]


def ksic_match(code, full=CBAM_WAVE2, partial=CBAM_WAVE2_PARTIAL):
    code = str(code or "").strip()
    if not code or code == "nan":
        return ("비해당", "")
    for key, item in partial.items():
        if code.startswith(key):
            return ("일부해당", item)
    for key, item in full.items():
        if code.startswith(key):
            return ("해당", item)
    cand = sorted({item for key, item in {**full, **partial}.items() if key.startswith(code)})
    if cand:
        return ("일부해당", "/".join(cand))
    return ("비해당", "")


def combine(dart, kets):
    (d_lv, d_it), (k_lv, k_it) = dart, kets
    if "해당" in (d_lv, k_lv):
        return ("해당", d_it if d_lv == "해당" else k_it)
    if k_lv != "비해당":
        return (k_lv, k_it)
    return (d_lv, d_it)


def wave_group(r):
    if r["cbam_wave1_industry"] == "해당":
        return "1차(2027)"
    if r["cbam_wave2_industry"] == "해당":
        return "2차(2028)"
    if r["cbam_wave2_industry"] == "일부해당" or r["cbam_wave1_industry"] == "일부해당":
        return "2차 후보(확인 필요)"
    return "비대상"


def main():
    df = pd.read_csv(INTERIM / "mfg_classified.csv", dtype=str)
    df["is_holding"] = df["is_holding"].str.lower().eq("true")
    df["kets_member"] = df["kets_member"].str.lower().eq("true")

    res = [combine(ksic_match(d), ksic_match(k) if pd.notna(k) else ("비해당", ""))
           for d, k in zip(df["induty_code"], df["kets_ksic"])]
    df["cbam_wave2_industry"] = [lv for lv, _ in res]
    df["cbam_wave2_item"] = [it for _, it in res]
    df["wave_group"] = df.apply(wave_group, axis=1)
    df.to_csv(INTERIM / "mfg_classified_waves.csv", index=False, encoding="utf-8-sig")

    mid = df[(df["size_class"] == "중견") & ~df["is_holding"]]
    order = ["1차(2027)", "2차(2028)", "2차 후보(확인 필요)", "비대상"]
    print(f"===== 중견 {len(mid)}곳 파도별 분포 (지주회사 제외) =====")
    print(mid["wave_group"].value_counts().reindex(order, fill_value=0).to_string())
    low = (mid["wave_group"].isin(["1차(2027)", "2차(2028)"])).sum()
    high = low + (mid["wave_group"] == "2차 후보(확인 필요)").sum()
    print(f"\n2028년까지 CBAM 대응이 필요한 중견: 최소 {low}곳 ~ 최대 {high}곳 (중견의 {low/len(mid):.0%} ~ {high/len(mid):.0%})")

    print("\n===== 2차(2028) 해당 품목 =====")
    print(mid[mid["wave_group"] == "2차(2028)"]["cbam_wave2_item"].value_counts().to_string())
    print("\n===== 2차 후보(확인 필요) 품목 =====")
    print(mid[mid["wave_group"] == "2차 후보(확인 필요)"]["cbam_wave2_item"].value_counts().head(20).to_string())

    print("\n===== 업종코드 점검 (공정위 파일로 대조 못 한 번호, 전 규모) =====")
    for code in UNVERIFIED:
        hit = df[df["induty_code"].astype(str).str.startswith(code)]
        names = ", ".join(hit["corp_name"].head(10)) if len(hit) else "(해당 회사 없음)"
        print(f"  {code}: {len(hit)}곳 → {names}")

    print("\n결과: data/interim/mfg_classified_waves.csv")


if __name__ == "__main__":
    main()