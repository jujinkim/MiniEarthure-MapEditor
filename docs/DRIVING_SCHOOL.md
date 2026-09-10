# Driving School Town

바로 사용할 패키지: [driving-school.memap](../examples/driving-school.memap).

편집 원본: [driving-school/](../examples/driving-school/).

전체 지도: [overview.svg](../examples/driving-school/overview.svg).

코스 상세: [고가의 질주](../examples/driving-school/village-freeway.svg) · [손가락](../examples/driving-school/village-finger.svg).

이 원본과 검증된 `.memap`은 프로젝트의 Git 관리 콘텐츠다. MiniEarthure 게임은 동일한
패키지를 기본 맵으로 포함하며, Client의 동기화 검사에서 원본·패키지 lock과 배포 사본의
바이트 일치를 확인한다. 이 저장소의 원본·생성기·Editor는 게임 저장소 없이 사용할 수 있다.

`driving-school-town-v2`은 6,144 × 6,144m, 144셀의 가상 드라이빙 스쿨 겸 도시다.
기존 G01 회귀 맵은 그대로 유지한다. 도로 중심선 총연장은 약 162.1km이며,
모든 구역이 하나의 명시적 도로 그래프로 연결된다. 좌표와 거리는 원본 지도 기준이고
실제 표시는 MapKit의 기존 1:8 축척을 따른다.

| 구역 | 구성 | 추천 시작 X / Y (m) | 표면 ID |
| --- | --- | --- | --- |
| 기능시험 연습장 | 2m 경사로·정지 구간·T자/평행주차·직각·S자·가속·복귀로 | **800 / 2250** | `license-start` |
| 테크니컬 | 급직각 코너·더블 시케인 | 1700 / 2400 | `technical-corners` |
| 더블 S | 470m 구간, 좌우 100m 진폭, 별도 복귀로 | 1800 / 3050 | `double-s` |
| 원선회 | 반경 170m, 폭 20m | 2080 / 3320 | `skidpad` |
| 가속·제동 | 2km 직선, 100m 간격 노변 표식, 별도 복귀로 | 650 / 3900 | `two-km-straight` |
| 헤어핀 | 반경 90m의 180° 회전 6개, 폭 12m, 긴 탈출 직선 | 850 / 4300 | `hairpin-straight-0` |
| 신도시 | 2.2 × 2.2km, 100블록, 건물 372개, 공원·교차로·20m 도로 | 4400 / 1550 | `city-ns-05-05` |
| 마을 | 주택 88채, 정원·공원·생활 도로 | 1800 / 1150 | `village-ns-04-02` |
| 고가의 질주 출발 | 원형 코너·램프·고가 직선·U턴·내리막·마지막 Z자 | 3750 / 4030 | `kart-freeway-start` |
| 고가 직선 | 높이 20m, 직선 650m, 폭 20m | 4200 / 3330 | `kart-freeway-highway-straight` |
| 고가 내리막 | 6.25% 경사·연속 감속 코너 | 5540 / 4240 | `kart-freeway-descent` |
| 손가락 출발 | 길이가 다른 네 손가락, 7연속 U턴, 두 지름길 | 4300 / 5540 | `kart-finger-start-a` |
| 손가락 급커브 | 반경 45m, 안쪽 원통형 벽, 폭 16m | 5415 / 5495 | `kart-finger-tip-1` |
| 손가락 시계탑 | 4m 교량 두 개와 폭 10m 통로, 옆의 원형 엄지 구간 | 3860 / 5290 | `kart-finger-clock-tower` |

첫 출발은 기능시험장의 **(800, 2250), `license-start`**를 사용한다. 기본 차량 방향은
지도 Y 증가 방향이므로 바로 앞으로 출발할 수 있다. 직선과 헤어핀은 동쪽으로 향한다.
정확한 좌표·권장 방향·10개 순환 코스의 도로 순서는
[driving.json](../examples/driving-school/driving.json)에 있다.

기능시험장은 **한국식 기능 연습을 위한 창작 배치**다. 공식 시험장의 정확한 치수·동선
복제나 자동 채점·신호 제어는 포함하지 않는다. 경사로 정지 구간과 주차 구간은 밝은
콘크리트 포장으로 구분한다. 교통 AI, 차량/카트 선택, 경기 규칙은 소비 앱의 기능이다.

카트 구역은 **카트라이더의 빌리지 고가의 질주와 빌리지 손가락** 원본 미니맵의
형태·진행 순서를 참고해 새로 만든 코스다. [고가의 질주 자료](https://kartrider.fandom.com/zh/wiki/城镇_高速公路)와
[손가락 자료](https://kartrider.fandom.com/zh/wiki/城镇_手指)의 원본 이미지를 확인했다.
고가 코스의 긴 위쪽 직선·굴곡·하강·끝 Z자, 손가락 코스의 4개 돌출부·7개 U턴·두 지름길·엄지 원형 구간을 반영했다.
원작의 정확한 치수·그래픽 복제가 아니며, 도로 폭과 경사는 이 게임의 주행 축척에 맞춰 조정했다.
원작 모델·텍스처·음악은 패키지에 포함하지 않는다.

두 코스에 **충돌 벽 133구간과 원통형 벽 10개**가 있다. 직선과 곡선 벽은 이어지는
다각형으로 만들고, 분리된 구간 이음 간격은 약 16cm다. 진입로·지름길·시계탑 입구에는
의도적인 개구부가 있다. 원통형 벽은 48면의 단단한 프리즘이며 표시와 충돌의 경계가 같다.
기존 8자 코스와 패키지는 [driving-school-v1](../examples/driving-school-v1/) 및
[driving-school-v1.memap](../examples/driving-school-v1.memap)으로 보존했다.

### 에디터에서 원통형 벽 만들기

1. **Authoring settings → Drawing**에서 `Cylinder wall radius`, `Cylinder wall height`를 설정한다.
   바닥 높이는 `Building / placement base`, 재질은 `Building material`을 사용한다.
2. **Cylinder wall** 도구로 캔버스의 중심을 한 번 클릭한다. 커서에 반지름이 미리 표시된다.
3. 선택 후 **Authoring settings → Selected**에서 중심·반지름·바닥·높이를 수정한다.
   이동·회전·복제·Undo/Redo·Save As·패키지 내보내기를 지원한다.

MapKit이 이미 지원하는 평평한 다각형 프리즘을 사용하므로 recipe 3 이상에서 사용할 수 있고
새 패키지 버전이나 Runtime 물리 변경이 필요 없다. 저장된 정수 꼭짓점이 원본이며,
임의 다각형으로 바꾼 뒤에는 일반 꼭짓점 편집을 사용한다. 잠긴 레이어, 맵 경계 밖,
도로와의 겹침은 기존 검증으로 거부된다.

지형은 외부 데이터가 없는 완전한 평지 PNG16이며, 128m 격자는 조밀한 곡선에서 생성기의
지형 분할 작업량을 제한하기 위한 것이다. 도시 도로에는 자동 보도를 생성하지 않는다.

## 재생성과 검사

공개 MIT 소스·원본 정적 모델만 사용하며 게임 저장소나 외부 다운로드가 필요 없다.
기존 출력 경로는 덮어쓰지 않는다. 아래 명령은 MapEditor 저장소 기준이다.

```sh
rtk cargo build --locked --manifest-path addons/mapkit/Cargo.toml -p mapkit-cli
rtk proxy python3 -B scripts/driving_school_map.py /new/driving-school
rtk proxy addons/mapkit/target/debug/mapkit pack /new/driving-school /new/driving-school.memap
rtk proxy python3 -B scripts/check_driving_school.py --mapkit addons/mapkit/target/debug/mapkit --output /new/school-checks
rtk proxy python3 -B -m unittest discover -s tests -p 'test_driving*map.py' -v
rtk proxy env MAPEDITOR_SCHOOL_ROOT=/absolute/driving-school MAPEDITOR_SCHOOL_REPORT=/new/editor-report.json python3 -B scripts/check_documents.py --godot /path/to/godot --script driving_school_validator --script cylinder_wall_validator --script authoring_safety_validator --log-dir /new/editor-checks
```

`check_driving_school.py` 재현 내보내기는 배포된 패키지와 바이트 해시까지 비교하고,
144개 셀을 모두 생성하여 각 해시를 보존한다. `driving_school_validator.gd`는 실제
Editor 열기·Save As·재열기·내보내기와 각 구역의 바인딩 생성, 표면별 높이를 확인한다.
`tests/driving_school.lock.json`은 배포된 소스·패키지·생성 셀을 고정한다.

2026-09-11 검증은 새 코스의 결정적 패키지/셀 생성, Editor 저장·내보내기,
원통형 벽의 생성·크기 수정·실행 취소·저장 후 재편집 및 네 셀에 걸친 충돌 형상,
실제 Client에서의 벽 충돌·등판·고가 직선·하강·손가락/시계탑 주행을 대상으로 한다.
상세 결과는 슈퍼프로젝트의 `docs/validation/village-courses-macos-2026-09-11/`에 기록한다.
개발 debug 빌드의 구역 준비는 수십 초가 걸리므로 준비 완료 후 출발한다.

지도 구현과 결정적 생성 검증은 전체 코스 수동 주행, Windows/Linux/Android 성능 및
프로젝트 최종 수락과 별개의 상태로 관리한다. 이 예제는 지도 제작 결과이며 제품 전환이나
최종 플랫폼 수락 완료를 뜻하지 않는다.
