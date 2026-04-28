-- Active: 1768885588121@@118.67.131.22@3306@whai
-- =====================================================
-- 1. 기본 테이블 (Base Tables)
-- =====================================================
 
-- 통화 테이블
CREATE TABLE CURRENCY (
    code VARCHAR(3) PRIMARY KEY COMMENT '통화 코드 (예: USD, KRW)',
    name VARCHAR(100) NOT NULL COMMENT '통화명 (예: 미국 달러)',
    country VARCHAR(100) COMMENT '국가'
);
 
-- 유저 테이블
CREATE TABLE USER (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '유저 ID',
    email VARCHAR(255) NOT NULL UNIQUE COMMENT '이메일',
    password VARCHAR(255) NOT NULL COMMENT '비밀번호 (Hash)',
    nickname VARCHAR(100) NOT NULL COMMENT '닉네임',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '가입일'
);
 
-- 유저 프로필 테이블
CREATE TABLE USER_PROFILE (
    user_id BIGINT PRIMARY KEY COMMENT '유저 ID',
    profile_image_url VARCHAR(500) COMMENT '이미지 저장 경로 (S3 URL 등)',
    original_file_name VARCHAR(255) COMMENT '원본 파일명',
    age_group VARCHAR(50) COMMENT '연령대',
    invest_type VARCHAR(100) COMMENT '투자 유형',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정일',
    FOREIGN KEY (user_id) REFERENCES USER(id) ON DELETE CASCADE
);
 
-- 기업 테이블
CREATE TABLE COMPANY (
    ticker VARCHAR(20) PRIMARY KEY COMMENT '티커 (예: "00000" or "AAPL")',
    name VARCHAR(255) NOT NULL COMMENT '기업명',
    sector VARCHAR(100) COMMENT '섹터',
    currency_code VARCHAR(3) COMMENT '결산 통화',
    FOREIGN KEY (currency_code) REFERENCES CURRENCY(code)
);
 
-- 환율 테이블
CREATE TABLE EXCHANGE_RATE (
    currency_pair VARCHAR(10) NOT NULL COMMENT '환율 쌍 (예: KRW/USD)',
    date DATE NOT NULL COMMENT '고시 일자',
    base_currency_code VARCHAR(3) COMMENT '기준 통화',
    target_currency_code VARCHAR(3) COMMENT '대상 통화',
    rate DECIMAL(18, 6) NOT NULL COMMENT '환율 값',
    PRIMARY KEY (currency_pair, date),
    FOREIGN KEY (base_currency_code) REFERENCES CURRENCY(code),
    FOREIGN KEY (target_currency_code) REFERENCES CURRENCY(code)
);
 
-- 시세 테이블
CREATE TABLE PRICE (
    ticker VARCHAR(20) NOT NULL COMMENT '종목 코드',
    date DATE NOT NULL COMMENT '일자',
    close DECIMAL(18, 2) NOT NULL COMMENT '종가',
    volume BIGINT COMMENT '거래량',
    PRIMARY KEY (ticker, date),
    FOREIGN KEY (ticker) REFERENCES COMPANY(ticker) ON DELETE CASCADE
);