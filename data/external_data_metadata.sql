-- =====================================================
-- 3. 외부 데이터 메타정보 (External Data Metadata)
-- =====================================================
 
-- 뉴스 메타 테이블
CREATE TABLE NEWS_META (
    id CHAR(36) PRIMARY KEY COMMENT '뉴스 ID (UUID)',
    ticker VARCHAR(20) COMMENT '관련 종목 (선택적)',
    currency_pair VARCHAR(10) COMMENT '관련 환율 (선택적)',
    title VARCHAR(500) NOT NULL COMMENT '제목',
    summary LONGTEXT COMMENT '요약',
    source_url VARCHAR(2000) COMMENT '출처',
    published_at TIMESTAMP COMMENT '발행일',
    es_doc_id VARCHAR(255) COMMENT 'ES 문서 연결 키',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticker) REFERENCES COMPANY(ticker) ON DELETE SET NULL,
    FOREIGN KEY (currency_pair) REFERENCES EXCHANGE_RATE(currency_pair) ON DELETE SET NULL,
    INDEX idx_ticker_published (ticker, published_at),
    INDEX idx_currency_published (currency_pair, published_at),
    INDEX idx_es_doc_id (es_doc_id)
);
 
-- 뉴스 메타 INSERT 검증 트리거
DELIMITER $$
CREATE TRIGGER news_meta_before_insert 
BEFORE INSERT ON NEWS_META
FOR EACH ROW
BEGIN
    IF NEW.ticker IS NULL AND NEW.currency_pair IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'ticker와 currency_pair 중 최소 하나는 필수입니다';
    END IF;
END$$
DELIMITER ;
 
-- 뉴스 메타 UPDATE 검증 트리거
DELIMITER $$
CREATE TRIGGER news_meta_before_update 
BEFORE UPDATE ON NEWS_META
FOR EACH ROW
BEGIN
    IF NEW.ticker IS NULL AND NEW.currency_pair IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'ticker와 currency_pair 중 최소 하나는 필수입니다';
    END IF;
END$$
DELIMITER ;
 
-- =====================================================
-- 기관 리포트 메타 테이블
CREATE TABLE REPORT_META (
    id CHAR(36) PRIMARY KEY COMMENT '리포트 ID (UUID)',
    ticker VARCHAR(20) COMMENT '관련 종목 (선택적)',
    currency_pair VARCHAR(10) COMMENT '관련 환율 (선택적)',
    title VARCHAR(500) NOT NULL COMMENT '제목',
    summary LONGTEXT COMMENT '요약',
    author VARCHAR(255) COMMENT '작성자/기관',
    published_at TIMESTAMP COMMENT '발행일',
    es_doc_id VARCHAR(255) COMMENT 'ES 문서 연결 키',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticker) REFERENCES COMPANY(ticker) ON DELETE SET NULL,
    FOREIGN KEY (currency_pair) REFERENCES EXCHANGE_RATE(currency_pair) ON DELETE SET NULL,
    INDEX idx_ticker_published (ticker, published_at),
    INDEX idx_currency_published (currency_pair, published_at),
    INDEX idx_es_doc_id (es_doc_id)
);
 
-- 기관 리포트 메타 INSERT 검증 트리거
DELIMITER $$
CREATE TRIGGER report_meta_before_insert 
BEFORE INSERT ON REPORT_META
FOR EACH ROW
BEGIN
    IF NEW.ticker IS NULL AND NEW.currency_pair IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'ticker와 currency_pair 중 최소 하나는 필수입니다';
    END IF;
END$$
DELIMITER ;
 
-- 기관 리포트 메타 UPDATE 검증 트리거
DELIMITER $$
CREATE TRIGGER report_meta_before_update 
BEFORE UPDATE ON REPORT_META
FOR EACH ROW
BEGIN
    IF NEW.ticker IS NULL AND NEW.currency_pair IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'ticker와 currency_pair 중 최소 하나는 필수입니다';
    END IF;
END$$
DELIMITER ;