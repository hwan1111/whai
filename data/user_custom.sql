-- =====================================================
-- 2. 유저 커스텀 데이터 (User Custom Data)
-- =====================================================
 
-- 즐겨찾기 테이블
CREATE TABLE FAVORITE (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '즐겨찾기 식별자',
    user_id BIGINT NOT NULL COMMENT '유저 ID',
    type VARCHAR(20) NOT NULL COMMENT '구분 (TICKER / EXCHANGE)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '등록일',
    FOREIGN KEY (user_id) REFERENCES USER(id) ON DELETE CASCADE,
    INDEX idx_user_type (user_id, type)
);
 
-- 즐겨찾기 - 종목
CREATE TABLE FAVORITE_TICKER (
    favorite_id BIGINT PRIMARY KEY COMMENT '즐겨찾기 ID',
    ticker VARCHAR(20) NOT NULL COMMENT '종목 코드',
    FOREIGN KEY (favorite_id) REFERENCES FAVORITE(id) ON DELETE CASCADE,
    FOREIGN KEY (ticker) REFERENCES COMPANY(ticker) ON DELETE CASCADE,
    UNIQUE KEY unique_favorite_ticker (favorite_id, ticker)
);
 
-- 즐겨찾기 - 환율
CREATE TABLE FAVORITE_EXCHANGE (
    favorite_id BIGINT PRIMARY KEY COMMENT '즐겨찾기 ID',
    currency_pair VARCHAR(10) NOT NULL COMMENT '환율 쌍',
    FOREIGN KEY (favorite_id) REFERENCES FAVORITE(id) ON DELETE CASCADE,
    FOREIGN KEY (currency_pair) REFERENCES EXCHANGE_RATE(currency_pair) ON DELETE CASCADE,
    UNIQUE KEY unique_favorite_exchange (favorite_id, currency_pair)
);
 
-- 유저 리포트 테이블
CREATE TABLE USER_REPORT (
    id CHAR(36) PRIMARY KEY COMMENT '레포트 ID (UUID)',
    user_id BIGINT NOT NULL COMMENT '작성자 ID',
    title VARCHAR(500) NOT NULL COMMENT '레포트 제목',
    content LONGTEXT NOT NULL COMMENT '분석 본문',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '작성일',
    FOREIGN KEY (user_id) REFERENCES USER(id) ON DELETE CASCADE,
    INDEX idx_user_created (user_id, created_at)
);
 
-- 유저 리포트 - 기업 매핑
CREATE TABLE REPORT_COMPANY_MAP (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '매핑 식별자',
    report_id CHAR(36) NOT NULL COMMENT '레포트 ID',
    ticker VARCHAR(20) NOT NULL COMMENT '종목 코드',
    FOREIGN KEY (report_id) REFERENCES USER_REPORT(id) ON DELETE CASCADE,
    FOREIGN KEY (ticker) REFERENCES COMPANY(ticker) ON DELETE CASCADE,
    INDEX idx_report_ticker (report_id, ticker)
);
 