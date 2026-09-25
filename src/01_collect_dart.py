#!/usr/bin/env python3
"""
01_collect_dart.py  (1단계: 전자공시 데이터 수집)

하는 일
  A. 전자공시(OpenDART)에서 전체 회사 코드를 받아 '상장사'만 남긴다
  B. 상장사마다 기업개황을 받아 '제조업'(업종코드 앞 두 자리 10~34)만 남긴다
  C. 제조업 상장사의 2025 사업보고서 주요계정(매출액, 자산총계)을 받는다
     - 당기·전기·전전기 3개년을 함께 받는다 (중소기업 판정에 3년 평균 매출이 필요)
     - 연결(CFS)·별도(OFS)를 모두 저장한다
     - 2025 보고서가 없는 회사는 2024 보고서로 한 번 더 시도한다

실행 전
  pip install -r requirements.txt
  프로젝트 폴더의 .env 파일에 DART_API_KEY=본인키 를 적어 둔다
  실행: 프로젝트 폴더에서  python src/01_collect_dart.py

결과 파일
  data/raw/dart_listed_corps.csv          상장사 목록
  data/raw/dart_company_overview.csv      상장사 기업개황 (업종코드, 법인등록번호 포함)
  data/raw/dart_financials_long.csv       주요계정 원자료 (세로형)
  data/interim/mfg_listed_financials.csv  제조업 상장사 1행 1회사 요약 (다음 단계 입력값)
  data/interim/missing_financials.csv     재무 데이터를 못 받은 회사

중간에 끊겨도 다시 실행하면 이미 받은 기업개황은 건너뛴다.
"""

import io
import os
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

API = "https://opendart.fss.or.kr/api"
BSNS_YEAR = "2025"
FALLBACK_YEAR = "2024"
REPRT_CODE = "11011"          # 11011 = 사업보고서
BATCH = 100                   # 다중회사 주요계정 API 1회 최대 회사 수
SLEEP = 0.15                  # 호출 간 대기(초)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"

REVENUE_NAMES = ["매출액", "수익(매출액)", "영업수익", "매출"]
ASSET_NAMES = ["자산총계"]

FATAL = {
    "010": "등록되지 않은 키입니다.",
    "011": "사용할 수 없는 키입니다.",
    "012": "접근할 수 없는 IP입니다.",
    "901": "계정 개인정보 보유기간이 만료되었습니다.",
}


# ---------------------------------------------------------------- 공통 유틸

def get_key() -> str:
    try:
        from dotenv import load_dotenv      # .env 파일이 있으면 읽는다
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        sys.exit("DART_API_KEY 를 찾지 못했습니다. 프로젝트 폴더의 .env 파일을 확인해 주세요.")
    return key


def to_int(value):
    """'1,234' '-1,234' '(1,234)' '' '-' 를 정수 또는 None 으로 바꾼다."""
    if value is None:
        return None
    s = str(value).replace(",", "").strip()
    if s in ("", "-"):
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        number = int(float(s))
    except ValueError:
        return None
    return -number if negative else number


def is_manufacturing(induty_code) -> bool:
    """한국표준산업분류 제조업(C) = 중분류 10~34."""
    code = str(induty_code or "").strip()
    if len(code) < 2 or not code[:2].isdigit():
        return False
    return 10 <= int(code[:2]) <= 34


def call_json(key: str, endpoint: str, params: dict, retries: int = 5):
    """JSON API 호출. 정상이면 dict, 데이터 없음이면 None."""
    full = {"crtfc_key": key, **params}
    for attempt in range(retries):
        try:
            r = requests.get(f"{API}/{endpoint}", params=full, timeout=30)
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            wait = 2 ** attempt
            print(f"  ! 통신 오류({e.__class__.__name__}), {wait}초 후 재시도")
            time.sleep(wait)
            continue

        status = data.get("status")
        if status == "000":
            return data
        if status == "013":                 # 조회된 데이터 없음
            return None
        if status in FATAL:
            sys.exit(f"중단: {FATAL[status]} (status {status})")
        if status in ("020", "800"):        # 요청 제한 초과 / 시스템 점검
            print(f"  ! {data.get('message')} → 60초 대기 후 재시도")
            time.sleep(60)
            continue
        print(f"  ! 예상 밖 응답 status={status} message={data.get('message')}")
        return None
    print("  ! 재시도 횟수 초과, 건너뜀")
    return None


# ---------------------------------------------------------------- A. 상장사 목록

def fetch_listed_corps(key: str) -> pd.DataFrame:
    print("[A] 전체 회사 코드 다운로드 중...")
    r = requests.get(f"{API}/corpCode.xml", params={"crtfc_key": key}, timeout=120)
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
    except zipfile.BadZipFile:
        sys.exit("회사 코드 파일을 받지 못했습니다. 응답 내용:\n" + r.text[:500])

    root = ET.fromstring(z.read(z.namelist()[0]))
    rows = []
    for el in root.iter("list"):
        rows.append({
            "corp_code": (el.findtext("corp_code") or "").strip(),
            "corp_name": (el.findtext("corp_name") or "").strip(),
            "stock_code": (el.findtext("stock_code") or "").strip(),
            "modify_date": (el.findtext("modify_date") or "").strip(),
        })
    df = pd.DataFrame(rows)
    listed = df[df["stock_code"] != ""].reset_index(drop=True)
    print(f"    전체 {len(df):,}개 중 상장사 {len(listed):,}개")
    return listed


# ---------------------------------------------------------------- B. 기업개황

OVERVIEW_COLS = ["corp_code", "corp_name", "stock_code", "corp_cls", "induty_code",
                 "jurir_no", "bizr_no", "est_dt", "acc_mt", "adres"]


def fetch_overviews(key: str, listed: pd.DataFrame, path: Path) -> pd.DataFrame:
    done = pd.DataFrame(columns=OVERVIEW_COLS)
    if path.exists():
        done = pd.read_csv(path, dtype=str).fillna("")
    done_codes = set(done["corp_code"])
    todo = [c for c in listed["corp_code"] if c not in done_codes]
    print(f"[B] 기업개황: 이미 받음 {len(done_codes):,}개, 남음 {len(todo):,}개 "
          f"(예상 {len(todo) * 0.4 / 60:.0f}분 내외)")

    buffer = []
    for i, code in enumerate(todo, 1):
        data = call_json(key, "company.json", {"corp_code": code})
        if data:
            buffer.append({c: str(data.get(c, "") or "") for c in OVERVIEW_COLS})
        if i % 100 == 0 or i == len(todo):
            if buffer:
                done = pd.concat([done, pd.DataFrame(buffer)], ignore_index=True)
                done.to_csv(path, index=False, encoding="utf-8-sig")
                buffer = []
            print(f"    {i:,}/{len(todo):,} 진행")
        time.sleep(SLEEP)

    done["is_mfg"] = done["induty_code"].apply(is_manufacturing)
    odd = done[~done["induty_code"].str[:2].str.isdigit().fillna(False)]
    if len(odd):
        print(f"    참고: 업종코드가 숫자가 아닌 회사 {len(odd)}개 (제조업에서 제외됨)")
    return done


# ---------------------------------------------------------------- C. 주요계정

FIN_COLS = ["corp_code", "bsns_year", "rcept_no", "fs_div", "account_nm",
            "thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount", "currency"]


def fetch_financials(key: str, corp_codes: list, year: str) -> pd.DataFrame:
    rows = []
    batches = [corp_codes[i:i + BATCH] for i in range(0, len(corp_codes), BATCH)]
    for n, batch in enumerate(batches, 1):
        data = call_json(key, "fnlttMultiAcnt.json", {
            "corp_code": ",".join(batch),
            "bsns_year": year,
            "reprt_code": REPRT_CODE,
        })
        for item in (data or {}).get("list", []):
            rows.append({c: item.get(c, "") for c in FIN_COLS})
        print(f"    {year}년 {n}/{len(batches)} 묶음 완료")
        time.sleep(SLEEP)
    df = pd.DataFrame(rows, columns=FIN_COLS)
    df["bsns_year"] = df["bsns_year"].replace("", year)
    return df


def pick_account(sub: pd.DataFrame, names: list):
    for name in names:
        hit = sub[sub["account_nm"].str.strip() == name]
        if len(hit):
            row = hit.iloc[0]
            return (to_int(row["thstrm_amount"]),
                    to_int(row["frmtrm_amount"]),
                    to_int(row["bfefrmtrm_amount"]))
    return (None, None, None)


def to_wide(long_df: pd.DataFrame) -> pd.DataFrame:
    """회사 1행으로 정리. 연결(CFS)·별도(OFS) 각각 매출 3개년, 자산총계."""
    out = []
    for code, g in long_df.groupby("corp_code"):
        rec = {
            "corp_code": code,
            "bsns_year": g["bsns_year"].iloc[0],
            "rcept_no": g["rcept_no"].iloc[0],
        }
        for fs in ("CFS", "OFS"):
            sub = g[g["fs_div"] == fs]
            rev = pick_account(sub, REVENUE_NAMES)
            ast = pick_account(sub, ASSET_NAMES)
            p = fs.lower()
            rec[f"{p}_rev_t"], rec[f"{p}_rev_t1"], rec[f"{p}_rev_t2"] = rev
            rec[f"{p}_assets_t"] = ast[0]
            vals = [v for v in rev if v is not None]
            rec[f"{p}_rev_3y_avg"] = round(sum(vals) / len(vals)) if vals else None
        out.append(rec)
    return pd.DataFrame(out)


# ---------------------------------------------------------------- 실행

def main():
    key = get_key()
    RAW.mkdir(parents=True, exist_ok=True)
    INTERIM.mkdir(parents=True, exist_ok=True)

    listed = fetch_listed_corps(key)
    listed.to_csv(RAW / "dart_listed_corps.csv", index=False, encoding="utf-8-sig")

    overview = fetch_overviews(key, listed, RAW / "dart_company_overview.csv")
    mfg = overview[overview["is_mfg"] & overview["corp_cls"].isin(["Y", "K"])].copy()
    print(f"    제조업 상장사(유가증권·코스닥): {len(mfg):,}개")

    print(f"[C] {BSNS_YEAR} 사업보고서 주요계정 수집")
    codes = mfg["corp_code"].tolist()
    long_df = fetch_financials(key, codes, BSNS_YEAR)

    missing = sorted(set(codes) - set(long_df["corp_code"]))
    if missing:
        print(f"[C-2] {BSNS_YEAR} 자료 없는 {len(missing)}개 → {FALLBACK_YEAR}년으로 재시도")
        long_df = pd.concat([long_df, fetch_financials(key, missing, FALLBACK_YEAR)],
                            ignore_index=True)
    long_df.to_csv(RAW / "dart_financials_long.csv", index=False, encoding="utf-8-sig")

    wide = to_wide(long_df)
    result = mfg.drop(columns=["is_mfg"]).merge(wide, on="corp_code", how="left")
    result.to_csv(INTERIM / "mfg_listed_financials.csv", index=False, encoding="utf-8-sig")

    still_missing = result[result["rcept_no"].isna()][["corp_code", "corp_name", "stock_code"]]
    still_missing.to_csv(INTERIM / "missing_financials.csv", index=False, encoding="utf-8-sig")

    print("\n===== 1단계 요약 =====")
    print(f"상장사                 {len(listed):,}")
    print(f"제조업 상장사          {len(mfg):,}")
    print(f"재무자료 확보          {result['rcept_no'].notna().sum():,}")
    print(f"  - {BSNS_YEAR}년 보고서   {(result['bsns_year'] == BSNS_YEAR).sum():,}")
    print(f"  - {FALLBACK_YEAR}년 보고서   {(result['bsns_year'] == FALLBACK_YEAR).sum():,}")
    print(f"재무자료 없음          {len(still_missing):,}")
    print("결과: data/interim/mfg_listed_financials.csv")


if __name__ == "__main__":
    main()