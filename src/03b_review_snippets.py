import pandas as pd
from pathlib import Path

pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 200)

ROOT = Path(__file__).resolve().parents[1]
I = ROOT / "data" / "interim"
s = pd.read_csv(I / "report_keyword_snippets.csv", dtype=str)
f = pd.read_csv(I / "mfg_final.csv", dtype=str)


def show(rows, n_per_company):
    for code, g in rows.groupby("stock_code", sort=False):
        head = g.iloc[0]
        print(f"■ {head['corp_name']} ({head['wave_group']})")
        for ctx in g["context"].head(n_per_company):
            print(f"   …{str(ctx).strip()}…")


print("[1] CBAM 언급 문맥 (회사별 최대 2개)")
show(s[s["keyword"] == "CBAM"], 2)

print("\n[2] 배터리 여권 언급 문맥 (회사별 최대 2개)")
show(s[s["keyword"] == "배터리여권"], 2)

print("\n[3] 제품명 확인으로 2차에 올라간 회사 (회사별 첫 문맥 1개)")
up = f[f["wave_group_final"] == "2차(2028, 제품명 확인)"]
prod = s[s["keyword"].isin(["기어박스", "휠", "현가장치", "라디에이터"])]
for _, r in up.iterrows():
    ctx = prod[prod["stock_code"] == r["stock_code"]].head(1)
    kw = ctx["keyword"].iloc[0] if len(ctx) else "-"
    txt = str(ctx["context"].iloc[0]).strip() if len(ctx) else "-"
    print(f"■ {r['corp_name']} [{r['induty_code']}] {kw}\n   …{txt}…")

print("\n[4] '2차 후보'에 남은 회사의 업종코드 분포 (상위 25)")
rem = f[f["wave_group_final"] == "2차 후보(확인 필요)"]
print(f"총 {len(rem)}곳")
print(rem["induty_code"].value_counts().head(25).to_string())