# 자유주행형 맵

현재 v1 문서의 필수 boolean `free_roam`을 문서 속성의 **자유주행형 맵**
체크박스로 편집한다. 설명은 “완주 후 결과 연출을 표시하고 자유주행으로
돌아갑니다”이다. 새 수동 문서와 Seed Track은 false, 외부 GeoJSON/OSM/PBF와
PNG/DEM 지도·지형 가져오기 성공 시 true이다. 가져오기 검토/취소/실패는
원본 문서를 바꾸지 않는다. 모델·텍스처 추가와 네이티브 문서 열기는 값을 유지한다.

일반 명령 이력에 포함되어 Undo/Redo·복구·Save As로 보존된다. 가져온 지형과
정책 변경도 같은 원자적 이력이다. MapKit의 일반/지역 패키지 계약과 콘텐츠
해시에 포함된다. 생성 트랙의 정책 편집은 MapKit `reseal_track_document`로
검증한 뒤 코스 해시와 함께 변경한다. 다른 소스/코스 위조를 허용하지 않는다.
Seed 편도 마지막의 도착 광장과 복구 기준점은 MapKit이 제공한다.

`examples/race-flow/`는 기본 게임 맵 7개와 합성 물리 맵의 현재 소스 스냅샷이다.
기존 예제, 생성물, 사용자 파일은 그대로 보존했다. 이전 문서를 자동으로
변환하거나 현재 읽기에 누락 필드 기본값을 추가하지 않았다. 모든 형식은 v1이다.

집중 검사: generated policy/hash Undo/Redo, save/reopen/recovery,
document history, GeoJSON 원자적 명령, 높이맵 가져오기, asset policy 보존을
통과했다. [검증 기록](validation/race-flow-2026-09-28/README.md)을 참조한다.
수동 편집·전체 DEM/OSM 데이터 수락·실주행은 사용자 확인이며 이번 검사의
통과로 간주하지 않는다.
