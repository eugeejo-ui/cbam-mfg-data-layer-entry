"""
04a_it_spend.py  (3단계-A: 실측 IT 투자액 연결 + 규모별 비율 검증)

자료  KISA 정보보호 공시 이행 기업 리스트
      - 2026년 공시 = 2025년 실적 (기본)
      - 2025년 공시 = 2024년 실적 (2026년에 없는 회사 보조)
      - 사용 항목: 투자현황_정보기술부문 투자액(A)
        (IT 자산 감가상각비, IT 인건비, 시스템 구입·유지보수, IT 서비스 이용료, 외주·컨설팅, 교육, 통신비 포함)

처리
  1. 회사명으로 전자공시 제조업 상장사와 대조 (공시 파일에 법인등록번호가 없음)
  2. IT 투자액 ÷ 같은 연도 별도 매출 = IT 투자 비율
  3. 매출 규모 구간별로 비율이 달라지는지 확인 (작은 회사로 넓혀도 되는지 판단용)

입력  data/interim/mfg_final_reviewed.csv, data/interim/mfg_listed_financials.csv,
      data/external/*정보보호*공시*.xlsx
출력  data/interim/it_spend_matched.csv, data/interim/kisa_unmatched_mfg.csv
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
EOK = 100_000_000

IT_COL = "투자현황_정보기술부문 투자액(A)"
BANDS = [0, 3000, 5000, 10000, 50000, float("inf")]
BAND_LABELS = ["3천억 미만", "3천억~5천억", "5천억~1조", "1조~5조", "5조 이상"]

LETTER_KO = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지",
    "H": "에이치", "I": "아이", "J": "제이", "K": "케이", "L": "엘", "M": "엠", "N": "엔",
    "O": "오", "P": "피", "Q": "큐", "R": "알", "S": "에스", "T": "티", "U": "유",
    "V": "브이", "W": "더블유", "X": "엑스", "Y": "와이", "Z": "제트",
}


def norm_name(x) -> str:
    s = str(x) if pd.notna(x) else ""
    s = re.sub(r"주식회사|유한회사|유한책임회사|합자회사|㈜|\(주\)|\(유\)|\(합\)", "", s)
    s = re.sub(r"[\s\.\,\-·&()]", "", s).upper()
    return "".join(LETTER_KO.get(ch, ch) for ch in s)


def find_year_file(year: str) -> Path:
    hits = sorted(EXTERNAL.glob(f"*{year}*정보보호*공시*.xlsx"))
    if not hits:
        sys.exit(f"data/external 에서 {year}년 정보보호 공시 파일을 찾지 못했습니다.")
    return hits[-1]


def load_kisa(year: str) -> pd.DataFrame:
    d = pd.read_excel(find_year_file(year), dtype=str)
    d["it_spend"] = pd.to_numeric(d[IT_COL].str.replace(",", ""), errors="coerce")
    d = d[d["it_spend"] > 0].copy()          # 0 은 '첨부 참조' 등 미기재로 보고 제외
    d["name_key"] = d["기업명"].map(norm_name)
    d = d.drop_duplicates("name_key")
    return d[["name_key", "기업명", "업종", "자율/의무", "it_spend"]]


def main():
    df = pd.read_csv(INTERIM / "mfg_final_reviewed.csv", dtype=str)
    df["is_holding"] = df["is_holding"].str.lower().eq("true")
    df["name_key"] = df["corp_name"].map(norm_name)
    # 2024년 매출(전기)은 1단계 파일에만 있으므로 가져와 붙인다 (2024년 IT 투자액과 연도 맞춤용)
    prev = pd.read_csv(INTERIM / "mfg_listed_financials.csv", dtype={"corp_code": str},
                       usecols=["corp_code", "ofs_rev_t1", "cfs_rev_t1"])
    df = df.drop(columns=[c for c in ["ofs_rev_t1", "cfs_rev_t1"] if c in df.columns]).merge(
        prev, on="corp_code", how="left")
    for c in ["ofs_rev_t", "ofs_rev_t1", "cfs_rev_t", "cfs_rev_t1"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    k26 = load_kisa("2026").rename(columns={"기업명": "kisa_name", "업종": "kisa_industry",
                                            "자율/의무": "kisa_type", "it_spend": "it_2025"})
    k25 = load_kisa("2025").rename(columns={"기업명": "kisa_name_25", "업종": "kisa_industry_25",
                                            "자율/의무": "kisa_type_25", "it_spend": "it_2024"})
    m = df.merge(k26, on="name_key", how="left").merge(k25, on="name_key", how="left")

    # 2025년 실적 우선, 없으면 2024년 실적 (매출도 같은 연도로 맞춤)
    use26 = m["it_2025"].notna()
    use25 = ~use26 & m["it_2024"].notna()
    m["it_spend"] = m["it_2025"].where(use26, m["it_2024"])
    m["it_year"] = pd.Series("", index=m.index).mask(use26, "2025").mask(use25, "2024")
    rev25 = m["ofs_rev_t"].fillna(m["cfs_rev_t"])
    rev24 = m["ofs_rev_t1"].fillna(m["cfs_rev_t1"])
    m["rev_same_year"] = rev25.where(use26, rev24.where(use25))
    m["it_ratio"] = m["it_spend"] / m["rev_same_year"]
    m["kisa_type_used"] = m["kisa_type"].where(use26, m["kisa_type_25"])
    m["rev_band"] = pd.cut(m["rev_same_year"] / EOK, BANDS, labels=BAND_LABELS, right=False)

    keep = ["stock_code", "corp_name", "size_class", "is_holding", "wave_group_reviewed", "induty_code",
            "kisa_name", "kisa_type_used", "it_year", "it_spend", "rev_same_year", "it_ratio", "rev_band"]
    m[keep].to_csv(INTERIM / "it_spend_matched.csv", index=False, encoding="utf-8-sig")

    # 공시 파일의 제조업 기업 중 상장 제조사와 이름이 안 맞은 곳 (비상장 또는 표기 차이)
    un = k26[k26["kisa_industry"].str.startswith("제조업", na=False) & ~k26["name_key"].isin(df["name_key"])]
    un[["kisa_name", "kisa_type", "it_2025"]].to_csv(INTERIM / "kisa_unmatched_mfg.csv",
                                                      index=False, encoding="utf-8-sig")

    ok = m[m["it_ratio"].notna() & ~m["is_holding"]]
    ops = m[~m["is_holding"]]
    print("===== 대조 결과 (지주회사 제외) =====")
    order = [c for c in ["대기업", "중견", "중소", "판정불가"] if c in set(ops["size_class"])]
    cov = pd.DataFrame({
        "회사 수": ops.groupby("size_class").size(),
        "실측 IT 투자액 확보": ok.groupby("size_class").size(),
    }).reindex(order).fillna(0).astype(int)
    cov["확보율(%)"] = (cov["실측 IT 투자액 확보"] / cov["회사 수"] * 100).round(1)
    print(cov.to_string())
    print(f"  └ 2025년 실적 {int((ok['it_year'] == '2025').sum())}곳, 2024년 실적(보조) {int((ok['it_year'] == '2024').sum())}곳")
    print(f"  └ 공시 파일의 제조업 기업 중 이름 미대조 {len(un)}곳 (kisa_unmatched_mfg.csv, 비상장이 대부분일 것으로 예상)")

    mid = ok[ok["size_class"] == "중견"]
    print("\n===== 중견 파도별 실측 확보 =====")
    allmid = ops[ops["size_class"] == "중견"]
    t = pd.DataFrame({"중견 수": allmid.groupby("wave_group_reviewed").size(),
                      "실측 확보": mid.groupby("wave_group_reviewed").size()}).fillna(0).astype(int)
    print(t.to_string())

    print("\n===== 규모별 IT 투자 비율 (실측 기업 전체, %) =====")
    g = ok.groupby("rev_band", observed=True)["it_ratio"]
    band = pd.DataFrame({
        "회사 수": g.size(),
        "25%": (g.quantile(0.25) * 100).round(2),
        "중앙값": (g.median() * 100).round(2),
        "75%": (g.quantile(0.75) * 100).round(2),
    })
    print(band.to_string())
    rho = ok[["it_ratio", "rev_same_year"]].corr(method="spearman").iloc[0, 1]
    print(f"\n매출 규모와 IT 투자 비율의 순위상관계수(Spearman): {rho:.2f}")
    print("  (0에 가까우면 규모와 무관, 음수면 클수록 비율 낮음, 양수면 클수록 비율 높음)")

    print("\n===== 의무·자율 공시별 IT 투자 비율 중앙값 (%) =====")
    print((ok.groupby("kisa_type_used")["it_ratio"].agg(["size", "median"])
             .assign(median=lambda x: (x["median"] * 100).round(2))).to_string())

    print("\n결과: data/interim/it_spend_matched.csv, data/interim/kisa_unmatched_mfg.csv")


if __name__ == "__main__":
    main()