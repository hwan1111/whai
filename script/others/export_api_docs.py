"""
WHAi API 명세 내보내기 스크립트
- docs/openapi.yaml : OpenAPI 3.0 스펙
- docs/api_spec.pdf : 사람이 읽기 좋은 PDF 명세
"""

import sys
import json
import yaml
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DOCS_DIR = ROOT / "docs"
DOCS_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# 1. OpenAPI YAML 추출
# ─────────────────────────────────────────────

def export_yaml():
    print("[*] OpenAPI YAML 추출 중...")

    # DB 연결 없이 app만 임포트하기 위해 환경 변수 더미 설정
    import os
    os.environ.setdefault("DATABASE_URL", "mysql+pymysql://dummy:dummy@localhost/dummy")
    os.environ.setdefault("SECRET_KEY", "dummy-secret-key")
    os.environ.setdefault("ALGORITHM", "HS256")

    try:
        from backend.main import app
        spec = app.openapi()
    except Exception as e:
        print(f"  [WARN] FastAPI app import 실패 ({e}), 수동 스펙으로 대체합니다.")
        spec = build_manual_spec()

    yaml_path = DOCS_DIR / "openapi.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(spec, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    print(f"  [OK] 저장: {yaml_path}")
    return spec


def build_manual_spec() -> dict:
    """FastAPI import 실패 시 수동으로 구성한 OpenAPI 3.0 스펙."""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "WHAi API",
            "version": "1.0.0",
            "description": "금융 AI 서비스 WHAi의 REST API 명세입니다.",
        },
        "servers": [{"url": "/api/v1", "description": "API v1"}],
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                }
            }
        },
        "security": [{"BearerAuth": []}],
        "paths": {
            # ── AUTH ──
            "/auth/register": {
                "post": {
                    "tags": ["Auth"],
                    "summary": "회원가입",
                    "description": "새 사용자 계정을 생성합니다. Rate Limit: 3/min",
                    "security": [],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["user_id", "name", "password"],
                            "properties": {
                                "user_id": {"type": "string", "minLength": 5, "maxLength": 20},
                                "name": {"type": "string"},
                                "password": {"type": "string", "minLength": 5, "maxLength": 20},
                                "birth_year": {"type": "integer", "nullable": True},
                                "gender": {"type": "string", "enum": ["M", "F"], "nullable": True},
                                "invest_type": {"type": "string", "nullable": True},
                            },
                        }}},
                    },
                    "responses": {
                        "201": {"description": "회원가입 성공"},
                        "400": {"description": "유효하지 않은 user_id"},
                        "409": {"description": "이미 사용 중인 아이디"},
                    },
                }
            },
            "/auth/check-id": {
                "get": {
                    "tags": ["Auth"],
                    "summary": "아이디 중복 확인",
                    "security": [],
                    "parameters": [{"name": "user_id", "in": "query", "required": True, "schema": {"type": "string"}}],
                    "responses": {
                        "200": {"description": "확인 결과", "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {"available": {"type": "boolean"}},
                        }}}},
                    },
                }
            },
            "/auth/login": {
                "post": {
                    "tags": ["Auth"],
                    "summary": "로그인",
                    "description": "Rate Limit: 5/min",
                    "security": [],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["user_id", "password"],
                            "properties": {
                                "user_id": {"type": "string"},
                                "password": {"type": "string"},
                            },
                        }}},
                    },
                    "responses": {
                        "200": {"description": "토큰 발급", "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "access_token": {"type": "string"},
                                "refresh_token": {"type": "string"},
                                "token_type": {"type": "string"},
                                "name": {"type": "string"},
                                "user_id": {"type": "string"},
                                "profile_image_url": {"type": "string", "nullable": True},
                            },
                        }}}},
                        "401": {"description": "아이디 또는 비밀번호 오류"},
                    },
                }
            },
            "/auth/refresh": {
                "post": {
                    "tags": ["Auth"],
                    "summary": "Access Token 재발급",
                    "security": [],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["refresh_token"],
                            "properties": {"refresh_token": {"type": "string"}},
                        }}},
                    },
                    "responses": {
                        "200": {"description": "새 Access Token"},
                        "401": {"description": "유효하지 않은 토큰"},
                    },
                }
            },
            "/auth/me": {
                "get": {
                    "tags": ["Auth"],
                    "summary": "내 프로필 조회",
                    "responses": {
                        "200": {"description": "프로필 정보"},
                        "401": {"description": "인증 실패"},
                    },
                },
                "patch": {
                    "tags": ["Auth"],
                    "summary": "프로필 수정 (이름·투자성향)",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "nullable": True},
                                "invest_type": {"type": "string", "nullable": True},
                            },
                        }}},
                    },
                    "responses": {"200": {"description": "수정 완료"}},
                },
                "delete": {
                    "tags": ["Auth"],
                    "summary": "계정 삭제",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["password"],
                            "properties": {"password": {"type": "string"}},
                        }}},
                    },
                    "responses": {"204": {"description": "삭제 완료"}, "401": {"description": "비밀번호 오류"}},
                },
            },
            "/auth/change-password": {
                "post": {
                    "tags": ["Auth"],
                    "summary": "비밀번호 변경",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["current_password", "new_password"],
                            "properties": {
                                "current_password": {"type": "string"},
                                "new_password": {"type": "string", "minLength": 5, "maxLength": 20},
                            },
                        }}},
                    },
                    "responses": {"200": {"description": "변경 완료"}, "401": {"description": "현재 비밀번호 오류"}},
                }
            },
            "/auth/me/profile-image": {
                "get": {
                    "tags": ["Auth"],
                    "summary": "프로필 이미지 다운로드",
                    "responses": {"200": {"description": "이미지 바이너리"}, "404": {"description": "이미지 없음"}},
                },
                "post": {
                    "tags": ["Auth"],
                    "summary": "프로필 이미지 업로드 (최대 5MB, JPEG/PNG/WEBP/GIF)",
                    "requestBody": {
                        "required": True,
                        "content": {"multipart/form-data": {"schema": {
                            "type": "object",
                            "properties": {"file": {"type": "string", "format": "binary"}},
                        }}},
                    },
                    "responses": {"200": {"description": "업로드 완료, S3 Presigned URL 반환"}, "400": {"description": "형식/크기 오류"}},
                },
                "delete": {
                    "tags": ["Auth"],
                    "summary": "프로필 이미지 삭제",
                    "responses": {"204": {"description": "삭제 완료"}},
                },
            },
            # ── PRICES ──
            "/prices/data-freshness": {
                "get": {
                    "tags": ["Prices"],
                    "summary": "데이터 최신성 확인",
                    "security": [],
                    "responses": {"200": {"description": "가격·뉴스·펀더멘탈 최신 업데이트일"}},
                }
            },
            "/prices/latest": {
                "get": {
                    "tags": ["Prices"],
                    "summary": "전체 자산 최신 가격 목록",
                    "security": [],
                    "responses": {"200": {"description": "종목별 종가·변동률 리스트"}},
                }
            },
            "/prices/{ticker}/history": {
                "get": {
                    "tags": ["Prices"],
                    "summary": "가격 이력 조회",
                    "security": [],
                    "parameters": [
                        {"name": "ticker", "in": "path", "required": True, "schema": {"type": "string"}, "description": "6자리 숫자 또는 3자리 영문"},
                        {"name": "period", "in": "query", "schema": {"type": "string", "enum": ["1W","1M","3M","6M","1Y","3Y","ALL"], "default": "3M"}},
                    ],
                    "responses": {"200": {"description": "날짜별 종가·수익률"}, "400": {"description": "유효하지 않은 ticker"}},
                }
            },
            "/prices/{ticker}/stats": {
                "get": {
                    "tags": ["Prices"],
                    "summary": "가격 통계 (52주 고저가·PER·PBR·시가총액)",
                    "security": [],
                    "parameters": [{"name": "ticker", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "통계 데이터"}},
                }
            },
            "/prices/{ticker}/prediction": {
                "get": {
                    "tags": ["Prices"],
                    "summary": "AI 가격 예측 (D+5 목표가·신뢰구간·모델 정보)",
                    "security": [],
                    "parameters": [{"name": "ticker", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "예측 결과"}, "404": {"description": "예측 데이터 없음"}},
                }
            },
            # ── NEWS ──
            "/news": {
                "get": {
                    "tags": ["News"],
                    "summary": "시장 레짐 + AI 요약 조회",
                    "security": [],
                    "parameters": [
                        {"name": "ticker", "in": "query", "schema": {"type": "string"}, "required": False},
                        {"name": "days", "in": "query", "schema": {"type": "integer", "default": 7}},
                    ],
                    "responses": {"200": {"description": "레짐 방향·누적수익률·AI 원인 분석"}},
                }
            },
            # ── FAVORITES ──
            "/favorites": {
                "get": {
                    "tags": ["Favorites"],
                    "summary": "관심종목 조회",
                    "responses": {"200": {"description": "ticker 리스트"}},
                },
                "put": {
                    "tags": ["Favorites"],
                    "summary": "관심종목 전체 교체",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {"assets": {"type": "array", "items": {"type": "string"}}},
                        }}},
                    },
                    "responses": {"200": {"description": "저장 완료"}},
                },
            },
            # ── REPORT ──
            "/report/snapshots": {
                "get": {
                    "tags": ["Report"],
                    "summary": "포트폴리오 스냅샷 목록 (최대 10개, 최신순)",
                    "responses": {"200": {"description": "스냅샷 리스트"}},
                },
                "post": {
                    "tags": ["Report"],
                    "summary": "스냅샷 저장 + LLM AI 분석 자동 실행",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["id", "datetime", "holdings"],
                            "properties": {
                                "id": {"type": "string"},
                                "datetime": {"type": "string"},
                                "holdings": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "ticker": {"type": "string"},
                                            "name": {"type": "string"},
                                            "quantity": {"type": "number"},
                                            "price": {"type": "number"},
                                        },
                                    },
                                },
                            },
                        }}},
                    },
                    "responses": {"201": {"description": "저장 완료"}},
                },
            },
            "/report/snapshots/{snap_id}": {
                "delete": {
                    "tags": ["Report"],
                    "summary": "스냅샷 삭제",
                    "parameters": [{"name": "snap_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "삭제 완료"}},
                }
            },
            "/report/factor-insights": {
                "post": {
                    "tags": ["Report"],
                    "summary": "변동 요인 LLM 분석 (당일 DB 캐시)",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["ticker", "ticker_name", "factors"],
                            "properties": {
                                "ticker": {"type": "string"},
                                "ticker_name": {"type": "string"},
                                "factors": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {"label": {"type": "string"}},
                                    },
                                },
                            },
                        }}},
                    },
                    "responses": {
                        "200": {"description": "요인별 방향·강도·설명·투자 유의사항"},
                        "502": {"description": "LLM 호출 실패"},
                    },
                }
            },
            "/report/correlation-insights": {
                "post": {
                    "tags": ["Report"],
                    "summary": "자산 쌍 상관관계 LLM 설명 (배치)",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "pairs": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "key": {"type": "string"},
                                            "asset_a_name": {"type": "string"},
                                            "asset_b_name": {"type": "string"},
                                            "correlation": {"type": "number"},
                                        },
                                    },
                                }
                            },
                        }}},
                    },
                    "responses": {
                        "200": {"description": "쌍별 30자 이내 설명"},
                        "502": {"description": "LLM 호출 실패"},
                    },
                }
            },
            "/report/correlation": {
                "get": {
                    "tags": ["Report"],
                    "summary": "사전 계산된 상관계수 조회",
                    "parameters": [
                        {"name": "period", "in": "query", "schema": {"type": "string", "enum": ["1W","1M","3M","6M","1Y","3Y","ALL"], "default": "1M"}},
                    ],
                    "responses": {
                        "200": {"description": "기간별 상관계수 쌍 리스트"},
                        "400": {"description": "유효하지 않은 period"},
                        "404": {"description": "데이터 없음"},
                    },
                }
            },
        },
    }


# ─────────────────────────────────────────────
# 2. PDF 생성
# ─────────────────────────────────────────────

def export_pdf():
    print("[*] PDF 생성 중...")
    from fpdf import FPDF

    ENDPOINTS = [
        # (tag, method, path, summary, auth, rate_limit, params, req_body, responses, note)
        # ── AUTH ──
        ("Auth", "POST",   "/api/v1/auth/register",           "회원가입",                        False, "3/min",
         [],
         '{"user_id":"string(5-20)","name":"string","password":"string(5-20)","birth_year":"int?","gender":"M|F?","invest_type":"string?"}',
         ["201 Created", "400 유효하지 않은 user_id", "409 중복 아이디"], ""),

        ("Auth", "GET",    "/api/v1/auth/check-id",           "아이디 중복 확인",                 False, "",
         ["user_id (query, required)"],
         "",
         ['200 {"available": boolean}'], ""),

        ("Auth", "POST",   "/api/v1/auth/login",              "로그인 → access/refresh 토큰 발급", False, "5/min",
         [],
         '{"user_id":"string","password":"string"}',
         ['200 {"access_token","refresh_token","token_type","name","user_id","profile_image_url"}', "401 인증 실패"], ""),

        ("Auth", "POST",   "/api/v1/auth/refresh",            "Access Token 재발급",              False, "",
         [],
         '{"refresh_token":"string"}',
         ["200 새 access_token", "401 유효하지 않은 토큰"], ""),

        ("Auth", "GET",    "/api/v1/auth/me",                 "내 프로필 조회",                   True, "",
         [], "", ["200 프로필 정보", "401 인증 실패"], ""),

        ("Auth", "PATCH",  "/api/v1/auth/me",                 "프로필 수정 (이름·투자성향)",       True, "",
         [],
         '{"name":"string?","invest_type":"string?"}',
         ["200 수정 완료"], ""),

        ("Auth", "DELETE", "/api/v1/auth/me",                 "계정 삭제",                        True, "",
         [],
         '{"password":"string"}',
         ["204 삭제 완료", "401 비밀번호 오류"], ""),

        ("Auth", "POST",   "/api/v1/auth/change-password",    "비밀번호 변경",                    True, "",
         [],
         '{"current_password":"string","new_password":"string(5-20)"}',
         ["200 변경 완료", "401 현재 비밀번호 오류"], ""),

        ("Auth", "GET",    "/api/v1/auth/me/profile-image",   "프로필 이미지 다운로드 (바이너리)", True, "",
         [], "", ["200 image/jpeg 등", "404 이미지 없음"], ""),

        ("Auth", "POST",   "/api/v1/auth/me/profile-image",   "프로필 이미지 업로드",             True, "",
         [],
         "multipart/form-data  file: binary (JPEG/PNG/WEBP/GIF, max 5MB)",
         ["200 S3 Presigned URL", "400 형식/크기 오류"], ""),

        ("Auth", "DELETE", "/api/v1/auth/me/profile-image",   "프로필 이미지 삭제",               True, "",
         [], "", ["204 삭제 완료"], ""),

        # ── PRICES ──
        ("Prices", "GET", "/api/v1/prices/data-freshness",    "데이터 최신성 확인",               False, "",
         [], "", ['200 {"price","news","fundamental"}: 최신 업데이트일(YYYY-MM-DD)'], ""),

        ("Prices", "GET", "/api/v1/prices/latest",            "전체 자산 최신 가격 목록",          False, "",
         [], "", ["200 [{ticker,name,sector,close,change,change_pct,date}]"], ""),

        ("Prices", "GET", "/api/v1/prices/{ticker}/history",  "가격 이력 조회",                   False, "",
         ["ticker (path): 6자리 숫자 또는 3자리 영문", "period (query, 기본 3M): 1W|1M|3M|6M|1Y|3Y|ALL"],
         "", ["200 [{date,close,return_pct}]", "400 유효하지 않은 ticker"], ""),

        ("Prices", "GET", "/api/v1/prices/{ticker}/stats",    "가격 통계 (52주 고저·PER·PBR 등)",  False, "",
         ["ticker (path)"],
         "", ["200 {high52,low52,volume,per,pbr,market_cap,change,change_pct,change_30d,change_1y}"], ""),

        ("Prices", "GET", "/api/v1/prices/{ticker}/prediction","AI D+5 가격 예측",                False, "",
         ["ticker (path)"],
         "", ["200 {pred_price_d5,pred_return_d5,ci_upper_d5,ci_lower_d5,ci_pct,model_used,drift_detected,retrain_needed,...}", "404 데이터 없음"], ""),

        # ── NEWS ──
        ("News", "GET",   "/api/v1/news",                     "시장 레짐 + AI 요약 조회",          False, "",
         ["ticker (query, 선택)", "days (query, 기본 7)"],
         "", ["200 [{ticker,name,direction,start_date,end_date,cum_return,cause,vol_insight,confidence}]"], ""),

        # ── FAVORITES ──
        ("Favorites", "GET", "/api/v1/favorites",             "관심종목 조회",                    True, "",
         [], "", ['200 {"assets":["ticker",...]}'], ""),

        ("Favorites", "PUT", "/api/v1/favorites",             "관심종목 전체 교체",               True, "",
         [],
         '{"assets":["ticker",...]}',
         ['200 {"ok":true}'], "기존 목록 전체 삭제 후 재삽입"),

        # ── REPORT ──
        ("Report", "GET",    "/api/v1/report/snapshots",          "포트폴리오 스냅샷 목록",        True, "",
         [], "", ["200 최대 10개, 최신순. ai_analysis 포함"], ""),

        ("Report", "POST",   "/api/v1/report/snapshots",          "스냅샷 저장 + LLM 분석 실행",  True, "",
         [],
         '{"id":"string","datetime":"string","holdings":[{"ticker","name","quantity","price"}]}',
         ["201 저장 완료"], "LLM 실패 시에도 스냅샷은 저장됨 (ai_analysis=null)"),

        ("Report", "DELETE", "/api/v1/report/snapshots/{snap_id}","스냅샷 삭제",                  True, "",
         ["snap_id (path)"], "", ["200 삭제 완료"], ""),

        ("Report", "POST",   "/api/v1/report/factor-insights",    "변동 요인 LLM 분석",           True, "",
         [],
         '{"ticker":"string","ticker_name":"string","factors":[{"label":"string"}]}',
         ['200 {"labels","directions","strengths","descs","advice"}', "502 LLM 호출 실패"],
         "당일 동일 ticker 재요청 시 DB 캐시 반환"),

        ("Report", "POST",   "/api/v1/report/correlation-insights","상관관계 LLM 설명 (배치)",    True, "",
         [],
         '{"pairs":[{"key":"A|B","asset_a_name":"","asset_b_name":"","correlation":0.0}]}',
         ['200 {"descriptions":{"A|B":"30자 이내 설명"}}', "502 LLM 호출 실패"], ""),

        ("Report", "GET",    "/api/v1/report/correlation",        "사전 계산 상관계수 조회",       True, "",
         ["period (query, 기본 1M): 1W|1M|3M|6M|1Y|3Y|ALL"],
         "", ['200 {"period","computed_date","pairs":[{"a","b","v"}]}', "400 유효하지 않은 period", "404 데이터 없음"], ""),

        # ── HEALTH ──
        ("Health", "GET", "/health",                           "헬스체크",                         False, "",
         [], "", ['200 {"status":"ok"}'], ""),
    ]

    MALGUN      = "C:/Windows/Fonts/malgun.ttf"
    MALGUN_BOLD = "C:/Windows/Fonts/malgunbd.ttf"

    METHOD_COLORS = {
        "GET":    (0x61, 0xAF, 0xEF),
        "POST":   (0x98, 0xC3, 0x79),
        "PUT":    (0xE5, 0xC0, 0x7B),
        "PATCH":  (0xD1, 0x9A, 0x66),
        "DELETE": (0xE0, 0x6C, 0x75),
    }

    class PDF(FPDF):
        def header(self):
            self.set_fill_color(30, 35, 48)
            self.rect(0, 0, 210, 18, "F")
            self.set_font("MalgunBold", size=13)
            self.set_text_color(255, 255, 255)
            self.set_y(4)
            self.cell(0, 10, "WHAi API Specification  v1.0.0", align="C")
            self.set_text_color(0, 0, 0)
            self.ln(12)

        def footer(self):
            self.set_y(-12)
            self.set_font("Malgun", size=8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, f"Page {self.page_no()}", align="C")
            self.set_text_color(0, 0, 0)

    pdf = PDF()
    pdf.add_font("Malgun",     fname=MALGUN,      uni=True)
    pdf.add_font("MalgunBold", fname=MALGUN_BOLD, uni=True)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # ── 커버 정보 ──
    pdf.set_fill_color(245, 246, 250)
    pdf.set_draw_color(200, 205, 215)
    pdf.rect(10, 20, 190, 26, "FD")
    pdf.set_xy(14, 23)
    pdf.set_font("MalgunBold", size=9)
    pdf.cell(35, 5, "Base URL")
    pdf.set_font("Malgun", size=9); pdf.cell(0, 5, "/api/v1"); pdf.ln(5)
    pdf.set_x(14); pdf.set_font("MalgunBold", size=9)
    pdf.cell(35, 5, "Authentication")
    pdf.set_font("Malgun", size=9)
    pdf.cell(0, 5, "Bearer Token (JWT HS256) - Authorization: Bearer <access_token>"); pdf.ln(5)
    pdf.set_x(14); pdf.set_font("MalgunBold", size=9)
    pdf.cell(35, 5, "Token Expiry")
    pdf.set_font("Malgun", size=9)
    pdf.cell(0, 5, "Access Token: 60min  |  Refresh Token: 3days  |  Issuer: whai")
    pdf.ln(10)

    # ── 공통 에러 표 ──
    pdf.set_font("MalgunBold", size=9)
    pdf.cell(0, 6, "공통 에러 응답", ln=True)
    errors = [("400", "잘못된 파라미터 (ticker 형식, 파일 형식 등)"),
              ("401", "인증 실패 / 토큰 만료"),
              ("404", "리소스 없음"),
              ("409", "중복 아이디"),
              ("429", "Rate Limit 초과"),
              ("502", "LLM 호출 실패")]
    for code, msg in errors:
        pdf.set_x(10)
        pdf.set_fill_color(240, 242, 248)
        pdf.set_font("MalgunBold", size=8)
        pdf.cell(14, 5, code, fill=True, border=1)
        pdf.set_font("Malgun", size=8)
        pdf.cell(0, 5, f"  {msg}", border=1, ln=True)
    pdf.ln(6)

    current_tag = None

    for (tag, method, path, summary, auth, rate, params, req, responses, note) in ENDPOINTS:
        if tag != current_tag:
            current_tag = tag
            pdf.set_fill_color(30, 35, 48)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("MalgunBold", size=10)
            pdf.cell(0, 7, f"  {tag}", fill=True, ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)

        # 메서드 뱃지
        r, g, b = METHOD_COLORS.get(method, (180, 180, 180))
        pdf.set_fill_color(r, g, b)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("MalgunBold", size=8)
        pdf.cell(16, 6, f" {method}", fill=True)
        pdf.set_text_color(0, 0, 0)
        # 경로
        pdf.set_font("Malgun", size=8)
        pdf.set_fill_color(245, 246, 250)
        pdf.cell(115, 6, f"  {path}", fill=True)
        # Auth 뱃지
        if auth:
            pdf.set_fill_color(230, 244, 255)
            pdf.set_text_color(30, 100, 200)
            pdf.set_font("MalgunBold", size=7)
            pdf.cell(20, 6, " Auth", fill=True, border=1)
            pdf.set_text_color(0, 0, 0)
        else:
            pdf.cell(20, 6, "")
        # Rate Limit 뱃지
        if rate:
            pdf.set_fill_color(255, 243, 225)
            pdf.set_text_color(180, 100, 0)
            pdf.set_font("MalgunBold", size=7)
            pdf.cell(30, 6, f" {rate}", fill=True, border=1)
            pdf.set_text_color(0, 0, 0)
        pdf.ln(6)

        # 요약
        pdf.set_font("MalgunBold", size=8)
        pdf.set_x(14)
        pdf.cell(0, 5, summary, ln=True)

        # 메모
        if note:
            pdf.set_x(14)
            pdf.set_font("Malgun", size=7)
            pdf.set_text_color(120, 120, 120)
            pdf.cell(0, 4, f"* {note}", ln=True)
            pdf.set_text_color(0, 0, 0)

        def label_row(label, content, color=(248, 250, 252)):
            pdf.set_x(14)
            pdf.set_fill_color(*color)
            pdf.set_font("MalgunBold", size=7)
            pdf.cell(22, 4, label, fill=True)
            pdf.set_font("Malgun", size=7)
            lines = content if isinstance(content, list) else [content]
            first = True
            for line in lines:
                if not first:
                    pdf.set_x(36)
                pdf.cell(0, 4, str(line), ln=True)
                first = False

        if params:
            label_row("Params", params)
        if req:
            label_row("Request", req, (240, 248, 240))
        if responses:
            label_row("Responses", responses, (240, 240, 255))

        pdf.ln(3)

    pdf_path = DOCS_DIR / "api_spec.pdf"
    pdf.output(str(pdf_path))
    print(f"  [OK] 저장: {pdf_path}")


# ─────────────────────────────────────────────
# 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":
    export_yaml()
    export_pdf()
    print("\n[완료] docs/ 폴더를 확인하세요.")
    print("  - docs/openapi.yaml")
    print("  - docs/api_spec.pdf")
