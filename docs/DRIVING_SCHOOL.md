# Driving School Town v3

[패키지](../examples/driving-school.memap) · [편집 원본](../examples/driving-school/) · [전체 지도](../examples/driving-school/overview.svg) · [고가 코스](../examples/driving-school/village-freeway.svg) · [손가락 코스](../examples/driving-school/village-finger.svg)

실제 크기 **192 × 192m**, 16m 셀 144개다. 커스텀 맵의 1m는 게임의 1m다.
이전 v2의 실제 표시 크기 768m를 각 축 1/4로 줄였고 도로는 이전 표시 폭의 두 배다.
작성 스크립트의 옛 좌표는 위치·높이 ÷32, 도로 폭 ÷4로 새 원본을 작성할 때 한 번 변환한다.
일반 커스텀 맵에 이 변환을 적용하지 않는다. OSM 가져오기 1:8은 별도 계약이다.

도로 459개와 10개 코스의 연결을 유지한다. 넓은 도로에 맞춰 급커브 반경, 연결부,
건물과 충돌 벽을 다시 배치했다. 일반 코스 경사는 최대 약7%, 카트 램프는 최대12%다.
높이 0.62m 고가와 시계탑 0.45m 통로를 포함한다. 차량 크기는 소비 앱이 결정한다.
기존 나무 **1,226개**를 작은 정적 모델로 보존했다. 원본 생성 위치는
`scripts/driving_school_vegetation_v2.json`에 있으며 도로와 겹친 나무만 가까운 빈 공간으로 옮긴다.
37개 식생 영역은 편집용 외곽선을 남기고 자동 생성 밀도를 0으로 설정해 중복을 막는다.
지형은 동일한 평지 PNG16이며 셀마다 5×5 표본, 실제 간격4m다.

| 출발 위치 | X / Y (실제 m) | 표면 |
| --- | --- | --- |
| 중앙 대로 | 93.75 / 50.68 | `central-spine-03` |
| 신도시 / 100개 블록 | 137.5 / 50.18 | `city-ns-05-05` |
| 드라이빙 스쿨 마을 | 56.25 / 36.43 | `village-ns-04-02` |
| 출발 / 기능시험장 | 25.0 / 70.31 | `license-start` |
| 급코너와 시케인 | 53.12 / 75.49 | `technical-corners` |
| 연속 S자 | 58.15 / 96.08 | `double-s` |
| 원선회 패드 | 66.0 / 100.66 | `skidpad` |
| 62.5m 가속 직선 | 22.05 / 121.88 | `two-km-straight` |
| 6연속 180° 헤어핀 | 27.3 / 134.38 | `hairpin-straight-0` |
| 고가의 질주 / 출발 | 118.45 / 124.31 | `kart-freeway-start` |
| 고가의 질주 / 고가 직선 | 136.35 / 102.08 | `kart-freeway-highway-straight` |
| 고가의 질주 / 내리막 | 174.34 / 132.28 | `kart-freeway-descent` |
| 손가락 / 출발 | 134.38 / 177.12 | `kart-finger-start-a` |
| 손가락 / 원통형 안쪽 벽 | 170.05 / 175.0 | `kart-finger-tip-1` |
| 손가락 / 시계탑 | 120.62 / 165.12 | `kart-finger-clock-tower` |

정확한 높이·방향·코스 순서는 [driving.json](../examples/driving-school/driving.json)에 있다.
공식 시험장이나 원작 게임의 모델을 복제한 맵이 아닌 창작 연습장이다. 라이선스는 MIT다.
이전 원본과 패키지는 [v2](../examples/driving-school-v2/), [v2 패키지](../examples/driving-school-v2.memap)로 보존했다.
이전 치수·검증 기록은 [보관 문서](archive/2026-09-11-loading-units/DRIVING_SCHOOL.md)에 있다.

## 재생성과 검증

작성 도구의 선택 의존성은 Shapely 2.1.2다. MapKit/Editor 실행 시에는 필요 없다.
기존 출력은 덮어쓰지 않는다. MapEditor 저장소에서 실행한다.

```sh
rtk proxy python3 -m pip install shapely==2.1.2
rtk proxy python3 scripts/driving_school_map.py /new/town
rtk proxy addons/mapkit/target/debug/mapkit pack /new/town /new/town.memap
rtk proxy python3 scripts/check_driving_school.py --mapkit addons/mapkit/target/debug/mapkit --project /new/town --output /new/town-check
rtk proxy python3 -m unittest discover -s tests -p test_driving_school_map.py
```

`tests/driving_school.lock.json`은 소스·패키지·144개 셀 해시를 고정한다.
`tests/driving_school_validator.gd`는 실제 Editor 열기·Save As·재열기·내보내기,
각 구역 바인딩과 시작점·램프 표면을 검사한다. 전체 코스 수동 주행과 Android
실기기 성능 수락은 후속 검증이다. 이 맵의 배치 변경은 로딩 최적화의 근거가 아니며,
시스템 개선 전후 측정에는 보존된 동일 v2 패키지를 사용한다.
