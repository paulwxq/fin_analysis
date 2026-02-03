-- =========================================
-- Stock blacklist table (optional)
-- =========================================
CREATE TABLE IF NOT EXISTS stock_blacklist (
    code VARCHAR(20) PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
