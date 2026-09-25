"""
06_verify_numbers.py  (5단계: 문서 수치 대조)

README.md 및 docs/progress 문서에 기재한 수치를 결과 파일에서 다시 계산하여 대조함
  - 일치: [일치]   /   불일치: [불일치] 기재값 vs 계산값   /   파일·열 없음: [확인 불가]
  - 반올림 표기 수치는 표기 자릿수 기준으로 비교함

입력  data/raw, data/interim, data/processed 의 결과 파일
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, INTERIM, PROCESSED = ROOT / "data" / "raw", ROOT / "data" / "interim", ROOT / "data" / "processed"

RESULTS = {"일치": 0, "불일치": 0, "확인 불가": 0}
FX, SUPPORT = 1366, 3.0
HB, HA = 22 * 10 * 12, 24 * 365


def check(label, fn, expected, digits=None):
    try:
        actual = fn()
        a = round(float(actual), digits) if digits is not None else actual
        e = round(float(expected), digits) if digits is not None else expected
        if a == e:
            RESULTS["일치"] += 1
            print(f"  [일치]     {label}: {e}")
        else:
            RESULTS["불일치"] += 1
            print(f"  [불일치]   {label}: 기재 {e} / 계산 {a}")
    except Exception as ex:  # 파일·열 누락 등
        RESULTS["확인 불가"] += 1
        print(f"  [확인 불가] {label}: {ex.__class__.__name__} {ex}")


def read(path, **kw):
    try:
        return pd.read_csv(path, dtype=str, **kw)
    except FileNotFoundError:
        print(f"  ! 파일 없음: {path.relative_to(ROOT)}")
        return pd.DataFrame()


def num(s):
    return pd.to_numeric(s, errors="coerce")


def truthy(s):
    return s.astype(str).str.lower().eq("true")


def main():
    listed = read(RAW / "dart_listed_corps.csv")
    fin = read(INTERIM / "mfg_listed_financials.csv")
    cls = read(INTERIM / "mfg_classified.csv")
    fr = read(INTERIM / "mfg_final_reviewed.csv")
    it = read(INTERIM / "it_spend_matched.csv")
    cs = read(PROCESSED / "cost_summary.csv")

    for d in (cls, fr, it):
        d["hold"] = truthy(d["is_holding"]) if "is_holding" in d else False
    mid = fr[(fr["size_class"] == "중견") & ~fr["hold"]] if "size_class" in fr else fr

    print("\n[1] 대상 기업 선별")
    check("상장사", lambda: len(listed), 3994)
    check("제조업 상장사", lambda: len(fin), 1610)
    for k, v in {"대기업": 111, "중견": 657, "중소": 831, "판정불가": 11}.items():
        check(f"규모 판정 {k}", lambda k=k: int((cls["size_class"] == k).sum()), v)
    check("공시대상기업집단 소속 중견", lambda: int((cls["size_reason"] == "공시대상기업집단 소속(중소 제외)").sum()), 65)
    check("지주회사형 전체", lambda: int(cls["hold"].sum()), 23)
    check("지주회사형 중 중견", lambda: int((cls["hold"] & (cls["size_class"] == "중견")).sum()), 12)
    check("분석 대상 중견", lambda: len(mid), 645)

    print("\n[2] 배출권 명단 대조")
    km = truthy(cls["kets_member"]) if "kets_member" in cls else pd.Series(dtype=bool)
    check("대조 기업 수", lambda: int(km.sum()), 194)
    for k, v in {"대기업": 65, "중견": 120, "중소": 9}.items():
        check(f"대조 기업 중 {k}", lambda k=k: int((km & (cls["size_class"] == k)).sum()), v)
    check("업종 대분류 불일치", lambda: int(cls["kets_match_note"].fillna("").ne("").sum()), 20)

    print("\n[3] CBAM 적용 단계 구분 (중견 645곳)")
    wg = mid["wave_group_reviewed"].value_counts() if "wave_group_reviewed" in mid else pd.Series(dtype=int)
    for k, v in {"1차(2027)": 58, "2차(2028)": 21, "2차(2028, 제품명 확인)": 15,
                 "2차 후보(확인 필요)": 95, "2차 후보-약": 24, "비대상": 432}.items():
        check(f"{k}", lambda k=k: int(wg.get(k, 0)), v)
    low = lambda: int(mid["wave_group_reviewed"].isin(["1차(2027)", "2차(2028)", "2차(2028, 제품명 확인)"]).sum())
    check("최소 합계", low, 94)
    check("최소 비율(%)", lambda: low() / len(mid) * 100, 15, 0)
    check("최대 합계", lambda: low() + int(wg.get("2차 후보(확인 필요)", 0)), 189)
    check("최대 비율(%)", lambda: (low() + int(wg.get("2차 후보(확인 필요)", 0))) / len(mid) * 100, 29, 0)
    check("1차 대비 최소 배수", lambda: low() / 58, 1.6, 1)

    w1 = mid[mid["wave_group_reviewed"] == "1차(2027)"] if "wave_group_reviewed" in mid else mid
    items = w1.get("cbam_wave1_item", pd.Series(dtype=str)).value_counts()
    for k, v in {"철강": 35, "알루미늄": 6, "시멘트": 5, "비료": 1, "구조물": 7, "탱크·용기": 3, "볼트·너트": 1}.items():
        check(f"1차 적용 품목 {k}", lambda k=k: int(items.get(k, 0)), v)
    check("1차 적용 중 배출권 할당대상", lambda: int(truthy(w1["kets_member"]).sum()), 25)
    try:
        w2 = mid[mid["wave_group_reviewed"] == "2차(2028)"]["cbam_wave2_item"].value_counts()
    except KeyError:
        w2 = pd.Series(dtype=int)
    for k, v in {"전동기·변압기": 6, "건설·광업 기계": 3, "크레인·컨베이어 등": 3, "농기계": 3,
                 "전선·케이블": 3, "냉장고·세탁기 등": 2, "철강 주조품": 1}.items():
        check(f"2차 적용 예정 품목 {k}", lambda k=k: int(w2.get(k, 0)), v)
    try:
        cand = mid[mid["wave_group_reviewed"] == "2차 후보(확인 필요)"]["induty_code"].value_counts()
    except KeyError:
        cand = pd.Series(dtype=int)
    check("2차 적용 후보 중 303", lambda: int(cand.get("303", 0)), 38)
    check("2차 적용 후보 중 292", lambda: int(cand.get("292", 0)), 24)

    print("\n[4] 사업보고서 검색")
    check("CBAM 언급 중견", lambda: int((num(mid["kw_CBAM"]) > 0).sum()), 8)
    check("CBAM 언급 비율(%)", lambda: (num(mid["kw_CBAM"]) > 0).mean() * 100, 1.2, 1)
    check("1차 적용 대상 중 CBAM 언급", lambda: int((num(w1["kw_CBAM"]) > 0).sum()), 5)
    check("배터리 여권 언급", lambda: int((num(mid["kw_배터리여권"]) > 0).sum()), 2)
    try:
        up = mid[mid["wave_group_final"] == "2차(2028, 제품명 확인)"]["review_decision"].value_counts()
    except KeyError:
        up = pd.Series(dtype=int)
    for k, v in {"확인": 15, "제외": 18, "보류": 4}.items():
        check(f"제품명 검토 {k}", lambda k=k: int(up.get(k, 0)), v)

    print("\n[5] 정보기술부문 투자액 확보")
    ok = it[num(it["it_ratio"]).notna() & ~it["hold"]] if "it_ratio" in it else it
    base = it[~it["hold"]] if "hold" in it else it
    for k, (tot, got) in {"대기업": (108, 86), "중견": (645, 296), "중소": (823, 3)}.items():
        check(f"{k} 전체", lambda k=k: int((base["size_class"] == k).sum()), tot)
        check(f"{k} 공시값 확보", lambda k=k: int((ok["size_class"] == k).sum()), got)
    check("2025년 실적", lambda: int((ok["it_year"].str.startswith("2025")).sum()), 375)
    check("2024년 실적(보조)", lambda: int((ok["it_year"].str.startswith("2024")).sum()), 10)
    bands = {"3천억 미만": (27, 1.13), "3천억~5천억": (129, 0.46), "5천억~1조": (100, 0.52),
             "1조~5조": (105, 0.64), "5조 이상": (24, 1.09)}
    for k, (n, med) in bands.items():
        sub = ok[ok.get("rev_band", pd.Series("", index=ok.index)) == k]
        check(f"매출 구간 {k} 기업 수", lambda sub=sub: len(sub), n)
        check(f"매출 구간 {k} 중앙값(%)", lambda sub=sub: num(sub["it_ratio"]).median() * 100, med, 2)
    check("순위상관계수", lambda: num(ok["it_ratio"]).rank().corr(num(ok["rev_same_year"]).rank()), 0.14, 2)
    for k, (n, med) in {"의무": (363, 0.56), "자율": (22, 1.01)}.items():
        sub = ok[ok.get("kisa_type_used", pd.Series("", index=ok.index)) == k]
        check(f"{k}공시 기업 수", lambda sub=sub: len(sub), n)
        check(f"{k}공시 중앙값(%)", lambda sub=sub: num(sub["it_ratio"]).median() * 100, med, 2)

    print("\n[6] A 연간 비용 (만 원)")
    a = {("소형·업무시간", False): 1803, ("소형·업무시간", True): 4311, ("소형·상시", True): 5983,
         ("중형·업무시간", False): 5121, ("중형·업무시간", True): 7629, ("중형·상시", True): 16992,
         ("대형·상시", True): 27044}
    eng = {"소형": 2.0, "중형": 11.2, "대형": 19.6}
    for (name, always), v in a.items():
        size, when = name.split("·")
        hrs = HB if when == "업무시간" else HA
        check(f"{name} (지원비 {'상시' if always else '가동시간만'})",
              lambda size=size, hrs=hrs, always=always:
              (eng[size] * hrs + SUPPORT * (HA if always else hrs)) * FX / 10000, v, 0)

    print("\n[7] IT 예산 증가율 (중앙값·상위 25%, %)")
    for c in ["n", "it_median_eok", "it_increase_median_pct", "it_increase_p75_pct"]:
        if c in cs:
            cs[c] = num(cs[c])

    def cell(group, scen, sup, col):
        r = cs[(cs["group"] == group) & (cs["A_scenario"] == scen) & (cs["support"] == sup)]
        return float(r[col].iloc[0])

    it_med = {"대기업": 204.5, "중견 전체": 28.6, "중견-1차(2027)": 14.3, "중견-2차(2028)": 17.6,
              "중견-2차 후보": 26.5, "중견-비대상": 33.3}
    for g, v in it_med.items():
        check(f"{g} 정보기술부문 투자액 중앙값(억)",
              lambda g=g: cell(g, "소형·업무시간", "지원비 상시", "it_median_eok"), v, 1)
    table = {  # (최소·가동시간만, 최소·상시, 중형·상시, 대형·상시)
        "대기업": (0.1, 0.2, 0.8, 1.3), "중견 전체": (0.6, 1.5, 5.9, 9.5),
        "중견-1차(2027)": (1.3, 3.0, 11.9, 18.9), "중견-2차(2028)": (1.0, 2.5, 9.7, 15.4),
        "중견-2차 후보": (0.7, 1.6, 6.4, 10.2), "중견-비대상": (0.5, 1.3, 5.1, 8.1)}
    p75 = {"대기업": (0.3, 0.8, 3.3, 5.2), "중견 전체": (1.4, 3.3, 13.0, 20.7),
           "중견-1차(2027)": (3.1, 7.3, 28.9, 46.1), "중견-2차(2028)": (1.7, 4.0, 15.7, 25.1),
           "중견-2차 후보": (1.8, 4.4, 17.3, 27.5), "중견-비대상": (1.1, 2.6, 10.4, 16.5)}
    scen = [("소형·업무시간", "지원비 가동시간만"), ("소형·업무시간", "지원비 상시"),
            ("중형·상시", "지원비 상시"), ("대형·상시", "지원비 상시")]
    for g in table:
        for (sn, sp), v, q in zip(scen, table[g], p75[g]):
            check(f"{g} {sn}/{sp} 중앙값", lambda g=g, sn=sn, sp=sp: cell(g, sn, sp, "it_increase_median_pct"), v, 1)
            check(f"{g} {sn}/{sp} 상위25%", lambda g=g, sn=sn, sp=sp: cell(g, sn, sp, "it_increase_p75_pct"), q, 1)

    print("\n[8] B·C·D 기준선")
    base_line = {"중견 전체": (2857, 4.29, 2143, 6.00, 3000), "중견-1차(2027)": (1433, 2.15, 1075, 3.01, 1505),
                 "중견-2차(2028)": (1762, 2.64, 1321, 3.70, 1850)}
    for g, (one, np15, vpc15, np21, vpc21) in base_line.items():
        med = lambda g=g: cell(g, "소형·업무시간", "지원비 상시", "it_median_eok") * 1e8
        check(f"{g} IT 예산 1%(만원)", lambda med=med: med() * 0.01 / 1e4, one, 0)
        check(f"{g} 신규 프로젝트 15%(억)", lambda med=med: med() * 0.15 / 1e8, np15, 2)
        check(f"{g} VPC 상한 15%(만원)", lambda med=med: med() * 0.15 / 20 / 1e4, vpc15, 0)
        check(f"{g} 신규 프로젝트 21%(억)", lambda med=med: med() * 0.21 / 1e8, np21, 2)
        check(f"{g} VPC 상한 21%(만원)", lambda med=med: med() * 0.21 / 20 / 1e4, vpc21, 0)

    print(f"\n===== 대조 결과: 일치 {RESULTS['일치']} / 불일치 {RESULTS['불일치']} / 확인 불가 {RESULTS['확인 불가']} =====")


if __name__ == "__main__":
    main()