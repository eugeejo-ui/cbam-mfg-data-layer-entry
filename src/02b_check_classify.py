import pandas as pd
from pathlib import Path

pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 200)

ROOT = Path(__file__).resolve().parents[1]
I = ROOT / "data" / "interim"
df = pd.read_csv(I / "mfg_classified.csv", dtype=str)

print("[1] 배출권 대조 중 업종 대분류 불일치 (오대조 가능성)")
r = pd.read_csv(I / "kets_match_review.csv", dtype=str)
cols = ["stock_code", "corp_name", "kets_name", "induty_code", "kets_ksic", "size_class"]
print(r[r["kets_match_note"].notna()][cols].to_string(index=False))

print("\n[2] 1차 파도 '일부해당' 회사 (품목 확인 필요)")
p = df[df["cbam_wave1_industry"] == "일부해당"]
print(p[["stock_code", "corp_name", "induty_code", "size_class", "cbam_wave1_item"]].to_string(index=False))

print("\n[3] 1차 파도 업종 배출권 업체 중 상장 제조사와 이름이 안 맞은 곳")
u = pd.read_csv(I / "kets_unmatched_wave1.csv", dtype=str)
print(u.to_string(index=False))

print("\n[4] 중견 1차 파도 해당 기업 (별도 매출 큰 순, 단위: 억 원)")
m = df[(df["size_class"] == "중견") & (df["cbam_wave1_industry"] == "해당")].copy()
m["rev_eok"] = (pd.to_numeric(m["ofs_rev_t"], errors="coerce") / 1e8).round(0)
cols = ["stock_code", "corp_name", "induty_code", "cbam_wave1_item", "kets_member", "ftc_group", "rev_eok"]
print(m.sort_values("rev_eok", ascending=False)[cols].to_string(index=False))