# 진행 현황

- 프로젝트명: cbam-mfg-data-layer-entry
- 목표 완료일: 2026-09-27

## 개요
- 국내 중견 제조기업의 데이터 층(IBM watsonx.data) 진입 비용을 실제 IT 예산 대비 부담 수준으로 산출함
- 2027~2028년 EU CBAM 적용 단계에 따라 데이터 대응이 필요한 기업군과 시점을 구분함

## 단계별 상태

| 단계 | 내용 | 상태 | 문서 |
|---|---|---|---|
| 0 | 방향 설정·설계 | 완료 (09-25) | [step0_planning.md](step0_planning.md) |
| 1 | 데이터 수집 (전자공시, 공정위, 배출권) | 완료 (09-25) | [step1_data_collection.md](step1_data_collection.md) |
| 2 | 규모 판정 및 CBAM 적용 단계 구분 | 완료 (09-25) | [step2_classification.md](step2_classification.md) |
| 3 | 진입 비용 계산 (정보기술부문 투자액 기준) | 완료 (09-25) | [step3_cost_model.md](step3_cost_model.md) |
| 4 | 그래프·도식 및 README 작성 | 완료 (09-26) | [../../README.md](../../README.md) |
| 5 | 수치 대조(149개 항목 일치) 및 레포 공개 | 완료 (09-26) | [../../src/06_verify_numbers.py](../../src/06_verify_numbers.py) |

## 주요 수치
- 제조업 상장사 1,610곳 중 중견 기업 645곳 (지주회사형 제외)
- 2028년까지 CBAM 대응이 필요한 중견 기업: 최소 94곳(15%) ~ 최대 189곳(29%)
- CBAM 1차 적용 대상 58곳 중 사업보고서 CBAM 언급 5곳, 데이터·시스템 대응 기재 1곳
- 정보기술부문 투자액 중앙값: 대기업 204.5억 원, 중견 기업 28.6억 원, 1차 적용 대상 중견 기업 14.3억 원
- IBM 온라인 버전 도입 시 IT 예산 증가율(중앙값): 대기업 0.2~0.8%, 1차 적용 대상 중견 기업 3.0~11.9%
- 1차 적용 대상 중견 기업 상위 25%는 상시 운영 구성 시 IT 예산 28.9% 이상 증가 필요

## 산출물
- 그림 1: `figures/fig1_it_increase_by_group.png` (그룹별 IT 예산 증가율 분포)
- 그림 2: `figures/fig2_cbam_data_flow.png` (CBAM 적용 단계와 배출 데이터 연결 구조)
- 최종 결과: `data/processed/cost_by_company.csv`, `data/processed/cost_summary.csv`
- 수치 대조: `src/06_verify_numbers.py` 실행 결과 149개 항목 일치, 불일치 0건

## 향후 과제
- EU 의료기기 데이터베이스(EUDAMED) 의무화를 의료기기 업종의 의무형 데이터 수요 사례로 추가 검토
- Azure 기반 watsonx.data SaaS의 서울 리전 제공 여부 확인