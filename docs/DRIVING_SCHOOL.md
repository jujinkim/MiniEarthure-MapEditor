# Driving School Town v6

[패키지](../examples/driving-school.memap) · [편집 원본](../examples/driving-school/) · [전체 지도](../examples/driving-school/overview.svg) · [고가 코스](../examples/driving-school/village-freeway.svg) · [손가락 코스](../examples/driving-school/village-finger.svg)

v6는 Q01 한빛 블록을 보존하면서 나머지 40개 블록을 상점가·주거·시장·오피스·호텔·광장의 용도별 배치로 바꾼 한국 샘플 맵이다.
전세계 지역/환경 테마 7종의 구현이 아니며, [세계 테마와 맵별 언어 저작 계획](WORLD_THEME_AUTHORING.md)은 별도로 남아 있다.
[현재 테마·자산·검증 경계](CITY_THEMES.md)와 [Q01 기준](SHOP_BLOCK.md)을 따른다. 기존 코스와 모든 출발점은 보존한다.

실제 크기 **576 × 192m**, 16m 셀 432개다. 서쪽 192m는 기존 주행 코스이며,
가운데 192m는 한국 도심, 동쪽 192m는 고층 업무 지구다. 커스텀 맵의 1m는 게임의 1m다.
이전 v2의 실제 표시 크기 768m를 각 축 1/4로 줄였고 도로는 이전 표시 폭의 두 배다.
작성 스크립트의 옛 좌표는 위치·높이 ÷32, 도로 폭 ÷4로 새 원본을 작성할 때 한 번 변환한다.
일반 커스텀 맵에 이 변환을 적용하지 않는다. OSM 가져오기 1:8은 별도 계약이다.

기존 도로 459개와 10개 코스의 연결을 유지한다. v5의 586개 도로에 Q03의 15개 골목과 연결 분할이 더해 총 622개다. 넓은 도로에 맞춰 급커브 반경, 연결부,
건물과 충돌 벽을 다시 배치했다. 일반 코스 경사는 최대 약7%, 카트 램프는 최대12%다.
높이 0.62m 고가와 시계탑 0.45m 통로를 포함한다. 차량 크기는 소비 앱이 결정한다.
2026-09-12 사용자 결정으로 기존 연습장과 도시의 나무를 **같은 `city-tree` 모델**로
통일했다. 높이 **3.25m**, 최대 수관 폭 **1.15m**이며 3단 잎·줄기·화단을 공유한다.
화단 65×24×65cm와 줄기 16×180×16cm에 충돌이 있고 잎에는 없다.
기존 나무 **1,226개**의 ID·수를 유지하며 옛 `compact-tree` 축소 모델은 활성 맵에서 사용하지 않는다.
원본 생성 위치는 `scripts/driving_school_vegetation_v2.json`에 있다. 도로·건물·기존 사물과
다른 나무를 피해 전체 수관에 최소 5cm 여유를 두고 재배치한다. 주변 16m에 공간이 없으면
기존 서쪽 192×192m 연습장 안에서 가장 가까운 안전한 후보를 사용한다.
현재 연습장 1,226개와 도시 237개, 총 1,463개가 모델 하나를 공유한다. 기존 연습장
배치 대비 1,224개가 이동했으며 이동 거리 중앙값은 10.948m, 최대는 40.827m다.
37개 식생 영역은 편집용 외곽선을 남기고 자동 생성 밀도를 0으로 설정해 중복을 막는다.
지형은 동일한 평지 PNG16이며 셀마다 5×5 표본, 실제 간격4m다.

| 출발 위치 | X / Y (실제 m) | 표면 |
| --- | --- | --- |
| 중앙 대로 | 93.75 / 50.68 | `central-spine-03` |
| 한국 도심 / 25개 블록 | 269.75 / 58.0 | `korea-ns-2-1` |
| 고층 업무 지구 / 16개 블록 | 477.75 / 66.0 | `sky-ns-2-1` |
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
이전 v3 원본과 패키지는 [v3](../examples/driving-school-v3/), [v3 패키지](../examples/driving-school-v3.memap), `tests/driving_school_v3.lock.json`으로 보존했다.
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

`tests/driving_school.lock.json`은 소스·패키지·432개 셀 해시를 고정한다.
`tests/driving_school_validator.gd`는 실제 Editor 열기·Save As·재열기·내보내기,
각 구역 바인딩과 시작점·램프 표면을 검사한다. 전체 코스 수동 주행과 Android
실기기 성능 수락은 후속 검증이다. 이 맵의 배치 변경은 로딩 최적화의 근거가 아니며,
시스템 개선 전후 측정에는 보존된 동일 v2 패키지를 사용한다.

## 도시 확장과 편집

`city_expansion.py`와 `city_assets.py`가 원본 배치와 MIT 정적 모델을 작성한다.
`compact_vegetation.py`도 같은 `city_assets.tree()`를 사용하여 구역별 모델·배율 차이를 막는다.
v4에서 41개 블록에 새 건물 164개, 한국 도심 3–6m / 업무 지구 8–16m 높이 변형,
상가 간판·창문·발코니·옥상 설비와 포디움/상층부 변형을 배치했다. 건물 대지의
점유율은 각 블록 65–80%였다. v5의 대표 블록은 4.1–7.6m 높이의 여섯 동과 60.9% 점유율이며 v6에도 보존된다.
v6는 총 197동, 블록당 3–6동과 용도별 골목·마당·광장으로 재배치한다. 현재 점유율과 형태는 [Q03 문서](CITY_THEMES.md)에 기록한다. 도시 지면은 포장 위주다.
가로수 화단, 벤치, 버스 정류장 16개, 가로등, 볼라드와 휴지통을 포함한다.
중앙 분리대가 있는 대로, 교차로 횡단보도·정지선, 연속 인도가 두 지구를 연결한다.
기존 출발 위치는 도시 위치만 옮겼고 고층 지구 출발을 추가해 총 16개다.

Recipe 6의 **Surface area** 도구는 지면 재질 폴리곤을 작성한다. 선택한 도로의
Authoring settings에서 차선 수·중앙선·가장자리 선·양 끝 횡단보도를 편집한다.
정확한 지오메트리, 이동·삭제·Undo/Redo·Save As·내보내기는 기존 원자적 검증을 따른다.
의도적으로 매설한 구조 도로는 지형 아래 그대로 둔다. 지면과 정확히 겹친
고가/교량 도로의 깜빡임·재질 가림은 공유 MapKit 생성기가 해결한다.

정점 공유 인덱스를 쓰는 GLB이며 모델·충돌·장식 수를 메모리 사유로 줄이지 않는다.
소스와 패키지 재현, 전체 432개 셀, 출발점/연결성, 대지 밀도, 기존 v3 보존,
Editor 열기/저장/재내보내기와 사용자 편집 경로를 검사한다. 소비 앱의 실제 주행·
512MiB 로딩 및 플랫폼 증거는 슈퍼프로젝트 도시 확장 보고서에 기록한다.

2026-09-12 나무 통일 검증: Python 회귀 12개(공유 모델 치수·충돌·기존 ID 및 전체
수관 간격 포함), MapKit 432개 셀 생성/소스 재패키징, Godot 4.7.2 편집기
열기·Save As·재열기·동일 패키지 내보내기 124개 확인을 통과했다.
도로·건물·출발점과 도시의 기존 배치는 동일하다. 현재 패키지 해시는
`81739d1ad619c34ce5b066dc11fae020b0e315f57cefbfa0a20548c87ebd5b92`이며,
이 집중 검증은 위의 전체 코스 수동 주행/Android 실기기 수락을 대신하지 않는다.
