"""
03_search_reports.py  (2단계-C: 사업보고서 원문 검색)

대상  data/interim/mfg_classified_waves.csv 중 중견(지주회사 제외)
방법  OpenDART 공시서류원본(document.xml)을 회사별로 1회 내려받아 본문에서 검색어를 찾는다.
      내려받은 본문은 data/raw/reports/<접수번호>.txt.gz 로 저장해 재실행 시 다시 받지 않는다.

검색 1: 규제 언급      CBAM(탄소국경), 배터리 여권
검색 2: 2차 파도 제품  기어박스, 휠, 현가장치, 라디에이터 (자동차 부품 '2차 후보' 확인용)
                      자동차 부품 업종의 '2차 후보'만 제품명이 나오면 '2차(2028, 제품명 확인)'으로 올림
검색 3: 참고           유럽 언급 횟수 (수출 여부의 약한 신호, 단독 판단 근거로 쓰지 않음)

출력
  data/interim/report_keywords.csv         회사별 검색 결과 (횟수, 문맥 1개)
  data/interim/report_keyword_snippets.csv 검색어별 문맥 (눈으로 확인용)
  data/interim/mfg_final.csv               파도 구분 최종본 (제품명 확인 반영)
"""

import gzip
import html
import io
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

API = "https://opendart.fss.or.kr/api"
SLEEP = 0.3

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
CACHE = ROOT / "data" / "raw" / "reports"

KEYWORDS = {
    # 검색 1: 규제 언급
    "CBAM": [r"CBAM", r"탄소\s*국경"],
    "배터리여권": [r"배터리\s*여권", r"배터리\s*패스포트", r"[Bb]attery\s*[Pp]assport"],
    # 검색 2: 2차 파도 제품 (EU 목록은 '해당 제품과 그 부품'까지 포함)
    "기어박스": [r"변속기", r"트랜스미션", r"기어\s*박스", r"감속기"],
    "휠": [r"알루미늄\s*휠", r"스틸\s*휠", r"(?<![가-힣])(?<!스티어링 )휠(?!체어|로더)"],
    "현가장치": [r"현가\s*(?:장치|모듈|시스템|부품)", r"서스펜션", r"쇼크\s*업소버", r"쇽\s*업소버",
                 r"스트럿", r"컨트롤\s*암", r"로어\s*암"],
    "라디에이터": [r"라디에이터", r"라지에이터"],
    # 검색 3: 참고
    "유럽": [r"유럽"],
}
PRODUCT_KEYS = ["기어박스", "휠", "현가장치", "라디에이터"]


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


def xml_to_text(raw: bytes) -> str:
    for enc in ("utf-8", "cp949"):
        try:
            s = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        s = raw.decode("utf-8", errors="ignore")
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s)


def fetch_report_text(key: str, rcept_no: str):
    """본문 텍스트를 돌려준다. 캐시가 있으면 캐시를 쓴다. 실패 시 None."""
    path = CACHE / f"{rcept_no}.txt.gz"
    if path.exists():
        return gzip.decompress(path.read_bytes()).decode("utf-8")

    for attempt in range(4):
        try:
            r = requests.get(f"{API}/document.xml",
                             params={"crtfc_key": key, "rcept_no": rcept_no}, timeout=60)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.content[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(r.content))
            text = " ".join(xml_to_text(z.read(n)) for n in z.namelist())
            path.write_bytes(gzip.compress(text.encode("utf-8")))
            return text
        msg = r.text[:300]
        if "020" in msg or "800" in msg:
            print("  ! 요청 제한/점검 → 60초 대기")
            time.sleep(60)
            continue
        print(f"  ! 원문 없음 ({rcept_no}): {re.sub(r'<[^>]+>', ' ', msg).strip()[:80]}")
        return None
    return None


def search(text: str):
    counts, snippets = {}, {}
    for group, patterns in KEYWORDS.items():
        rx = re.compile("|".join(patterns))
        hits = list(rx.finditer(text))
        counts[group] = len(hits)
        snippets[group] = [text[max(0, m.start() - 60): m.end() + 60] for m in hits[:3]]
    return counts, snippets


AUTO_ITEMS = ("기어박스", "휠", "현가", "자동차")   # 제품명 검색으로 확인할 수 있는 2차 후보 품목


def final_group(r) -> str:
    if r["wave_group"] in ("1차(2027)", "2차(2028)"):
        return r["wave_group"]
    is_auto = any(k in str(r.get("cbam_wave2_item", "")) for k in AUTO_ITEMS)
    if r["wave_group"] == "2차 후보(확인 필요)" and is_auto and r.get("product_hit", False):
        return "2차(2028, 제품명 확인)"
    return r["wave_group"]


def main():
    key = get_key()
    CACHE.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(INTERIM / "mfg_classified_waves.csv", dtype=str)
    df["is_holding"] = df["is_holding"].str.lower().eq("true")
    target = df[(df["size_class"] == "중견") & ~df["is_holding"] & df["rcept_no"].notna()]
    print(f"대상: 중견(지주회사 제외) {len(target)}곳 "
          f"(이미 받은 원문 {sum((CACHE / f'{r}.txt.gz').exists() for r in target['rcept_no'])}곳)")

    rows, snip_rows = [], []
    for i, (_, r) in enumerate(target.iterrows(), 1):
        cached = (CACHE / f"{r['rcept_no']}.txt.gz").exists()
        text = fetch_report_text(key, r["rcept_no"])
        if not cached:
            time.sleep(SLEEP)
        if i % 50 == 0 or i == len(target):
            print(f"    {i}/{len(target)} 진행")
        if text is None:
            rows.append({"corp_code": r["corp_code"], "report_ok": False})
            continue
        counts, snippets = search(text)
        row = {"corp_code": r["corp_code"], "report_ok": True}
        row.update({f"kw_{g}": c for g, c in counts.items()})
        rows.append(row)
        for g, ss in snippets.items():
            for s in ss:
                snip_rows.append({"stock_code": r["stock_code"], "corp_name": r["corp_name"],
                                  "wave_group": r["wave_group"], "keyword": g, "context": s})

    kw = pd.DataFrame(rows)
    out = df.merge(kw, on="corp_code", how="left")
    for g in KEYWORDS:
        col = f"kw_{g}"
        if col not in out.columns:
            out[col] = 0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    out["product_hit"] = out[[f"kw_{g}" for g in PRODUCT_KEYS]].sum(axis=1) > 0
    out["wave_group_final"] = out.apply(final_group, axis=1)

    kw_cols = ["stock_code", "corp_name", "induty_code", "wave_group", "wave_group_final", "report_ok"] + \
              [f"kw_{g}" for g in KEYWORDS]
    out[out["corp_code"].isin(target["corp_code"])][kw_cols].to_csv(
        INTERIM / "report_keywords.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(snip_rows).to_csv(INTERIM / "report_keyword_snippets.csv", index=False, encoding="utf-8-sig")
    out.to_csv(INTERIM / "mfg_final.csv", index=False, encoding="utf-8-sig")

    mid = out[out["corp_code"].isin(target["corp_code"])]
    print(f"\n===== 원문 확보 =====")
    print(f"성공 {int(mid['report_ok'].fillna(False).astype(bool).sum())} / 대상 {len(mid)}")

    print("\n===== 검색 1: 규제 언급 (회사 수) =====")
    for g in ["CBAM", "배터리여권"]:
        hit = mid[mid[f"kw_{g}"] > 0]
        print(f"  {g}: {len(hit)}곳")
        if len(hit):
            print("    " + ", ".join(hit["corp_name"].head(15)))
    cbam = mid[mid["kw_CBAM"] > 0]
    if len(cbam):
        print("  CBAM 언급 회사의 파도 구분:")
        print(cbam["wave_group"].value_counts().to_string())

    print("\n===== 검색 2: 2차 후보 중 제품명 확인 =====")
    cand = mid[mid["wave_group"] == "2차 후보(확인 필요)"]
    conf = cand[cand["product_hit"]]
    print(f"  2차 후보 {len(cand)}곳 중 제품명 확인 {len(conf)}곳")
    for g in PRODUCT_KEYS:
        print(f"    {g}: {int((cand[f'kw_{g}'] > 0).sum())}곳")

    order = ["1차(2027)", "2차(2028)", "2차(2028, 제품명 확인)", "2차 후보(확인 필요)", "비대상"]
    print("\n===== 최종 파도 분포 (중견, 지주회사 제외) =====")
    print(mid["wave_group_final"].value_counts().reindex(order, fill_value=0).to_string())
    low = mid["wave_group_final"].isin(order[:3]).sum()
    high = low + (mid["wave_group_final"] == "2차 후보(확인 필요)").sum()
    print(f"\n2028년까지 CBAM 대응 필요 중견: 최소 {low}곳 ~ 최대 {high}곳 "
          f"(중견의 {low/len(mid):.0%} ~ {high/len(mid):.0%})")

    print("\n결과: report_keywords.csv, report_keyword_snippets.csv (문맥 확인용), mfg_final.csv")


if __name__ == "__main__":
    main()