"""
03c_apply_review.py  (2단계-D: 문맥 검토 결과 반영)

1. 제품명 검색으로 '2차(2028, 제품명 확인)'에 오른 37곳을 문맥 검토 결과로 확정·제외
   - 확인: 자사 제품이 기어박스·휠·현가장치·라디에이터(또는 그 부품)이거나 확대안 목록의 다른 품목
   - 제외: 업계 일반 설명, 특허·연구 문구, 목록에 없는 부품(차축·브라켓·휠커버 등), 사업 이전
   - 보류: 전장·제어 부품처럼 품목 분류가 애매 → 후보로 되돌림
2. '2차 후보' 중 연결이 약한 품목(의료기기·가스분석기·석재가공기만 해당)은 '2차 후보-약'으로 분리해 최대값에서 제외

입력  data/interim/mfg_final.csv
출력  data/interim/mfg_final_reviewed.csv
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"

# 검토 기준: report_keyword_snippets.csv 의 회사별 첫 문맥 (2026-09-25 검토)
REVIEW = {
    "(주)서진오토모티브": ("확인", "자동변속기 제품 라인업"),
    "SNT모티브(주)": ("확인", "전기차 구동모터·드라이브유닛 (전동기 품목과도 연결)"),
    "(주)디아이씨": ("확인", "변속기 기술연구소, 변속기 부품"),
    "지엠비코리아(주)": ("확인", "엔진 워터펌프 (확대안 8413 30 엔진용 냉각 펌프)"),
    "평화산업(주)": ("확인", "에어서스펜션 제품"),
    "(주)화신정공": ("확인", "샤시류 현가장치 관련 부품"),
    "(주)오리엔트정공": ("확인", "변속기 관련 알루미늄 가공·조립 부품"),
    "(주)네오오토": ("확인", "변속기용 기어류"),
    "경창산업(주)": ("확인", "변속기 조작용 레버"),
    "(주)삼기": ("확인", "밸브바디·클러치하우징 등 변속기 부품"),
    "에이치엘만도(주)": ("확인", "제동·조향·현가장치 제조"),
    "핸즈코퍼레이션(주)": ("확인", "알루미늄 휠 제조사 (첫 문맥은 업계 일반 설명, 추가 확인 권장)"),
    "SNT다이내믹스(주)": ("확인", "차축·변속기"),
    "(주)씨티알모빌리티": ("확인", "엔진·변속기 소요 샤프트·로터 부품"),
    "삼보모터스(주)": ("확인", "자동변속기 구성 부품"),
    "(주)서연이화": ("제외", "라디에이터 그릴 조명 특허 (라디에이터 아님)"),
    "(주)화승코퍼레이션": ("제외", "업계 일반 설명"),
    "주식회사 화승알앤에이": ("제외", "업계 일반 설명"),
    "유성기업(주)": ("제외", "피투자회사의 인휠모터 설명"),
    "우리산업(주)": ("제외", "액추에이터용 소형 기어박스 특허 (차량 변속기 아님)"),
    "아진산업(주)": ("제외", "업계 일반 설명"),
    "한국무브넥스(주)": ("제외", "하프샤프트·차축 (확대안 목록 외)"),
    "(주)성우하이텍": ("제외", "업계 일반 설명"),
    "상신브레이크(주)": ("제외", "연구과제 문구, 주력은 제동장치 (목록 외)"),
    "디와이피(주)": ("제외", "업계 일반 설명"),
    "대원산업(주)": ("제외", "시트 액추에이터 특허"),
    "인지컨트롤스(주)": ("제외", "회사 연혁 문구"),
    "에코플라스틱(주)": ("제외", "플라스틱 휠커버 (목록 외)"),
    "(주)디에이치오토리드": ("제외", "업계 분류 설명"),
    "모트렉스 주식회사": ("제외", "휠가드 내장재 (목록 외)"),
    "아진전자부품(주)": ("제외", "업계 일반 설명"),
    "(주)디와이에이": ("제외", "알루미늄휠 사업 2015년 분할 이전"),
    "코리아에프티(주)": ("제외", "업계 일반 설명"),
    "(주)인팩": ("보류", "변속기 위치센서 (전장품, 품목 분류 애매)"),
    "(주)모토닉": ("보류", "변속기용 오일펌프 제어기 (전장품)"),
    "(주)유니크": ("보류", "변속기 제어 솔레노이드 밸브 (밸브류)"),
    "(주)스모트로닉": ("보류", "변속기 마운팅 브라켓 (목록 외 가능성)"),
}
WEAK_ITEMS = {"의료기기(일부)", "가스 분석기(일부)", "석재 가공기(일부)"}
ORDER = ["1차(2027)", "2차(2028)", "2차(2028, 제품명 확인)", "2차 후보(확인 필요)", "2차 후보-약", "비대상"]


def reviewed_group(r) -> str:
    g = r["wave_group_final"]
    if g == "2차(2028, 제품명 확인)":
        decision = REVIEW.get(r["corp_name"], ("미검토", ""))[0]
        if decision in ("제외", "보류"):
            return "2차 후보(확인 필요)"
        return g
    if g == "2차 후보(확인 필요)":
        items = {x for x in str(r.get("cbam_wave2_item", "")).split("/") if x and x != "nan"}
        if items and items <= WEAK_ITEMS:
            return "2차 후보-약"
    return g


def main():
    df = pd.read_csv(INTERIM / "mfg_final.csv", dtype=str)
    df["is_holding"] = df["is_holding"].str.lower().eq("true")
    df["review_decision"] = df["corp_name"].map(lambda n: REVIEW.get(n, ("", ""))[0])
    df["review_note"] = df["corp_name"].map(lambda n: REVIEW.get(n, ("", ""))[1])
    df["wave_group_reviewed"] = df.apply(reviewed_group, axis=1)
    df.to_csv(INTERIM / "mfg_final_reviewed.csv", index=False, encoding="utf-8-sig")

    up = df[df["wave_group_final"] == "2차(2028, 제품명 확인)"]
    print("===== 제품명 확인 37곳 검토 반영 =====")
    print(up["review_decision"].replace("", "미검토").value_counts().to_string())
    missing = up[up["review_decision"] == ""]
    if len(missing):
        print("  ! 검토표에 없는 회사 (이름 표기 확인 필요): " + ", ".join(missing["corp_name"]))

    mid = df[(df["size_class"] == "중견") & ~df["is_holding"]]
    print(f"\n===== 최종 파도 분포 (중견 {len(mid)}곳, 지주회사 제외) =====")
    print(mid["wave_group_reviewed"].value_counts().reindex(ORDER, fill_value=0).to_string())
    low = mid["wave_group_reviewed"].isin(ORDER[:3]).sum()
    high = low + (mid["wave_group_reviewed"] == "2차 후보(확인 필요)").sum()
    print(f"\n2028년까지 CBAM 대응 필요 중견: 최소 {low}곳 ~ 최대 {high}곳 "
          f"(중견의 {low/len(mid):.0%} ~ {high/len(mid):.0%})")
    print(f"  └ 연결이 약한 후보 {int((mid['wave_group_reviewed'] == '2차 후보-약').sum())}곳은 최대값에서 제외")

    rem = mid[mid["wave_group_reviewed"] == "2차 후보(확인 필요)"]
    print(f"\n===== 남은 2차 후보 {len(rem)}곳 업종코드 (중견만, 상위 15) =====")
    print(rem["induty_code"].value_counts().head(15).to_string())

    print("\n결과: data/interim/mfg_final_reviewed.csv")


if __name__ == "__main__":
    main()