"""
02_classify.py  (2단계-A: 기업 규모 판정 + CBAM 1차 파도 표시)

입력
  data/interim/mfg_listed_financials.csv          1단계 결과 (제조업 상장사 1,610곳)
  data/external/*기업집단별*개요*.xlsx              공정위 기업집단별 개요 (102개 집단)
  data/external/*소속회사*개요*.xlsx                공정위 소속회사 개요 (법인등록번호 포함)
  data/external/*할당대상업체*.xlsx                 배출권거래제 할당대상업체 (772개)

판정 순서
  1. 법인등록번호로 공정위 소속회사와 대조
     - 상호출자제한기업집단(공정위 자산총액 12조 원 이상) 소속 → 대기업
     - 그 외 공시대상기업집단 소속 → 중견 (중소기업기본법 제2조 단서: 공시대상 소속은 중소 제외)
  2. 그룹 미소속 기업
     - 최근 3년 평균 매출이 업종 기준 이하이고 자산총액 5,000억 원 미만 → 중소
     - 그 외 → 중견
     - 별도 매출이 없으면 연결 매출로 대체 (지주회사형)
  3. 지주회사형 상장사 표시 (운영 자회사와 이중 집계 방지, 집계 제외)
  4. 배출권거래제 할당대상업체와 회사명으로 대조 (법인등록번호 없음, 영문 약어는 한글 읽기로 통일)
  5. CBAM 1차 파도 업종 표시
     - 원재료: 철강, 알루미늄, 시멘트, 비료
     - 1차 가공품: 구조물(7308·7610), 탱크·용기(7309~7311·7611~7613), 볼트·너트(7318)
     - 기타 파스너·단조품처럼 업종 안에 대상·비대상이 섞인 경우는 일부해당(집계 제외)

출력
  data/interim/mfg_classified.csv          1,610곳 판정 결과
  data/interim/kets_match_review.csv       배출권 명단과 이름이 맞은 상장 제조사 (검토용)
  data/interim/kets_unmatched_wave1.csv    1차 파도 업종 배출권 업체 중 이름이 안 맞은 곳 (검토용)
"""

import re
import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
EXTERNAL = ROOT / "data" / "external"

EOK = 100_000_000                 # 1억 원
LARGE_GROUP_ASSET = 12_000_000    # 상호출자제한 기준 12조 원 (공정위 파일 단위: 백만 원)
SME_ASSET_CAP = 5_000 * EOK       # 자산총액 5,000억 원

# 중소기업기본법 시행령 별표 1 (2025-10-01 개정) 제조업 평균매출액 기준 (억 원)
SME_REV_LIMIT = {
    "17": 1800, "24": 1800, "28": 1800,
    "14": 1500, "15": 1500, "32": 1500,
    "10": 1200, "20": 1200, "22": 1200, "25": 1200, "29": 1200, "30": 1200, "31": 1200,
    "12": 1000, "13": 1000, "16": 1000, "19": 1000, "26": 1000, "33": 1000,
    "11": 800, "18": 800, "21": 800, "23": 800, "27": 800,
    "34": 600,
}
SME_REV_EXCEPTION = {"30393": 1500}   # 자동차용 신품 의자 제조업

# CBAM 1차 파도(현행 대상 품목, 규정 2023/956 부속서 I) 관련 한국표준산업분류
# 원재료
CBAM_WAVE1 = {
    "241": "철강",                   # 1차 철강 (제철·제강·합금철·압연·강관·관이음쇠·도금 등) ← CN 72, 7301~7307
    "24212": "알루미늄",             # 알루미늄 제련·정련·합금 ← CN 7601
    "24222": "알루미늄",             # 알루미늄 압연·압출·연신 ← CN 7604~7608
    "23311": "시멘트",               # 시멘트 제조 ← CN 2523
    "2031": "비료",                  # 비료 및 질소화합물 ← CN 2814, 3102, 3105 등
    # 1차 가공품
    "2511": "구조물",                # 구조용 금속제품 (문·창·골조·판제품) ← CN 7308, 7610
    "25122": "탱크·용기",            # 금속탱크 및 저장용기 ← CN 7309, 7611
    "25123": "탱크·용기",            # 압축 및 액화 가스용기 ← CN 7311, 7613
    "25991": "탱크·용기",            # 금속캔 및 기타 포장용기 ← CN 7310, 7612
    "25941": "볼트·너트",            # 볼트 및 너트류 ← CN 7318
}
# 업종코드만으로는 대상 여부를 가릴 수 없는 업종 → 일부해당(집계 제외)
CBAM_WAVE1_PARTIAL = {
    "25942": "기타 파스너(일부)",    # 그 외 금속 파스너 및 나사제품 (못 등 CN 7317은 비대상)
    "2591": "단조·압형(일부)",       # 금속 단조·압형·분말야금 ← CN 7326 일부 세부코드만 대상
}
WAVE1_TYPE = {"철강": "원재료", "알루미늄": "원재료", "시멘트": "원재료", "비료": "원재료",
              "구조물": "가공품", "탱크·용기": "가공품", "볼트·너트": "가공품"}

ID_COLS = ["corp_code", "corp_name", "stock_code", "corp_cls", "induty_code",
           "jurir_no", "bizr_no", "est_dt", "acc_mt", "adres", "bsns_year", "rcept_no"]


# ---------------------------------------------------------------- 공통

def find_file(pattern: str) -> Path:
    hits = sorted(EXTERNAL.glob(pattern))
    if not hits:
        sys.exit(f"data/external 에서 '{pattern}' 파일을 찾지 못했습니다.")
    if len(hits) > 1:
        print(f"  참고: '{pattern}' 파일이 여러 개라 이름순 마지막(최신) 사용 → {hits[-1].name}")
    return hits[-1]


def digits(x) -> str:
    return re.sub(r"\D", "", str(x)) if pd.notna(x) else ""


LETTER_KO = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지",
    "H": "에이치", "I": "아이", "J": "제이", "K": "케이", "L": "엘", "M": "엠", "N": "엔",
    "O": "오", "P": "피", "Q": "큐", "R": "알", "S": "에스", "T": "티", "U": "유",
    "V": "브이", "W": "더블유", "X": "엑스", "Y": "와이", "Z": "제트",
}


def norm_name(x) -> str:
    """회사명 비교용: 법인 표기·공백·괄호 제거, 영문은 한글 알파벳 읽기로 변환 (KG스틸 = 케이지스틸)."""
    s = str(x) if pd.notna(x) else ""
    s = re.sub(r"주식회사|유한회사|유한책임회사|합자회사|㈜|\(주\)|\(유\)|\(합\)", "", s)
    s = re.sub(r"[\s\.\,\-·&()]", "", s).upper()
    return "".join(LETTER_KO.get(ch, ch) for ch in s)


def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", ""), errors="coerce")


def ksic_match(code: str, full: dict = CBAM_WAVE1, partial: dict = CBAM_WAVE1_PARTIAL):
    """
    업종코드 → (해당 여부, 품목)
      - partial 키로 시작: 일부해당 (업종 안에 대상·비대상 품목이 섞임)
      - full 키로 시작: 해당
      - 키가 code 로 시작 (code 가 더 뭉뚱그려짐, 예: 242, 251): 일부해당
    """
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


# ---------------------------------------------------------------- 입력

def load_inputs():
    mfg = pd.read_csv(INTERIM / "mfg_listed_financials.csv", dtype={c: str for c in ID_COLS})
    mfg["jurir_key"] = mfg["jurir_no"].map(digits)

    groups = pd.read_excel(find_file("*기업집단별*개요*.xlsx"), dtype=str)
    groups["ftc_asset"] = to_num(groups["공정거래위원회자산총액"])
    groups["is_large"] = groups["ftc_asset"] >= LARGE_GROUP_ASSET

    aff = pd.read_excel(find_file("*소속회사*개요*.xlsx"), dtype=str)
    aff["jurir_key"] = aff["법인등록번호"].map(digits)
    aff = aff.merge(groups[["기업집단", "is_large", "ftc_asset"]],
                    left_on="기업집단명", right_on="기업집단", how="left")

    kets = pd.read_excel(find_file("*할당대상업체*.xlsx"), header=0, dtype=str)
    kets = kets.dropna(subset=["업체명"]).copy()
    kets["kets_ksic"] = kets["KSIC 코드"].astype(str).str.strip().str.zfill(5)
    kets["name_key"] = kets["업체명"].map(norm_name)

    print(f"입력: 제조업 상장사 {len(mfg):,} / 기업집단 {len(groups)} "
          f"(상호출자제한 {int(groups['is_large'].sum())}) / 소속회사 {len(aff):,} / 배출권 {len(kets)}")
    return mfg, groups, aff, kets


# ---------------------------------------------------------------- 판정

def attach_groups(mfg: pd.DataFrame, aff: pd.DataFrame) -> pd.DataFrame:
    # 한 회사가 두 집단에 동시에 올라간 경우(합작사) → 집단명은 모두 기록, 대기업 여부는 하나라도 해당하면 True
    agg = (aff.groupby("jurir_key")
              .agg(ftc_group=("기업집단명", lambda s: "/".join(sorted(set(s)))),
                   ftc_is_large=("is_large", "max"))
              .reset_index())
    out = mfg.merge(agg, on="jurir_key", how="left")
    out["ftc_is_large"] = out["ftc_is_large"].fillna(False).astype(bool)
    return out


def classify_row(r) -> pd.Series:
    div = str(r["induty_code"])[:2]
    code = str(r["induty_code"])
    limit_eok = next((v for k, v in SME_REV_EXCEPTION.items() if code.startswith(k)),
                     SME_REV_LIMIT.get(div))

    rev, rev_basis = r["ofs_rev_3y_avg"], "별도"
    if pd.isna(rev):
        rev, rev_basis = r["cfs_rev_3y_avg"], "연결"
    assets = r["ofs_assets_t"] if pd.notna(r["ofs_assets_t"]) else r["cfs_assets_t"]

    if pd.notna(r["ftc_group"]):
        if r["ftc_is_large"]:
            return pd.Series({"size_class": "대기업", "size_reason": "상호출자제한기업집단 소속",
                              "rev_basis": rev_basis, "sme_limit_eok": limit_eok})
        return pd.Series({"size_class": "중견", "size_reason": "공시대상기업집단 소속(중소 제외)",
                          "rev_basis": rev_basis, "sme_limit_eok": limit_eok})

    if pd.isna(rev) or limit_eok is None:
        return pd.Series({"size_class": "판정불가", "size_reason": "매출 또는 업종 기준 없음",
                          "rev_basis": "", "sme_limit_eok": limit_eok})

    over_rev = rev > limit_eok * EOK
    over_asset = pd.notna(assets) and assets >= SME_ASSET_CAP
    if not over_rev and not over_asset:
        reason = f"3년 평균 매출 {rev / EOK:,.0f}억 ≤ 기준 {limit_eok:,}억, 자산 5,000억 미만"
        return pd.Series({"size_class": "중소", "size_reason": reason,
                          "rev_basis": rev_basis, "sme_limit_eok": limit_eok})
    parts = []
    if over_rev:
        parts.append(f"3년 평균 매출 {rev / EOK:,.0f}억 > 기준 {limit_eok:,}억")
    if over_asset:
        parts.append(f"자산 {assets / EOK:,.0f}억 ≥ 5,000억")
    return pd.Series({"size_class": "중견", "size_reason": ", ".join(parts),
                      "rev_basis": rev_basis, "sme_limit_eok": limit_eok})


def flag_holding(df: pd.DataFrame) -> pd.DataFrame:
    """지주회사형 상장사 표시. 운영 자회사와 이중 집계되지 않도록 집계에서 제외한다."""
    df["is_holding"] = df["corp_name"].astype(str).str.contains(r"홀딩스|지주|HOLDINGS", case=False)
    return df


def match_kets(df: pd.DataFrame, kets: pd.DataFrame):
    df["name_key"] = df["corp_name"].map(norm_name)
    k = kets.drop_duplicates("name_key")
    m = df.merge(k[["name_key", "업체코드", "업체명", "kets_ksic"]], on="name_key", how="left")
    m["kets_member"] = m["업체코드"].notna()
    same_div = m["kets_ksic"].str[:2] == m["induty_code"].astype(str).str[:2]
    m["kets_match_note"] = ""
    m.loc[m["kets_member"] & ~same_div, "kets_match_note"] = "업종 대분류 불일치(확인 필요)"
    return m.rename(columns={"업체코드": "kets_code", "업체명": "kets_name"})


def flag_wave1(df: pd.DataFrame) -> pd.DataFrame:
    by_dart = df["induty_code"].map(ksic_match)
    by_kets = df["kets_ksic"].map(lambda c: ksic_match(c) if pd.notna(c) else ("비해당", ""))
    has_kets = df["kets_ksic"].notna()
    level, item = [], []
    for (d_lv, d_it), (k_lv, k_it), kk in zip(by_dart, by_kets, has_kets):
        if "해당" in (d_lv, k_lv):
            level.append("해당")
            item.append(d_it if d_lv == "해당" else k_it)
        elif kk:
            # 배출권 명단의 5자리 업종코드가 더 세분화되어 있으므로 우선 적용
            level.append(k_lv)
            item.append(k_it)
        elif d_lv == "일부해당":
            level.append("일부해당")
            item.append(d_it)
        else:
            level.append("비해당")
            item.append("")
    df["cbam_wave1_industry"] = level
    df["cbam_wave1_item"] = item
    df["cbam_wave1_type"] = [WAVE1_TYPE.get(it, "") if lv == "해당" else "" for lv, it in zip(level, item)]
    return df


# ---------------------------------------------------------------- 실행

def main():
    mfg, groups, aff, kets = load_inputs()

    df = attach_groups(mfg, aff)
    df = pd.concat([df, df.apply(classify_row, axis=1)], axis=1)
    df = flag_holding(df)
    df = match_kets(df, kets)
    df = flag_wave1(df)

    keep = ID_COLS + ["ftc_group", "ftc_is_large", "is_holding", "size_class", "size_reason", "rev_basis",
                      "sme_limit_eok", "ofs_rev_t", "ofs_rev_3y_avg", "ofs_assets_t",
                      "cfs_rev_t", "cfs_rev_3y_avg", "cfs_assets_t",
                      "kets_member", "kets_code", "kets_name", "kets_ksic", "kets_match_note",
                      "cbam_wave1_industry", "cbam_wave1_item", "cbam_wave1_type"]
    keep = [c for c in keep if c in df.columns]
    df[keep].to_csv(INTERIM / "mfg_classified.csv", index=False, encoding="utf-8-sig")

    review = df[df["kets_member"]][["stock_code", "corp_name", "kets_name", "induty_code",
                                    "kets_ksic", "size_class", "kets_match_note"]]
    review.to_csv(INTERIM / "kets_match_review.csv", index=False, encoding="utf-8-sig")

    # 1차 파도 업종인데 상장 제조사와 이름이 맞지 않은 배출권 업체 (수동 확인용)
    kets["wave1"] = kets["kets_ksic"].map(lambda c: ksic_match(c)[0])
    unmatched = kets[(kets["wave1"] == "해당") & ~kets["업체코드"].isin(df["kets_code"])]
    unmatched[["업체코드", "업체명", "kets_ksic"]].to_csv(
        INTERIM / "kets_unmatched_wave1.csv", index=False, encoding="utf-8-sig")

    print("\n===== 규모 판정 =====")
    print(df["size_class"].value_counts().to_string())
    print(f"  └ 중견 중 공시대상기업집단 소속: "
          f"{(df['size_reason'] == '공시대상기업집단 소속(중소 제외)').sum()}")
    print(f"  └ 연결 매출로 대체 판정: {(df['rev_basis'] == '연결').sum()}")

    print("\n===== 배출권 명단 대조 =====")
    print(f"제조업 상장사 중 할당대상업체: {int(df['kets_member'].sum())}곳 "
          f"(업종 대분류 불일치 {int((df['kets_match_note'] != '').sum())}곳)")
    print(pd.crosstab(df["size_class"], df["kets_member"]).to_string())

    print("\n===== 지주회사형 (집계 제외) =====")
    hold = df[df["is_holding"]]
    print(f"{len(hold)}곳: " + ", ".join(hold["corp_name"].tolist()))

    ops = df[~df["is_holding"]]
    print("\n===== CBAM 1차 파도 업종 (지주회사 제외) =====")
    print(pd.crosstab(ops["size_class"], ops["cbam_wave1_industry"]).to_string())
    mid = ops[ops["size_class"] == "중견"]
    w1 = mid[mid["cbam_wave1_industry"] == "해당"]
    print(f"\n중견 {len(mid)}곳 중 1차 파도 업종 {len(w1)}곳 "
          f"(그중 배출권 할당대상 {int(w1['kets_member'].sum())}곳)")
    print(w1.groupby(["cbam_wave1_type", "cbam_wave1_item"]).size().to_string())
    part = mid[mid["cbam_wave1_industry"] == "일부해당"]
    print(f"  └ '일부해당'(업종코드로 대상 품목 여부 판단 불가) {len(part)}곳은 집계 제외")
    if len(part):
        print(part["cbam_wave1_item"].value_counts().to_string())

    print(f"\n배출권 명단 중 1차 파도 업종인데 상장 제조사와 이름이 안 맞은 업체: {len(unmatched)}곳"
          " (비상장이 대부분, kets_unmatched_wave1.csv 에서 확인)")
    print("\n결과: data/interim/mfg_classified.csv, kets_match_review.csv, kets_unmatched_wave1.csv")


if __name__ == "__main__":
    main()