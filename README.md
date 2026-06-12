# Stock Discovery GPT Backend

개인용 주식 발굴 GPT를 위한 FastAPI 백엔드 MVP입니다. 이 저장소는 자동 매매 봇이 아니며, 매수/매도 주문을 생성하지 않습니다. 목표는 NASDAQ, KOSPI, KOSDAQ 등 다양한 시장의 종목 데이터를 수집하고 정규화한 뒤, 재무/밸류에이션/리스크/스코어링 지표를 계산하여 Custom GPT Action에서 사용할 수 있는 안정적인 API를 제공하는 것입니다.

## 프로젝트 목적

- 미국 주식은 FMP(Financial Modeling Prep), 한국 주식은 DART 및 KRX 관련 데이터 소스를 연결합니다.
- 원천 데이터를 도메인 모델로 정규화하고, 결정론적인 스코어링 로직으로 후보 종목을 평가합니다.
- GPT가 조건부 투자 분석, 리스크 점검, 점수 설명, 후보 랭킹을 수행할 수 있도록 구조화된 응답을 제공합니다.
- 이 프로젝트는 리서치 및 스크리닝 도구이며, 자동 주문 또는 직접적인 거래 실행 기능을 포함하지 않습니다.

## 아키텍처

```text
app/
  main.py                  # FastAPI 앱 생성 및 라우터 등록
  core/                    # 설정 및 보안
  models/                  # Pydantic v2 응답/요청 모델
  services/                # API 클라이언트, 정규화, 지표 계산, 스코어링, 스크리닝
  api/routes/              # HTTP 엔드포인트

tests/                     # pytest 테스트
```

핵심 설계 원칙은 다음과 같습니다.

- 외부 API 클라이언트와 정규화 모델을 분리합니다.
- 재무 계산 및 스코어링은 결정론적으로 유지하여 테스트 가능하게 만듭니다.
- API 키와 Action 인증 토큰은 환경 변수에서만 로드합니다.
- 현재 MVP는 mock 데이터를 사용하지만, 응답 스키마는 추후 FMP/DART 데이터로 교체할 수 있도록 설계했습니다.

## 로컬 설정

Python 3.11 이상을 사용합니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

서버 실행:

```bash
uvicorn app.main:app --reload
```

API 문서 확인:

- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>

## 환경 변수

`.env.example`을 복사하여 `.env`를 만들고 값을 채웁니다. `/score/{market}/{ticker}`는 `STOCK_DATA_GATEWAY_URL`의 gateway를 통해 미국 FMP snapshot 또는 한국 DART/KRX 데이터를 조회합니다. gateway가 없거나 상세 데이터가 부족하면 기존 응답 스키마를 유지한 partial fallback을 반환합니다.

| 변수 | 설명 |
| --- | --- |
| `STOCK_DATA_GATEWAY_URL` | `/score/{market}/{ticker}`가 호출하는 데이터 게이트웨이 URL. 미설정 시 `https://stock-data-gateway.onrender.com`을 사용합니다. |
| `STOCK_DATA_GATEWAY_BEARER_TOKEN` | stock-discovery-gpt가 stock-data-gateway를 호출할 때 `Authorization: Bearer ...` 헤더에 사용하는 토큰 |
| `FMP_API_KEY` | 기존 직접 FMP 클라이언트를 사용하는 서비스용 선택 설정. `/score`는 게이트웨이를 통해 FMP 데이터를 조회합니다. |
| `DART_API_KEY` | 기존 직접 DART 클라이언트를 사용하는 서비스용 선택 설정. `/score`는 게이트웨이를 통해 DART/KRX 데이터를 조회합니다. |
| `ACTION_API_BEARER_TOKEN` | Custom GPT Action 호출 보호용 Bearer 토큰 |
| `ENVIRONMENT` | 실행 환경. 기본값은 `development` |

보안상 `.env` 파일은 Git에 커밋하지 않습니다.

## FMP 미국 주식 데이터 설정

기존 직접 FMP 클라이언트는 `FMP_API_KEY`가 있을 때 Financial Modeling Prep API를 사용합니다. `/score`의 미국 상장 종목(`NASDAQ`, `NYSE`, `AMEX`) 요청은 API 키를 scoring backend에 노출하지 않고 stock-data-gateway의 `/v1/market-snapshot`을 사용합니다. 현재 연동되는 FMP 엔드포인트는 다음과 같습니다.

- `profile/{ticker}`
- `income-statement/{ticker}`
- `balance-sheet-statement/{ticker}`
- `cash-flow-statement/{ticker}`
- `key-metrics/{ticker}`
- `ratios/{ticker}`
- `quote/{ticker}`

하나의 FMP 엔드포인트가 실패해도 전체 응답은 중단되지 않습니다. 가능한 데이터로 내부 스키마를 채우고, 실패한 엔드포인트는 `data_basis.notes`에 기록하며 `data_basis.reliability`를 낮춥니다. `FMP_API_KEY`가 없으면 기존 mock 응답을 반환하므로 로컬 개발 중 API 키를 요구하지 않습니다.

## DART 한국 주식 데이터 설정

기존 직접 DART 클라이언트는 `DART_API_KEY`가 있을 때 OpenDART API를 사용합니다. `/score`의 한국 상장 종목(`KOSPI`, `KOSDAQ`) 요청은 stock-data-gateway의 `/kr/resolve`, `/kr/dart/company`, `/kr/dart/disclosures`를 필요한 범위에서 사용합니다. 티커는 `005930`, `083450`처럼 6자리 종목코드를 입력합니다. 현재 연동되는 DART 엔드포인트는 다음과 같습니다.

- `corpCode.xml`
- `company.json`
- `fnlttSinglAcnt.json`
- `list.json`

`corpCode.xml`에서 내려받은 고유번호 매핑은 요청마다 다시 다운로드하지 않도록 프로세스 메모리에 캐시합니다. 하나의 DART 엔드포인트가 실패해도 가능한 데이터로 내부 스키마를 채우고, 실패한 엔드포인트는 `data_basis.notes`에 기록하며 `data_basis.reliability`를 낮춥니다. 최근 공시명에서 유상증자, 전환사채, 신주인수권부사채, 감사의견 이슈, 거래정지 관련 내용, 최대주주 변경을 탐지해 `risk_flags`에 반영합니다. `DART_API_KEY`가 없으면 기존 mock 응답을 반환합니다.

## API 엔드포인트

### `GET /`

Render 및 브라우저 확인용 공개 루트 엔드포인트입니다. 앱 이름, 상태, 환경, `/health`, `/openapi.json`, `/docs` 경로를 반환합니다.

### `GET /health`

서비스 상태, 앱 이름, 실행 환경을 반환합니다.

### `POST /score/{market}/{ticker}`

단일 종목에 대한 스코어 응답을 반환합니다. 미국 시장은 gateway의 `/v1/market-snapshot`을 호출하고, 한국 시장은 필요할 때 `/kr/resolve`로 종목 코드를 확인한 뒤 `/kr/dart/company`와 `/kr/dart/disclosures`를 호출합니다. gateway 장애나 상세 재무 데이터 누락 시 값을 만들어내지 않고 partial result와 낮아진 데이터 신뢰도를 반환합니다.

- `market`: `NASDAQ`, `NYSE`, `AMEX`, `KOSPI`, `KOSDAQ`
- `ticker`: 미국 티커 또는 한국 종목 코드

응답에는 `company`, `data_basis`, `metrics`, `valuation`, `scores`, `risk_flags`, `hard_fail`, `final_label`이 포함됩니다.

### `POST /screen`

시장, 최소 시가총액, 최소 총점, 반환 개수를 입력받아 mock 후보 리스트를 총점 내림차순으로 반환합니다.

### `GET /candidates/top`

선택적 시장 필터와 limit을 받아 mock 상위 후보를 반환합니다.

## 데이터 게이트웨이 아키텍처

```text
Custom GPT
→ stock-discovery-gpt
→ stock-data-gateway
→ FMP / DART / KRX
```

`stock-data-gateway`는 외부 공급자의 raw data collection layer이며, 이 서비스는 정규화된 데이터를 사용해 scoring과 candidate ranking을 수행합니다. `STOCK_DATA_GATEWAY_URL`의 기본값은 `https://stock-data-gateway.onrender.com`입니다.

`/score/{market}/{ticker}` 테스트 예시:

```bash
curl -X POST https://<your-render-service>.onrender.com/score/NASDAQ/AAPL \
  -H "Authorization: Bearer <ACTION_API_BEARER_TOKEN>"

curl -X POST https://<your-render-service>.onrender.com/score/KOSPI/005930 \
  -H "Authorization: Bearer <ACTION_API_BEARER_TOKEN>"
```

게이트웨이가 일시적으로 응답하지 않거나 상세 재무 데이터가 없으면 API는 기존 응답 스키마를 유지한 partial result를 반환하고, `data_basis.reliability`와 `risk_flags`로 데이터 한계를 표시합니다.

## Screening 결과 해석

`screenStocks`와 `getTopCandidates`의 `market_cap` 및 `min_market_cap`은 상장 시장의 통화를 기준으로 해석합니다. 통화 변환은 자동으로 수행하지 않습니다.

- `NASDAQ`, `NYSE`, `AMEX`: `market_cap`과 `min_market_cap` 단위는 **USD**입니다.
- `KOSPI`, `KOSDAQ`: `market_cap`과 `min_market_cap` 단위는 **KRW**입니다.
- 시가총액을 확인할 수 없으면 `market_cap=null`로 반환합니다. `min_market_cap=0`이면 해당 후보를 자동 제외하지 않지만, 양수 필터는 확인 가능한 시가총액을 요구하므로 제외합니다.

후보 응답 메타데이터는 다음과 같이 해석합니다.

- `is_mock`: 실제 공급자 데이터가 아닌 mock/fallback 후보이면 `true`입니다.
- `data_reliability`: `0`에서 `1` 사이의 수치 신뢰도입니다. `0.5` 미만인 후보는 `elite_candidate`가 될 수 없습니다.
- `data_reliability_label`: 사람이 읽기 쉬운 신뢰도 등급입니다. fallback 후보는 `low`입니다.
- `data_source`: 후보 데이터의 출처입니다.
- `market_cap_unit`: 후보 시가총액의 통화 단위인 `USD` 또는 `KRW`입니다.
- `risk_flags`: `mock_data_used`, `partial_gateway_data`, `gateway_unavailable`, `dart_data_unavailable` 등 데이터 한계와 리스크를 표시합니다.
- `notes`: 오류 세부정보나 내부 URL을 노출하지 않는 안전한 설명입니다.

mock/fallback 후보는 시장 발굴 흐름을 중단하지 않기 위한 참고 결과입니다. 실제 데이터로 오해하지 말고 현재 시세와 재무 데이터를 별도로 확인해야 합니다.

### `screenStocks` 사용 예시

```bash
curl -X POST https://<your-render-service>.onrender.com/screen \
  -H "Authorization: Bearer <ACTION_API_BEARER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"market":"KOSPI","min_market_cap":0,"min_total_score":60,"limit":10}'
```

### `getTopCandidates` 사용 예시

```bash
curl "https://<your-render-service>.onrender.com/candidates/top?market=NASDAQ&limit=5" \
  -H "Authorization: Bearer <ACTION_API_BEARER_TOKEN>"
```

게이트웨이 또는 공급자 오류가 발생하면 endpoint는 crash 대신 빈 목록 또는 명시적으로 표시된 fallback 후보를 반환합니다. fallback 후보의 `risk_flags`와 `notes`에는 민감정보 없이 안전한 상태만 기록됩니다.

## Custom GPT Actions 연결 방식

1. FastAPI 앱을 배포하고 HTTPS 엔드포인트를 준비합니다.
2. `/openapi.json` 스키마를 Custom GPT Action에 등록합니다.
3. 필요한 경우 `ACTION_API_BEARER_TOKEN`을 설정하고 GPT Action 인증 설정에 같은 Bearer 토큰을 입력합니다.
4. GPT는 `/score/{market}/{ticker}`, `/screen`, `/candidates/top` 응답을 기반으로 종목 점수, 리스크 플래그, 후보 랭킹을 설명합니다.

## 개발 로드맵

- **Phase 1: single-stock scoring**  
  단일 종목 mock 스코어링, 응답 스키마, 기본 테스트 구축
- **Phase 2: FMP integration**  
  미국 주식 프로필, 재무제표, 밸류에이션 데이터 연동
- **Phase 3: DART integration**  
  한국 공시 및 재무 데이터 연동, 한국 시장 종목 코드 처리
- **Phase 4: market screener**  
  NASDAQ/KOSPI/KOSDAQ 후보군 스크리닝 및 정렬 로직 강화
- **Phase 5: GPT analysis integration**  
  Custom GPT Action 연결, 조건부 투자 분석 프롬프트와 리스크 설명 고도화

## 테스트

```bash
pytest
```

정적 검사:

```bash
ruff check .
```

## Render 배포 가이드

이 저장소에는 Render Blueprint 배포에 사용할 수 있는 `render.yaml`이 포함되어 있습니다. Render가 `render.yaml`을 감지하면 아래 설정을 기본값으로 사용할 수 있습니다.

### Build Command

```bash
pip install -e .
```

`pyproject.toml`에 런타임 의존성이 정의되어 있으므로 별도 `requirements.txt` 없이 설치할 수 있습니다. 로컬 개발이나 테스트 의존성이 필요하면 `pip install -e '.[dev]'`를 사용합니다.

### Start Command

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Render는 `PORT` 환경 변수를 자동으로 주입합니다. 위 명령은 외부 요청을 받을 수 있도록 `0.0.0.0`에 바인딩하고 Render가 지정한 포트를 사용합니다.

### Health Check Path

```text
/health
```

### 배포 단계

1. GitHub 저장소를 Render에 연결합니다.
2. **New Web Service** 또는 Blueprint 배포를 선택합니다.
3. Runtime은 Python 3.11 이상을 사용합니다.
4. Build Command와 Start Command가 위 값과 일치하는지 확인합니다.
5. **Environment** 탭에 `STOCK_DATA_GATEWAY_URL`과 `STOCK_DATA_GATEWAY_BEARER_TOKEN`을 설정합니다.
6. Health Check Path를 `/health`로 설정합니다.
7. 배포 후 다음 URL이 정상 응답하는지 확인합니다.

- `https://<your-render-service>.onrender.com/`
- `https://<your-render-service>.onrender.com/health`
- `https://<your-render-service>.onrender.com/openapi.json`

## Render 환경 변수 설정

Render 대시보드의 **Environment** 탭에서 다음 값을 설정합니다.

| 변수 | 필수 여부 | 설명 |
| --- | --- | --- |
| `ENVIRONMENT` | 권장 | `production` 등 배포 환경 이름 |
| `STOCK_DATA_GATEWAY_URL` | 권장 | raw data gateway URL. 기본값은 `https://stock-data-gateway.onrender.com` |
| `STOCK_DATA_GATEWAY_BEARER_TOKEN` | 필수 | stock-data-gateway 요청의 Bearer 인증에 사용할 토큰 |
| `FMP_API_KEY` | 선택 | 기존 직접 FMP client용 키. gateway 연동 `/score`에서는 사용하지 않음 |
| `DART_API_KEY` | 선택 | 기존 직접 DART client용 키. gateway 연동 `/score`에서는 사용하지 않음 |
| `ACTION_API_BEARER_TOKEN` | 권장 | Custom GPT Actions에서 보호 엔드포인트 호출 시 사용할 Bearer 토큰 |
| `PORT` | Render 자동 설정 | Render가 자동 주입합니다. 직접 설정하지 않아도 됩니다. |

`ACTION_API_BEARER_TOKEN`을 설정하면 `/score/{market}/{ticker}`, `/screen`, `/candidates/top` 호출에는 `Authorization: Bearer <token>` 헤더가 필요합니다. `/health`는 배포 상태 확인을 위해 공개 엔드포인트로 유지됩니다.

## Render 배포 체크리스트

- [ ] `render.yaml` 또는 Render 대시보드의 Build Command가 `pip install -e .`인지 확인
- [ ] Start Command가 `uvicorn app.main:app --host 0.0.0.0 --port $PORT`인지 확인
- [ ] Health Check Path가 `/health`인지 확인
- [ ] `ENVIRONMENT=production` 설정
- [ ] 필요한 경우 `FMP_API_KEY`, `DART_API_KEY` 설정
- [ ] Custom GPT Actions를 사용할 경우 `ACTION_API_BEARER_TOKEN` 설정
- [ ] 실제 API 키를 코드, README, 커밋 메시지에 포함하지 않기
- [ ] 배포 후 `/`, `/health`, `/openapi.json` 응답 확인

## Custom GPT Actions 연결

1. 배포된 서버의 OpenAPI 스키마를 엽니다.

```text
https://<your-render-service>.onrender.com/openapi.json
```

2. Custom GPT 설정 화면에서 **Actions**를 열고, OpenAPI 스키마 가져오기 또는 붙여넣기 영역에 `/openapi.json` 내용을 복사합니다.
3. 인증 방식은 **API Key** 또는 **Bearer** 방식으로 설정하고, 헤더 이름은 `Authorization`을 사용합니다.
4. 토큰 값은 Render에 설정한 값과 동일하게 입력합니다.

```text
Bearer <ACTION_API_BEARER_TOKEN>
```

5. GPT Action 테스트에서 다음 엔드포인트를 확인합니다.

- `GET /health` — 공개 상태 확인
- `POST /score/{market}/{ticker}` — 단일 종목 점수화
- `POST /screen` — 후보 스크리닝
- `GET /candidates/top` — 상위 후보 조회

이 API는 리서치와 스크리닝 목적의 백엔드이며, 매수/매도 주문을 생성하지 않습니다.

## `/v1/market-snapshot` 데이터 범위와 partial 응답

`POST /v1/market-snapshot`은 기존 symbol/market 요청 구조와 기본 company/quote 정보를 유지하면서, 가능한 FMP 데이터를 `data` 아래의 optional 필드로 정규화합니다. 응답에는 가격·시가총액과 함께 `valuation`의 PER, forward PER, EV/EBITDA, P/S, P/B, FCF yield, `financial_metrics`의 매출·성장률·마진·EPS·FCF·ROE·ROIC·부채비율·유동비율, `market_data`의 거래량·평균 거래량·52주 고가/저가·섹터·산업이 포함될 수 있습니다. 공급자가 값을 제공하지 않으면 해당 필드는 값을 추정해 만들지 않고 `null`입니다.

FMP 무료 플랜이나 계정 권한에 따라 `key-metrics`, `ratios`, 재무제표 endpoint 일부가 제한될 수 있습니다. 이 경우 snapshot 전체 요청은 실패하지 않고 사용 가능한 profile/quote 등의 partial data를 HTTP 200 응답으로 반환합니다. 제한되거나 사용할 수 없는 endpoint는 민감정보 없이 `notes`, `endpoint_errors`, `error_type`에 표시됩니다. `fmp_auth_failed_or_plan_limited`는 401/403 또는 플랜 제한, `fmp_timeout`은 timeout, `fmp_endpoint_unavailable`은 그 밖의 endpoint 실패를 뜻합니다.

`data_reliability`와 `data_reliability_label`은 다음처럼 해석합니다.

- `high` / 약 `0.75` 이상: 가격·시가총액, valuation, financial metrics를 함께 확보했습니다.
- `medium` / 약 `0.60` 이상: 가격·시가총액과 valuation 일부를 확보했지만 상세 재무 데이터가 제한적입니다.
- `medium_low` / 약 `0.45` 이상: 기본 가격·시가총액 중심의 partial data입니다.
- `low`: 가격 또는 시가총액 등 기본 데이터도 부족합니다.

partial 응답에서는 `null` 필드와 `notes`를 확인하고, 낮은 신뢰도의 값을 완전한 재무 분석으로 해석하지 않아야 합니다. API key, bearer token, secret은 응답과 notes에 포함되지 않습니다.
