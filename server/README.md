# LuxVerify Price API Server

크림(KREAM) + 번개장터 실시간 시세 스크래핑 서버

## Railway 배포 방법

### 1. 이 폴더를 GitHub에 올리기

```bash
# server/ 폴더 내용을 새 GitHub 레포지토리로
git init
git add .
git commit -m "init: LuxVerify price server"
git remote add origin https://github.com/YOUR_ID/luxverify-server.git
git push -u origin main
```

### 2. Railway 연결

1. https://railway.app 접속
2. **New Project** → **Deploy from GitHub repo**
3. 방금 만든 레포 선택
4. Railway가 Dockerfile 자동 감지 후 빌드 시작
5. 배포 완료 후 **Settings → Networking → Generate Domain** 클릭
6. 발급된 URL 복사 (예: `https://luxverify-server-production.up.railway.app`)

### 3. LuxVerify에 서버 URL 등록

발급된 URL을 LuxVerify 사이트의 **관리자 설정 → 시세 서버 URL** 에 입력

## API 엔드포인트

```
GET /api/price?q=샤넬+클래식+미디엄     # 크림+번개장터 동시
GET /api/kream?q=샤넬+클래식+미디엄     # 크림 단독
GET /api/bunjang?q=샤넬+클래식+미디엄   # 번개장터 단독
```

## 응답 예시

```json
{
  "keyword": "샤넬 클래식 미디엄",
  "kream": {
    "count": 12,
    "min": 3800000,
    "max": 5200000,
    "avg": 4300000,
    "mid": 4200000,
    "trimmed_avg": 4250000,
    "items": [...]
  },
  "bunjang": {
    "count": 8,
    "min": 3200000,
    "max": 4800000,
    "avg": 3900000,
    "mid": 3850000,
    "trimmed_avg": 3900000,
    "items": [...]
  }
}
```
