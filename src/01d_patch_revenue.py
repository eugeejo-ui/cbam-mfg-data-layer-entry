"""
01d_patch_revenue.py  (1단계 보완: 매출 누락 기업 재수집)

주요계정 API에 매출 행이 없는 기업만 골라,
'단일회사 전체 재무제표' API(fnlttSinglAcntAll)로 매출을 다시 찾는다.
  - 2025 사업보고서: 2025년(당기), 2024년(전기)
  - 2024 사업보고서: 2023년(전기)
  - 별도(OFS) 우선, 연결(CFS)은 비어 있을 때만 보완
실행 전 원본을 data/interim/mfg_listed_financials_before_patch.csv 로 백업한다.
"""

import os
import re
import sys
import time
import shutil
from pathlib import Path

import pandas as pd
import requests

API = "https://opendart.fss.or.kr/api"
REPRT_CODE = "11011"
SLEEP = 0.2

ROOT = Path(__file__).resolve().parents[1]
MFG = ROOT / "data" / "interim" / "mfg_listed_financials.csv"
BACKUP = ROOT / "data" / "interim" / "mfg_listed_financials_before_patch.csv"

ID_COLS = ["corp_code", "corp_name", "stock_code", "corp_cls", "induty_code",
           "jurir_no", "bizr_no", "est_dt", "acc_mt", "adres", "bsns_year", "rcept_no"]
REV_IDS = ["ifrs-full_Revenue", "ifrs_Revenue",
           "ifrs-full_RevenueFromContractsWithCustomers"]
REV_NAME = re.compile(r"^(매출액|수익\(매출액\)|영업수익|매출|수익|매출액\(영업수익\))$")


def get_key() -> str:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        sys.exit("DART_API_KEY 를 찾지 못했습니다. .env 파일을 확인해 주세요.")
    return key


def to_int(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).replace(",", "").strip()
    if s in ("", "-", "nan"):
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        number = int(float(s))
    except ValueError:
        return None
    return -number if negative else number


def call_full(key, corp_code, year, fs_div):
    params = {"crtfc_key": key, "corp_code": corp_code, "bsns_year": year,
              "reprt_code": REPRT_CODE, "fs_div": fs_div}
    for attempt in range(5):
        try:
            data = requests.get(f"{API}/fnlttSinglAcntAll.json",
                                params=params, timeout=30).json()
        except (requests.RequestException, ValueError):
            time.sleep(2 ** attempt)
            continue
        status = data.get("status")
        if status == "000":
            return data.get("list", [])
        if status == "013":
            return []
        if status in ("020", "800"):
            print("  ! 요청 제한/점검 → 60초 대기")
            time.sleep(60)
            continue
        print(f"  ! status={status} {data.get('message')}")
        return []
    return []


def find_revenue(rows):
    """손익계산서(IS) 또는 포괄손익계산서(CIS)에서 매출 행을 찾아 (당기, 전기)를 돌려준다."""
    df = pd.DataFrame(rows)
    if df.empty or "sj_div" not in df.columns:
        return (None, None, None)
    for col in ("account_id", "account_nm"):
        if col not in df.columns:
            df[col] = ""
    df = df[df["sj_div"].isin(["IS", "CIS"])]
    for sj in ("IS", "CIS"):
        part = df[df["sj_div"] == sj]
        hit = part[part["account_id"].isin(REV_IDS)]
        if hit.empty:
            hit = part[part["account_nm"].str.strip().str.match(REV_NAME)]
        if not hit.empty:
            row = hit.iloc[0]
            return (to_int(row.get("thstrm_amount")),
                    to_int(row.get("frmtrm_amount")),
                    f"{row.get('account_id', '')}|{str(row.get('account_nm', '')).strip()}")
    return (None, None, None)


def fmt(v):
    return "없음" if v is None else f"{v:,}"


def patch_one(key, corp_code, base_year, fs_div):
    now_t, now_t1, label = find_revenue(call_full(key, corp_code, base_year, fs_div))
    time.sleep(SLEEP)
    prev_year = str(int(base_year) - 1)
    prev_t, prev_t1, _ = find_revenue(call_full(key, corp_code, prev_year, fs_div))
    time.sleep(SLEEP)
    t, t1, t2 = now_t, now_t1 if now_t1 is not None else prev_t, prev_t1
    return t, t1, t2, label


def main():
    key = get_key()
    df = pd.read_csv(MFG, dtype={c: str for c in ID_COLS})
    if not BACKUP.exists():
        shutil.copy(MFG, BACKUP)
        print(f"백업 저장: {BACKUP.name}")

    if "rev_source" not in df.columns:
        df["rev_source"] = df["ofs_rev_t"].notna().map({True: "주요계정", False: ""})

    gap = df[df["rcept_no"].notna() & df["ofs_rev_t"].isna()]
    print(f"보완 대상 {len(gap)}곳\n")

    for idx, r in gap.iterrows():
        base_year = str(r["bsns_year"]).split(".")[0]
        print(f"■ {r['corp_name']} ({r['stock_code']})")
        for fs in ("OFS", "CFS"):
            p = fs.lower()
            if fs == "CFS" and pd.notna(df.at[idx, "cfs_rev_t"]):
                continue
            t, t1, t2, label = patch_one(key, r["corp_code"], base_year, fs)
            if t is None:
                print(f"  [{fs}] 매출 행 없음")
                continue
            df.at[idx, f"{p}_rev_t"], df.at[idx, f"{p}_rev_t1"], df.at[idx, f"{p}_rev_t2"] = t, t1, t2
            vals = [v for v in (t, t1, t2) if v is not None]
            df.at[idx, f"{p}_rev_3y_avg"] = round(sum(vals) / len(vals))
            if fs == "OFS":
                df.at[idx, "rev_source"] = "전체재무제표"
            print(f"  [{fs}] {label} → 2025 {fmt(t)} / 2024 {fmt(t1)} / 2023 {fmt(t2)}")

    df.to_csv(MFG, index=False, encoding="utf-8-sig")
    left = df[df["rcept_no"].notna() & df["ofs_rev_t"].isna()]
    print(f"\n완료. 별도 매출이 여전히 빈 곳: {len(left)}곳")
    if len(left):
        print(left[["stock_code", "corp_name"]].to_string(index=False))


if __name__ == "__main__":
    main()