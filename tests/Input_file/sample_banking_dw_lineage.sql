/* ============================================================================
   SAMPLE SQL FILE FOR SOURCE-TO-TARGET MAPPING (STTM) / LINEAGE TESTING
   Domain      : Retail Banking Data Warehouse
   Dialect     : Snowflake (MERGE, CREATE OR REPLACE PROCEDURE ... LANGUAGE SQL)
   Purpose     : Contains source tables, staging tables, target tables, views,
                 and stored procedures with varying lineage complexity:
                   - direct 1:1 column mapping
                   - derived / calculated columns
                   - lookups & joins across multiple sources
                   - conditional (CASE) transformations
                   - aggregations & window functions
                   - SCD Type 2 MERGE logic
                   - multi-hop lineage (source -> staging -> target)
   ============================================================================ */


/* ============================================================================
   1. SOURCE (OLTP) TABLES  -- schema: src
   ============================================================================ */

CREATE TABLE IF NOT EXISTS src.customers (
    customer_id      NUMBER(10)      PRIMARY KEY,
    first_name       VARCHAR(50),
    last_name        VARCHAR(50),
    date_of_birth    DATE,
    email            VARCHAR(100),
    phone            VARCHAR(20),
    address_line1    VARCHAR(150),
    city             VARCHAR(60),
    state_code       VARCHAR(2),
    zip_code         VARCHAR(10),
    customer_segment VARCHAR(20),     -- RETAIL, SMALL_BUSINESS, PRIVATE
    created_date     TIMESTAMP,
    last_updated_ts  TIMESTAMP,
    is_active        BOOLEAN
);

CREATE TABLE IF NOT EXISTS src.branches (
    branch_id        NUMBER(6)       PRIMARY KEY,
    branch_name      VARCHAR(100),
    region           VARCHAR(50),
    state_code       VARCHAR(2),
    open_date        DATE,
    branch_type      VARCHAR(20)     -- FULL_SERVICE, ATM_ONLY, DIGITAL
);

CREATE TABLE IF NOT EXISTS src.accounts (
    account_id       NUMBER(12)      PRIMARY KEY,
    customer_id      NUMBER(10)      REFERENCES src.customers(customer_id),
    branch_id        NUMBER(6)       REFERENCES src.branches(branch_id),
    account_type     VARCHAR(20),     -- CHECKING, SAVINGS, LOAN, CD
    open_date        DATE,
    close_date       DATE,
    account_status   VARCHAR(15),     -- ACTIVE, DORMANT, CLOSED
    interest_rate    NUMBER(6,4),
    credit_limit     NUMBER(15,2)
);

CREATE TABLE IF NOT EXISTS src.transactions (
    transaction_id   NUMBER(15)      PRIMARY KEY,
    account_id       NUMBER(12)      REFERENCES src.accounts(account_id),
    transaction_ts   TIMESTAMP,
    transaction_type VARCHAR(20),     -- DEPOSIT, WITHDRAWAL, TRANSFER, FEE, INTEREST
    amount           NUMBER(15,2),
    currency_code    VARCHAR(3),
    channel          VARCHAR(20),     -- BRANCH, ATM, ONLINE, MOBILE, ACH
    merchant_name    VARCHAR(100),
    description      VARCHAR(255),
    is_reversed      BOOLEAN
);

CREATE TABLE IF NOT EXISTS src.exchange_rates (
    currency_code    VARCHAR(3),
    rate_date        DATE,
    rate_to_usd      NUMBER(10,6),
    PRIMARY KEY (currency_code, rate_date)
);

CREATE TABLE IF NOT EXISTS src.fraud_flags (
    transaction_id   NUMBER(15),
    flag_reason      VARCHAR(100),
    flagged_ts       TIMESTAMP,
    severity         VARCHAR(10)      -- LOW, MEDIUM, HIGH
);


/* ============================================================================
   2. STAGING TABLES  -- schema: stg
   ============================================================================ */

CREATE TABLE IF NOT EXISTS stg.stg_customer_profile (
    customer_id       NUMBER(10),
    full_name         VARCHAR(120),
    email             VARCHAR(100),
    state_code        VARCHAR(2),
    customer_segment  VARCHAR(20),
    age_band          VARCHAR(10),
    is_active         BOOLEAN,
    load_ts           TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stg.stg_transactions_enriched (
    transaction_id    NUMBER(15),
    account_id        NUMBER(12),
    customer_id       NUMBER(10),
    branch_id         NUMBER(6),
    transaction_date  DATE,
    transaction_type  VARCHAR(20),
    amount_usd        NUMBER(15,2),
    channel           VARCHAR(20),
    txn_category      VARCHAR(30),
    is_fraud_flagged  BOOLEAN,
    load_ts           TIMESTAMP
);


/* ============================================================================
   3. TARGET DATA WAREHOUSE TABLES  -- schema: dw
   ============================================================================ */

CREATE TABLE IF NOT EXISTS dw.dim_customer (
    customer_key      NUMBER(10)      IDENTITY PRIMARY KEY,
    customer_id       NUMBER(10),
    full_name         VARCHAR(120),
    email             VARCHAR(100),
    state_code        VARCHAR(2),
    customer_segment  VARCHAR(20),
    age_band          VARCHAR(10),
    is_active         BOOLEAN,
    effective_date    DATE,
    end_date          DATE,
    is_current        BOOLEAN
);

CREATE TABLE IF NOT EXISTS dw.dim_branch (
    branch_key        NUMBER(6)       IDENTITY PRIMARY KEY,
    branch_id         NUMBER(6),
    branch_name       VARCHAR(100),
    region            VARCHAR(50),
    state_code        VARCHAR(2),
    branch_type       VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key          NUMBER(8)       PRIMARY KEY,   -- YYYYMMDD
    full_date         DATE,
    year              NUMBER(4),
    quarter           NUMBER(1),
    month             NUMBER(2),
    day_of_week       VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS dw.fact_transactions (
    transaction_key   NUMBER(15)      IDENTITY PRIMARY KEY,
    transaction_id    NUMBER(15),
    customer_key      NUMBER(10)      REFERENCES dw.dim_customer(customer_key),
    branch_key        NUMBER(6)       REFERENCES dw.dim_branch(branch_key),
    date_key          NUMBER(8)       REFERENCES dw.dim_date(date_key),
    transaction_type  VARCHAR(20),
    txn_category      VARCHAR(30),
    channel           VARCHAR(20),
    amount_usd        NUMBER(15,2),
    running_balance_usd NUMBER(15,2),
    is_fraud_flagged  BOOLEAN,
    load_ts           TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dw.agg_daily_branch_summary (
    branch_key        NUMBER(6),
    date_key          NUMBER(8),
    total_deposits_usd    NUMBER(18,2),
    total_withdrawals_usd NUMBER(18,2),
    txn_count             NUMBER(10),
    fraud_flag_count       NUMBER(10)
);


/* ============================================================================
   4. STORED PROCEDURE #1
      Simple lookup/reference load -> dw.dim_branch
      Lineage complexity: LOW (mostly 1:1 with a full refresh pattern)
   ============================================================================ */

CREATE OR REPLACE PROCEDURE dw.sp_load_dim_branch()
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    TRUNCATE TABLE dw.dim_branch;

    INSERT INTO dw.dim_branch (branch_id, branch_name, region, state_code, branch_type)
    SELECT
        b.branch_id,
        b.branch_name,
        b.region,
        b.state_code,
        b.branch_type
    FROM src.branches b;

    RETURN 'dim_branch load complete';
END;
$$;


/* ============================================================================
   5. STORED PROCEDURE #2
      Staging build with derived columns (age_band, full_name)
      Lineage complexity: MEDIUM (concatenation, CASE-derived buckets)
   ============================================================================ */

CREATE OR REPLACE PROCEDURE stg.sp_build_stg_customer_profile()
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    DELETE FROM stg.stg_customer_profile;

    INSERT INTO stg.stg_customer_profile (
        customer_id, full_name, email, state_code,
        customer_segment, age_band, is_active, load_ts
    )
    SELECT
        c.customer_id,
        c.first_name || ' ' || c.last_name                          AS full_name,
        LOWER(c.email)                                               AS email,
        c.state_code,
        c.customer_segment,
        CASE
            WHEN DATEDIFF(year, c.date_of_birth, CURRENT_DATE()) < 25 THEN 'UNDER_25'
            WHEN DATEDIFF(year, c.date_of_birth, CURRENT_DATE()) BETWEEN 25 AND 40 THEN '25_40'
            WHEN DATEDIFF(year, c.date_of_birth, CURRENT_DATE()) BETWEEN 41 AND 60 THEN '41_60'
            ELSE 'OVER_60'
        END                                                           AS age_band,
        c.is_active,
        CURRENT_TIMESTAMP()                                          AS load_ts
    FROM src.customers c
    WHERE c.created_date IS NOT NULL;

    RETURN 'stg_customer_profile build complete';
END;
$$;


/* ============================================================================
   6. STORED PROCEDURE #3
      SCD Type 2 MERGE into dw.dim_customer, sourced from staging (multi-hop
      lineage: src.customers -> stg.stg_customer_profile -> dw.dim_customer)
      Lineage complexity: HIGH (MERGE with conditional insert/update branches)
   ============================================================================ */

CREATE OR REPLACE PROCEDURE dw.sp_load_dim_customer_scd2()
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    -- Step 1: expire changed records
    UPDATE dw.dim_customer d
    SET end_date   = CURRENT_DATE() - 1,
        is_current = FALSE
    FROM stg.stg_customer_profile s
    WHERE d.customer_id = s.customer_id
      AND d.is_current = TRUE
      AND (
            d.full_name        <> s.full_name
         OR d.email             <> s.email
         OR d.state_code        <> s.state_code
         OR d.customer_segment  <> s.customer_segment
         OR d.age_band          <> s.age_band
         OR d.is_active         <> s.is_active
      );

    -- Step 2: insert new + changed records as new current rows
    INSERT INTO dw.dim_customer (
        customer_id, full_name, email, state_code,
        customer_segment, age_band, is_active,
        effective_date, end_date, is_current
    )
    SELECT
        s.customer_id,
        s.full_name,
        s.email,
        s.state_code,
        s.customer_segment,
        s.age_band,
        s.is_active,
        CURRENT_DATE()      AS effective_date,
        NULL                AS end_date,
        TRUE                AS is_current
    FROM stg.stg_customer_profile s
    LEFT JOIN dw.dim_customer d
        ON s.customer_id = d.customer_id
       AND d.is_current = TRUE
    WHERE d.customer_id IS NULL
       OR d.full_name        <> s.full_name
       OR d.email             <> s.email
       OR d.state_code        <> s.state_code
       OR d.customer_segment  <> s.customer_segment
       OR d.age_band          <> s.age_band
       OR d.is_active         <> s.is_active;

    RETURN 'dim_customer SCD2 load complete';
END;
$$;


/* ============================================================================
   7. STORED PROCEDURE #4
      Complex fact load using CTEs, multi-table joins, currency conversion,
      CASE-based categorization, window function for running balance, and
      a fraud-flag left join.
      Lineage complexity: VERY HIGH
      Sources: src.transactions, src.accounts, src.customers, src.exchange_rates,
               src.fraud_flags, dw.dim_customer, dw.dim_branch, dw.dim_date
      Target : dw.fact_transactions
   ============================================================================ */

CREATE OR REPLACE PROCEDURE dw.sp_load_fact_transactions(p_load_date DATE)
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    WITH txn_base AS (
        SELECT
            t.transaction_id,
            t.account_id,
            a.customer_id,
            a.branch_id,
            t.transaction_ts,
            CAST(t.transaction_ts AS DATE)                     AS transaction_date,
            t.transaction_type,
            t.channel,
            t.amount,
            t.currency_code,
            t.merchant_name
        FROM src.transactions t
        INNER JOIN src.accounts a
            ON t.account_id = a.account_id
        WHERE CAST(t.transaction_ts AS DATE) = p_load_date
          AND t.is_reversed = FALSE
    ),
    txn_fx AS (
        SELECT
            b.*,
            ROUND(b.amount * COALESCE(fx.rate_to_usd, 1.0), 2)  AS amount_usd
        FROM txn_base b
        LEFT JOIN src.exchange_rates fx
            ON b.currency_code = fx.currency_code
           AND b.transaction_date = fx.rate_date
    ),
    txn_categorized AS (
        SELECT
            f.*,
            CASE
                WHEN f.transaction_type = 'FEE'                                    THEN 'FEE_INCOME'
                WHEN f.transaction_type = 'INTEREST'                               THEN 'INTEREST_INCOME'
                WHEN f.transaction_type = 'DEPOSIT'  AND f.amount_usd >= 10000      THEN 'LARGE_DEPOSIT'
                WHEN f.transaction_type = 'DEPOSIT'                                THEN 'STANDARD_DEPOSIT'
                WHEN f.transaction_type = 'WITHDRAWAL' AND f.channel = 'ATM'       THEN 'ATM_WITHDRAWAL'
                WHEN f.transaction_type = 'WITHDRAWAL'                            THEN 'STANDARD_WITHDRAWAL'
                WHEN f.transaction_type = 'TRANSFER'                              THEN 'TRANSFER'
                ELSE 'OTHER'
            END AS txn_category,
            SUM(f.amount_usd) OVER (
                PARTITION BY f.account_id
                ORDER BY f.transaction_ts
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS running_balance_usd
        FROM txn_fx f
    ),
    txn_with_fraud AS (
        SELECT
            c.*,
            CASE WHEN ff.transaction_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_fraud_flagged
        FROM txn_categorized c
        LEFT JOIN (
            SELECT DISTINCT transaction_id
            FROM src.fraud_flags
            WHERE severity IN ('MEDIUM', 'HIGH')
        ) ff
            ON c.transaction_id = ff.transaction_id
    )
    INSERT INTO dw.fact_transactions (
        transaction_id, customer_key, branch_key, date_key,
        transaction_type, txn_category, channel, amount_usd,
        running_balance_usd, is_fraud_flagged, load_ts
    )
    SELECT
        t.transaction_id,
        dc.customer_key,
        db.branch_key,
        CAST(TO_CHAR(t.transaction_date, 'YYYYMMDD') AS NUMBER(8))  AS date_key,
        t.transaction_type,
        t.txn_category,
        t.channel,
        t.amount_usd,
        t.running_balance_usd,
        t.is_fraud_flagged,
        CURRENT_TIMESTAMP()                                         AS load_ts
    FROM txn_with_fraud t
    INNER JOIN dw.dim_customer dc
        ON t.customer_id = dc.customer_id
       AND dc.is_current = TRUE
    INNER JOIN dw.dim_branch db
        ON t.branch_id = db.branch_id;

    RETURN 'fact_transactions load complete for ' || p_load_date;
END;
$$;


/* ============================================================================
   8. STORED PROCEDURE #5
      Downstream aggregate built FROM the fact table (second-hop lineage:
      dw.fact_transactions -> dw.agg_daily_branch_summary)
      Lineage complexity: MEDIUM (aggregation with conditional SUM/COUNT)
   ============================================================================ */

CREATE OR REPLACE PROCEDURE dw.sp_load_agg_daily_branch_summary(p_load_date DATE)
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    DELETE FROM dw.agg_daily_branch_summary
    WHERE date_key = CAST(TO_CHAR(p_load_date, 'YYYYMMDD') AS NUMBER(8));

    INSERT INTO dw.agg_daily_branch_summary (
        branch_key, date_key, total_deposits_usd,
        total_withdrawals_usd, txn_count, fraud_flag_count
    )
    SELECT
        f.branch_key,
        f.date_key,
        SUM(CASE WHEN f.transaction_type = 'DEPOSIT' THEN f.amount_usd ELSE 0 END)    AS total_deposits_usd,
        SUM(CASE WHEN f.transaction_type = 'WITHDRAWAL' THEN f.amount_usd ELSE 0 END) AS total_withdrawals_usd,
        COUNT(*)                                                                       AS txn_count,
        SUM(CASE WHEN f.is_fraud_flagged THEN 1 ELSE 0 END)                            AS fraud_flag_count
    FROM dw.fact_transactions f
    WHERE f.date_key = CAST(TO_CHAR(p_load_date, 'YYYYMMDD') AS NUMBER(8))
    GROUP BY f.branch_key, f.date_key;

    RETURN 'agg_daily_branch_summary load complete for ' || p_load_date;
END;
$$;


/* ============================================================================
   9. ORCHESTRATION WRAPPER
      Calls the above procedures in dependency order -- useful for testing
      whether a lineage agent can trace call chains, not just single
      statements.
   ============================================================================ */

CREATE OR REPLACE PROCEDURE dw.sp_run_daily_etl(p_load_date DATE)
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    CALL dw.sp_load_dim_branch();
    CALL stg.sp_build_stg_customer_profile();
    CALL dw.sp_load_dim_customer_scd2();
    CALL dw.sp_load_fact_transactions(:p_load_date);
    CALL dw.sp_load_agg_daily_branch_summary(:p_load_date);

    RETURN 'Daily ETL orchestration complete for ' || p_load_date;
END;
$$;


/* ============================================================================
   10. STANDALONE COMPLEX VIEW (no procedure wrapper)
       Good for testing lineage extraction from plain SQL, not just
       procedural code. Includes a correlated subquery and a self-join.
   ============================================================================ */

CREATE OR REPLACE VIEW dw.vw_customer_high_value_flag AS
SELECT
    dc.customer_key,
    dc.customer_id,
    dc.full_name,
    dc.customer_segment,
    (
        SELECT SUM(ft.amount_usd)
        FROM dw.fact_transactions ft
        WHERE ft.customer_key = dc.customer_key
          AND ft.transaction_type = 'DEPOSIT'
    ) AS total_deposits_usd,
    CASE
        WHEN (
            SELECT SUM(ft2.amount_usd)
            FROM dw.fact_transactions ft2
            WHERE ft2.customer_key = dc.customer_key
              AND ft2.transaction_type = 'DEPOSIT'
        ) >= 100000 THEN 'HIGH_VALUE'
        ELSE 'STANDARD'
    END AS value_tier
FROM dw.dim_customer dc
WHERE dc.is_current = TRUE;
