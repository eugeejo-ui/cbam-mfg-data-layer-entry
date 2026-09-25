"""
05b_diagram.py  (4단계: 배경 도식)

그림 2. CBAM 적용 단계와 배출 데이터 연결 구조
  - 상단: 1차 적용 대상 → 2차 적용 예정 대상 → EU 수입업자로 이어지는 배출 데이터 흐름
  - 하단: 제조기업 내부 데이터 구조와 분석 대상(데이터 층)의 위치

출력  figures/fig2_cbam_data_flow.png
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "figures"

KOREAN_FONTS = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans CJK JP"]
C = {  # 그림 1과 같은 색 체계
    "w1": "#e6550d", "w1_bg": "#fdebdd",
    "w2": "#3182bd", "w2_bg": "#deebf7",
    "eu": "#636363", "eu_bg": "#f0f0f0",
    "data": "#e6550d", "data_bg": "#fff5eb",
    "text": "#252525", "sub": "#636363", "line": "#9e9e9e",
}


def pick_korean_font() -> str:
    available = {f.name for f in font_manager.fontManager.ttflist}
    return next((n for n in KOREAN_FONTS if n in available), "sans-serif")


def card(ax, x, y, w, h, title, lines, edge, face, title_size=12.5, badge=None, lw=2.0):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.018",
                                linewidth=lw, edgecolor=edge, facecolor=face, zorder=2))
    ax.text(x + 0.018, y + h - 0.035, title, fontsize=title_size, fontweight="bold",
            color=C["text"], va="top", zorder=4)
    if badge:
        ax.text(x + w - 0.015, y + h - 0.037, badge, fontsize=9, color="white", fontweight="bold",
                ha="right", va="top", zorder=5,
                bbox=dict(boxstyle="round,pad=0.35", facecolor=edge, edgecolor="none"))
    for i, (txt, style) in enumerate(lines):
        ax.text(x + 0.018, y + h - 0.095 - i * 0.042, txt, fontsize=10,
                color=C["sub"] if style == "sub" else C["text"],
                fontweight="bold" if style == "bold" else "normal", va="top", zorder=4)


def arrow(ax, p1, p2, color, label=None, label_xy=None, rad=0.0, lw=2.2, style="-|>", ls="-"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=16, linewidth=lw,
                                 color=color, linestyle=ls, connectionstyle=f"arc3,rad={rad}", zorder=1))
    if label:
        ax.text(*label_xy, label, fontsize=9.5, color=color, ha="center", va="center", fontweight="bold",
                zorder=6, bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="none"))


def main():
    sns.set_theme(style="white", font=pick_korean_font(), rc={"axes.unicode_minus": False})
    FIGURES.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(13, 7.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # ---------------- 상단: 배출 데이터 흐름
    ax.text(0.02, 0.965, "① 배출 데이터 흐름", fontsize=13, fontweight="bold", color=C["text"])
    top_y, top_h, w = 0.61, 0.29, 0.25
    xs = [0.02, 0.375, 0.73]
    card(ax, xs[0], top_y, w, top_h, "CBAM 1차 적용 대상",
         [("현행 대상 품목", "sub"),
          ("철강 · 알루미늄 · 시멘트 · 비료", "bold"),
          ("철강 구조물 · 탱크 · 볼트너트", "bold"),
          ("2026년 수입분 첫 신고: 2027-09-30", "sub")],
         C["w1"], C["w1_bg"], badge="2027")
    card(ax, xs[1], top_y, w, top_h, "CBAM 2차 적용 예정 대상",
         [("확대안 COM(2025) 989, 약 180개 품목", "sub"),
          ("자동차 부품 · 기계", "bold"),
          ("전기장비 · 가전 · 금속 가구", "bold"),
          ("2028-01-01 적용 예정 (확정 전)", "sub")],
         C["w2"], C["w2_bg"], badge="2028")
    card(ax, xs[2], top_y, w, top_h, "EU 수입업자",
         [("CBAM 법적 신고 의무자", "sub"),
          ("제품 내재 배출량 신고", "bold"),
          ("CBAM 인증서 구매·제출", "bold"),
          ("1차 적용 대상 직접 수출분 포함", "sub")],
         C["eu"], C["eu_bg"])

    mid = top_y + top_h / 2
    gap = xs[1] - (xs[0] + w)
    arrow(ax, (xs[0] + w + 0.008, mid), (xs[1] - 0.008, mid), C["w1"],
          "검증 배출\n데이터", (xs[0] + w + gap / 2, mid + 0.06))
    arrow(ax, (xs[1] + w + 0.008, mid), (xs[2] - 0.008, mid), C["w2"],
          "제품 내재\n배출량", (xs[1] + w + gap / 2, mid + 0.06))

    # 규칙 요약
    rule = ("연결 규칙 (EU 시행규칙 2025/2547 · 2025/2621)\n"
            "복합 제품 배출량 = 자기 공정 배출량 + 원재료 내재 배출량   |   "
            "외부 원재료는 공인 검증 보고서가 있어야 실제 값 인정, 없으면 기본값 적용   |   "
            "기본값 할증 2026년 10% → 2027년 20% → 2028년 이후 30%")
    ax.text(0.5, 0.515, rule, fontsize=9, color=C["text"], ha="center", va="center", linespacing=1.6,
            bbox=dict(boxstyle="round,pad=0.6", facecolor="#fafafa", edgecolor="#d9d9d9"))

    # ---------------- 하단: 제조기업 내부 데이터 구조
    ax.text(0.02, 0.395, "② 제조기업 내부 데이터 구조", fontsize=13, fontweight="bold", color=C["text"])
    ax.text(0.235, 0.397, "1·2차 적용 대상 기업 공통", fontsize=10, color=C["sub"])
    by, bh = 0.07, 0.27
    bw = [0.24, 0.36, 0.24]
    bx = [0.02, 0.33, 0.74]
    card(ax, bx[0], by, bw[0], bh, "원천 데이터",
         [("MES · ERP", "bold"), ("에너지 계측 · 공정 기록", "bold"), ("공급사 제출 배출 데이터", "bold")],
         C["eu"], "white", title_size=12)
    card(ax, bx[1], by, bw[1], bh, "데이터 층",
         [("데이터 통합: 공장·공급사 데이터 수집", "bold"),
          ("watsonx.data: 저장·조회", "bold"),
          ("데이터 인텔리전스: 출처·이력 추적", "bold"),
          ("검증 대응에 필요한 데이터 계보 관리", "sub")],
         C["data"], C["data_bg"], title_size=12, badge="분석 대상", lw=2.6)
    card(ax, bx[2], by, bw[2], bh, "계산·보고 도구",
         [("CBAM 전용 소프트웨어", "bold"), ("IBM Envizi 등", "bold"), ("배출량 산정·보고서 작성", "sub")],
         C["eu"], "white", title_size=12)
    bm = by + bh / 2
    arrow(ax, (bx[0] + bw[0] + 0.008, bm), (bx[1] - 0.008, bm), C["line"])
    arrow(ax, (bx[1] + bw[1] + 0.008, bm), (bx[2] - 0.008, bm), C["line"])

    fig.suptitle("CBAM 적용 단계와 배출 데이터 연결 구조", fontsize=15, fontweight="bold", y=0.995)
    fig.text(0.02, 0.012,
             "자료: EU 규정 2023/956, 시행규칙 2025/2547·2025/2621, 집행위원회 확대안 COM(2025) 989. "
             "데이터 층이 1·2차 적용 단계를 연결하는 경로가 된다는 판단은 규정 구조에서 도출한 가설임.",
             fontsize=8, color="#666666")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.94, bottom=0.04)
    out = FIGURES / "fig2_cbam_data_flow.png"
    fig.savefig(out, dpi=200)
    print(f"저장: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()