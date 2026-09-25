import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
df = pd.read_csv(ROOT / "data/interim/mfg_listed_financials.csv", dtype=str)
lg = pd.read_csv(ROOT / "data/raw/dart_financials_long.csv", dtype=str)

gap = df[df["rcept_no"].notna() & df["ofs_rev_t"].isna()]
print(f"대상 {len(gap)}곳")

for _, r in gap.iterrows():
    sub = lg[lg["corp_code"] == r["corp_code"]]
    print(f"\n■ {r['corp_name']} ({r['stock_code']}), 보고서 {r['rcept_no']}")
    if sub.empty:
        print("  주요계정 행 없음")
        continue
    for fs, g in sub.groupby("fs_div"):
        names = ", ".join(g["account_nm"].str.strip().unique())
        print(f"  [{fs}] {names}")