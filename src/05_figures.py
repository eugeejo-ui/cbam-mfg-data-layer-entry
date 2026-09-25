"""
05_figures.py  (4단계: 결과 그래프, seaborn)

그림 1. 그룹별 IT 예산 증가율 분포
  - IBM watsonx.data 온라인 버전(A)을 도입할 때 실측 IT 투자액이 몇 % 늘어나는지
  - 왼쪽: 최소 구성 (소형·업무시간, 지원비 상시) / 오른쪽: 상시 운영 구성 (중형·24시간)
  - 상자: 25~75% 구간, 가운데 선: 중앙값, 점: 개별 기업

입력  data/processed/cost_by_company.csv
출력  figures/fig1_it_increase_by_group.png
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib import font_manager
from matplotlib.ticker import FixedLocator, FixedFormatter, NullLocator

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"

KOREAN_FONTS = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans CJK JP"]
GROUPS = [  # 위에서 아래 순서로 그려짐
    ("중견-1차(2027)", "중견 · CBAM 1차 적용 대상\n(2027년 첫 신고)"),
    ("중견-2차(2028)", "중견 · CBAM 2차 적용 예정 대상\n(2028년 확대안)"),
    ("중견-2차 후보", "중견 · 2차 적용 후보"),
    ("중견-비대상", "중견 · CBAM 비대상\n(약한 연결 후보 포함)"),
    ("대기업", "대기업"),
]
PALETTE = {GROUPS[0][1]: "#e6550d", GROUPS[1][1]: "#3182bd", GROUPS[2][1]: "#6baed6",
           GROUPS[3][1]: "#9ecae1", GROUPS[4][1]: "#969696"}
PANELS = [
    ("소형·업무시간", "지원비 상시", "최소 구성\n소형 엔진 · 업무시간 가동 · 연 4,311만 원"),
    ("중형·상시", "지원비 상시", "상시 운영 구성\n중형 엔진 · 24시간 가동 · 연 1억 6,992만 원"),
]


def pick_korean_font() -> str:
    available = {f.name for f in font_manager.fontManager.ttflist}
    return next((n for n in KOREAN_FONTS if n in available), "sans-serif")


def main():
    sns.set_theme(style="whitegrid", context="notebook", font=pick_korean_font(),
                  rc={"axes.unicode_minus": False})
    FIGURES.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(PROCESSED / "cost_by_company.csv")
    label_map = dict(GROUPS)
    df = df[df["group"].isin(label_map)].copy()
    df["그룹"] = df["group"].map(label_map)
    df["IT 예산 증가율(%)"] = df["it_increase"] * 100
    order = [label for _, label in GROUPS]
    counts = df.drop_duplicates("stock_code").groupby("그룹").size().reindex(order).fillna(0).astype(int)

    fig, axes = plt.subplots(1, 2, figsize=(13, 6), sharey=True)
    for ax, (scen, sup, title) in zip(axes, PANELS):
        sub = df[(df["A_scenario"] == scen) & (df["support"] == sup)]
        sns.boxplot(data=sub, x="IT 예산 증가율(%)", y="그룹", hue="그룹", order=order, hue_order=order,
                    palette=PALETTE, showfliers=False, width=0.55, linewidth=1.2,
                    boxprops={"alpha": 0.55}, medianprops={"color": "black", "linewidth": 2},
                    legend=False, ax=ax, log_scale=True)
        sns.stripplot(data=sub, x="IT 예산 증가율(%)", y="그룹", hue="그룹", order=order, hue_order=order,
                      palette=PALETTE, size=3.2, alpha=0.75, jitter=0.18, legend=False, ax=ax)

        medians = sub.groupby("그룹")["IT 예산 증가율(%)"].median()
        for i, label in enumerate(order):
            if label in medians and pd.notna(medians[label]):
                ax.text(medians[label], i - 0.31, f"중앙값 {medians[label]:.1f}%", ha="center", va="bottom",
                        fontsize=9, fontweight="bold", color="#222222")

        ticks = [0.01, 0.1, 1, 10, 100]
        ax.set_xlim(0.01, 200)
        ax.xaxis.set_major_locator(FixedLocator(ticks))
        ax.xaxis.set_major_formatter(FixedFormatter([f"{t:g}%" for t in ticks]))
        ax.xaxis.set_minor_locator(NullLocator())
        ax.set_title(title, fontsize=11.5, pad=10)
        ax.set_xlabel("IT 예산 증가율 (온라인 버전 연간 비용 ÷ 정보기술부문 투자액, 로그 척도)", fontsize=10)
        ax.set_ylabel("")

    axes[0].set_yticks(range(len(order)))
    axes[0].set_yticklabels([f"{label}\n(n={counts[label]})" for label in order])
    sns.despine(fig=fig, left=True)

    fig.suptitle("IBM watsonx.data 온라인 버전 도입 시 IT 예산 증가율\nCBAM 1차 적용 대상 중견 기업의 증가율이 가장 높음",
                 fontsize=13.5, fontweight="bold", y=0.99)
    fig.text(0.01, 0.035,
             "주: 정가 기준, 저장소 비용 제외, 1달러 = 1,366원 적용. 정보기술부문 투자액을 공시한 기업에 한정함. "
             "상자는 25~75% 구간, 굵은 선은 중앙값, 점은 개별 기업을 나타냄.",
             fontsize=8, color="#666666")
    fig.text(0.01, 0.01,
             "자료: 금융감독원 전자공시(매출·업종), 공정거래위원회 기업집단포털(기업집단), "
             "한국인터넷진흥원 정보보호 공시(정보기술부문 투자액, 2025년 실적), IBM watsonx.data 가격 페이지(2026년 9월)",
             fontsize=8, color="#666666")
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    out = FIGURES / "fig1_it_increase_by_group.png"
    fig.savefig(out, dpi=200)
    print(f"저장: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()