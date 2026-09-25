import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ov = pd.read_csv(ROOT / "data/raw/dart_company_overview.csv", dtype=str)
df = pd.read_csv(ROOT / "data/interim/mfg_listed_financials.csv",
                 dtype={"corp_code": str, "stock_code": str, "induty_code": str})

print("[1] 시장 구분 (Y 유가, K 코스닥, N 코넥스, E 기타)")
print(ov["corp_cls"].value_counts().to_string())

print("\n[2] 값이 비어 있는 회사 수 (제조업 상장사 1,610곳 기준)")
for col in ["ofs_rev_t", "ofs_rev_3y_avg", "ofs_assets_t", "cfs_rev_t"]:
    print(f"  {col}: {df[col].isna().sum()}")

print("\n[3] 대표 회사 확인 (단위: 원)")
codes = {"005930": "삼성전자", "005380": "현대자동차", "000270": "기아", "004020": "현대제철"}
cols = ["stock_code", "corp_name", "induty_code", "bsns_year", "ofs_rev_t", "ofs_assets_t"]
print(df[df["stock_code"].isin(codes.keys())][cols].to_string(index=False))

print("\n[4] 재무자료 없는 회사")
print(pd.read_csv(ROOT / "data/interim/missing_financials.csv", dtype=str).to_string(index=False))

print("\n[5] 별도 매출 3년치가 모두 있는 회사 수")
yrs = df[["ofs_rev_t", "ofs_rev_t1", "ofs_rev_t2"]].notna().sum(axis=1)
print(f"  3년 모두: {(yrs == 3).sum()}")
print(f"  2년만:   {(yrs == 2).sum()}")
print(f"  1년만:   {(yrs == 1).sum()}")
print(f"  없음:    {(yrs == 0).sum()}")

print("\n[6] 재무자료는 있는데 별도 매출이 빈 회사")
gap = df[df["rcept_no"].notna() & df["ofs_rev_t"].isna()]
print(gap[["stock_code", "corp_name", "induty_code", "rcept_no"]].to_string(index=False))