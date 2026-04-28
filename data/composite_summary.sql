-- =====================================================
-- 4. 복합 요약 (Composite Summary)
-- =====================================================
 
-- 복합 요약 테이블
CREATE TABLE COMPOSITE_SUMMARY (
    id CHAR(36) PRIMARY KEY COMMENT '복합 요약 ID (UUID)',
    user_id BIGINT NOT NULL COMMENT '생성 요청한 유저 아이디',
    summary LONGTEXT NOT NULL COMMENT 'LLM 복합 요약 결과',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성일',
    FOREIGN KEY (user_id) REFERENCES USER(id) ON DELETE CASCADE,
    INDEX idx_user_created (user_id, created_at)
);
 
-- 복합 요약 - 종목 매핑
CREATE TABLE COMPOSITE_SUMMARY_TICKER (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '매핑 ID',
    summary_id CHAR(36) NOT NULL COMMENT '복합 요약 ID',
    ticker VARCHAR(20) NOT NULL COMMENT '종목 코드',
    FOREIGN KEY (summary_id) REFERENCES COMPOSITE_SUMMARY(id) ON DELETE CASCADE,
    FOREIGN KEY (ticker) REFERENCES COMPANY(ticker) ON DELETE CASCADE,
    INDEX idx_summary_ticker (summary_id, ticker)
);
 
-- 복합 요약 - 환율 매핑
CREATE TABLE COMPOSITE_SUMMARY_EXCHANGE (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '매핑 ID',
    summary_id CHAR(36) NOT NULL COMMENT '복합 요약 ID',
    currency_pair VARCHAR(10) NOT NULL COMMENT '환율 쌍',
    FOREIGN KEY (summary_id) REFERENCES COMPOSITE_SUMMARY(id) ON DELETE CASCADE,
    FOREIGN KEY (currency_pair) REFERENCES EXCHANGE_RATE(currency_pair) ON DELETE CASCADE,
    INDEX idx_summary_currency (summary_id, currency_pair)
);
 
-- 복합 요약 - 뉴스 매핑
CREATE TABLE COMPOSITE_SUMMARY_NEWS (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '매핑 ID',
    summary_id CHAR(36) NOT NULL COMMENT '복합 요약 ID',
    news_id CHAR(36) NOT NULL COMMENT '뉴스 ID',
    FOREIGN KEY (summary_id) REFERENCES COMPOSITE_SUMMARY(id) ON DELETE CASCADE,
    FOREIGN KEY (news_id) REFERENCES NEWS_META(id) ON DELETE CASCADE,
    INDEX idx_summary_news (summary_id, news_id)
);
 
-- 복합 요약 - 리포트 매핑
CREATE TABLE COMPOSITE_SUMMARY_REPORT (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '매핑 ID',
    summary_id CHAR(36) NOT NULL COMMENT '복합 요약 ID',
    report_id CHAR(36) NOT NULL COMMENT '리포트 ID',
    FOREIGN KEY (summary_id) REFERENCES COMPOSITE_SUMMARY(id) ON DELETE CASCADE,
    FOREIGN KEY (report_id) REFERENCES REPORT_META(id) ON DELETE CASCADE,
    INDEX idx_summary_report (summary_id, report_id)
);
 