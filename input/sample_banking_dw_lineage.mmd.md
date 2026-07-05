```mermaid
flowchart LR
    table_dw_dim_branch["dw.dim_branch"]
    table_src_branches["src.branches"]
    table_stg_stg_customer_profile["stg.stg_customer_profile"]
    table_src_customers["src.customers"]
    table_dw_dim_customer["dw.dim_customer"]
    table_dw_agg_daily_branch_summary["dw.agg_daily_branch_summary"]
    table_dw_fact_transactions["dw.fact_transactions"]
    table_dw_vw_customer_high_value_flag["dw.vw_customer_high_value_flag"]
    table_src_branches --> table_dw_dim_branch
    table_stg_stg_customer_profile --> table_dw_dim_customer
    table_stg_stg_customer_profile --> table_dw_vw_customer_high_value_flag
    table_src_customers --> table_stg_stg_customer_profile
    table_src_customers --> table_dw_dim_customer
    table_src_customers --> table_dw_vw_customer_high_value_flag
    table_dw_dim_customer --> table_dw_vw_customer_high_value_flag
    table_dw_fact_transactions --> table_dw_vw_customer_high_value_flag
    table_dw_fact_transactions --> table_dw_agg_daily_branch_summary
```
