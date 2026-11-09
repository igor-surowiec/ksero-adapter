# Graph Report - ksero-adapter  (2026-11-09)

## Corpus Check
- 55 files · ~50,783 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 3 file(s) not represented in the graph (top: (none) 1, .ini 1, .lock 1)

## Summary
- 1093 nodes · 3203 edges · 50 communities (34 shown, 16 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 274 edges (avg confidence: 0.94)
- Token cost: unavailable for host-agent semantic extraction; no external LLM API calls were made. AST extraction uses no LLM tokens.

## Community Hubs (Navigation)
- Configuration validation
- Live database integration
- Service write tests
- Schema cache and types
- HTTP resource tests
- Resource mutation services
- Application wiring and errors
- SQL filtering and search
- Serialization and fixtures
- Agreement and CPC validation
- Service modules and errors
- Application settings and routing
- Shared query execution
- YAML configuration
- Curated column validation
- Fake service facade
- Connection pool lifecycle
- CPC wire models
- Documented write safeguards
- Firebird driver transactions
- Agreement wire models
- Authentication and error rendering
- Service schema error tests
- Client wire models
- Machine wire models
- Generic query tests
- Documented read safeguards
- HTTP write payload tests
- Public metadata models
- Order wire models
- Scripted database transactions
- Invoice wire models
- Decimal response contracts
- Reserved write transactions
- Write permission gate
- Agreement machine linking
- Database connection settings
- Invoice read service
- Order read service
- OpenAPI browser tester
- Parameterized insert builder
- Database test isolation
- API tester delivery
- Serialization rollback tests
- Locked uv dependencies
- Search parameter budget
- Curated machine payloads
- Documented HTTP error mapping
- Adapter project overview

## God Nodes (most connected - your core abstractions)
1. `_Pool` - 152 edges
2. `make_projection_service()` - 136 edges
3. `InvalidRequest` - 101 edges
4. `FakeService` - 94 edges
5. `DatabaseService` - 83 edges
6. `create_app()` - 76 edges
7. `TableInfo` - 46 edges
8. `BaseDatabaseService` - 42 edges
9. `make_settings()` - 42 edges
10. `RecordNotFound` - 39 edges

## Surprising Connections (you probably didn't know these)
- `Read-only reads` --references--> `ensure_read_only()`  [EXTRACTED]
  AGENTS.md → adapter/sql.py
- `Lazy database startup` --references--> `create_app()`  [EXTRACTED]
  docs/ARCHITECTURE.md → adapter/app.py
- `Immutable whitelisted configuration` --references--> `load_config()`  [EXTRACTED]
  docs/ARCHITECTURE.md → adapter/config.py
- `Atomic write transactions` --references--> `ConnectionPool`  [EXTRACTED]
  docs/ARCHITECTURE.md → adapter/pool.py
- `Bounded connection pool` --references--> `ConnectionPool`  [EXTRACTED]
  docs/ARCHITECTURE.md → adapter/pool.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Curated write safety** — docs_configuration_opt_in_write_enablement, agents_bound_sql_values, docs_architecture_atomic_write_transactions, agents_sql_and_transaction_assertions [EXTRACTED 1.00]
- **Agreement allocation and linking** — docs_architecture_protected_agreement_reservation, docs_architecture_lowest_unused_agreement_id, docs_architecture_atomic_machine_link_replacement [EXTRACTED 1.00]

## Communities (50 total, 16 thin omitted)

### Community 0 - "Configuration validation"
Cohesion: 0.07
Nodes (48): ApiSettings, _apply_env_overrides(), _bool(), _build_settings(), _check_keys(), ConfigError, _expand_env(), replace() (+40 more)

### Community 1 - "Live database integration"
Cohesion: 0.08
Nodes (58): DatabaseService, Central database service, delete_agreement(), delete_client(), delete_machine(), first_table(), service(), test_agreement_links_reject_duplicate_machine_business_ids() (+50 more)

### Community 2 - "Service write tests"
Cohesion: 0.07
Nodes (68): _client_insert(), make_projection_service(), _Pool, test_create_agreement_binds_values_and_merges_legacy_defaults(), test_create_agreement_default_payment_profile(), test_create_agreement_requires_business_and_client_columns(), test_create_agreement_requires_write_permission(), test_create_agreement_reserves_table_before_allocating_id() (+60 more)

### Community 3 - "Schema cache and types"
Cohesion: 0.07
Nodes (19): _char_length(), _clean_text(), describe_type(), _optional_int(), _row_dict(), SchemaCache, _FakeConnection, _FakeCursor (+11 more)

### Community 4 - "HTTP resource tests"
Cohesion: 0.07
Nodes (51): test_agreement_machines_required_only_for_creation(), test_agreements_endpoint(), test_agreements_endpoint_defaults(), test_agreements_rejects_out_of_range_limit(), test_clients_endpoint(), test_clients_endpoint_defaults(), test_clients_rejects_out_of_range_limit(), test_cpc_create_schema_derives_client_from_agreement() (+43 more)

### Community 5 - "Resource mutation services"
Cohesion: 0.10
Nodes (6): InvalidRequest, RecordConflict, RecordNotFound, ClientsService, CpcSettlementService, MachinesService

### Community 6 - "Application wiring and errors"
Cohesion: 0.08
Nodes (30): create_app(), make_settings(), test_agreements_requires_api_key(), test_all_cpc_routes_require_api_key(), test_api_key_is_enforced_when_configured(), test_api_tester_is_html_at_exact_prefix_without_db_access(), test_clients_requires_api_key(), test_cors_allows_client_delete() (+22 more)

### Community 7 - "SQL filtering and search"
Cohesion: 0.09
Nodes (30): build_next_available_id(), build_search(), build_where(), Filter, _like_pattern(), parse_filters(), _scalar(), test_build_delete_quotes_identifiers_and_binds_the_key() (+22 more)

### Community 8 - "Serialization and fixtures"
Cohesion: 0.10
Nodes (19): row_to_dict(), serialize_rows(), to_jsonable(), unique_column_names(), client(), fake_service(), settings(), test_binary_blob_falls_back_to_base64() (+11 more)

### Community 9 - "Agreement and CPC validation"
Cohesion: 0.10
Nodes (32): test_agreement_service_rejects_invalid_machine_arrays(), test_cpc_database_failure_rolls_back(), test_cpc_validates_record_key(), test_cpc_writes_are_disabled_by_default(), test_create_agreement_allocation_failure_rolls_back(), test_create_agreement_defaults_number_to_generated_id_and_current_year(), test_create_agreement_defaults_start_date_and_active_flag(), test_create_agreement_rejects_invalid_payload() (+24 more)

### Community 10 - "Service modules and errors"
Cohesion: 0.14
Nodes (11): ColumnNotFound, DatabaseUnavailable, QueryNotAllowed, _insert_plan(), build_delete(), build_update(), ensure_read_only(), strip_sql_literals() (+3 more)

### Community 11 - "Application settings and routing"
Cohesion: 0.19
Nodes (3): AppSettings, get_service(), page_limit()

### Community 12 - "Shared query execution"
Cohesion: 0.10
Nodes (4): BaseDatabaseService, quote_identifier(), test_quote_identifier(), test_quote_identifier_rejects_empty()

### Community 13 - "YAML configuration"
Cohesion: 0.07
Nodes (27): api, allow_writes, api_key, blob_encoding, cors_origins, decimal_as_string, default_limit, max_limit (+19 more)

### Community 14 - "Curated column validation"
Cohesion: 0.15
Nodes (23): ColumnInfo, TableInfo, test_create_agreement_preserves_supplied_date_and_active_flag(), test_create_client_requires_the_name_column(), test_create_client_skips_columns_missing_from_the_schema(), test_create_machine_requires_the_owner_column(), test_create_machine_skips_columns_missing_from_the_schema(), test_create_machine_uses_full_legacy_profile_and_caller_overrides() (+15 more)

### Community 17 - "CPC wire models"
Cohesion: 0.13
Nodes (6): create_router(), Cpc, CpcCreate, CpcPage, CpcUpdate, CpcValues

### Community 18 - "Documented write safeguards"
Cohesion: 0.16
Nodes (11): SQL and transaction assertions, Lowest unused agreement ID, Opt-in write enablement, Resource API key authentication, Agreement CRUD, Client CRUD, Database current date defaults, Legacy delete cascades (+3 more)

### Community 19 - "Firebird driver transactions"
Cohesion: 0.16
Nodes (5): _configure_macos_transactions(), connect(), _ClientAPI, test_macos_transaction_binding_preserves_handles_and_tpb(), test_macos_transaction_binding_rejects_multiple_database_arguments()

### Community 20 - "Agreement wire models"
Cohesion: 0.14
Nodes (5): create_router(), Agreement, AgreementCreate, AgreementPage, AgreementUpdate

### Community 21 - "Authentication and error rendering"
Cohesion: 0.13
Nodes (7): create_router(), _adapter_error_handler(), _firebird_error_handler(), AdapterError, AuthenticationError, require_api_key(), check_api_key()

### Community 22 - "Service schema error tests"
Cohesion: 0.12
Nodes (13): TableNotFound, _StubSchema, test_create_agreement_link_failure_rolls_back(), test_create_agreement_links_machines_in_same_transaction(), test_fetch_agreements_validates_arguments(), test_fetch_clients_validates_arguments(), test_fetch_invoices_validates_arguments(), test_fetch_machines_validates_arguments() (+5 more)

### Community 23 - "Client wire models"
Cohesion: 0.15
Nodes (5): create_router(), Client, ClientCreate, ClientPage, ClientUpdate

### Community 24 - "Machine wire models"
Cohesion: 0.15
Nodes (6): create_router(), create_client_machine(), Machine, MachineCreate, MachinePage, MachineUpdate

### Community 25 - "Generic query tests"
Cohesion: 0.12
Nodes (17): make_service(), make_settings(), test_describe_table_includes_columns(), test_fetch_rows_builds_count_and_page_queries(), test_fetch_rows_serialises_decimals_and_dates(), test_fetch_rows_uses_default_limit(), test_fetch_rows_validates_limit_and_offset(), test_fetch_rows_validates_order_by() (+9 more)

### Community 26 - "Documented read safeguards"
Cohesion: 0.14
Nodes (4): Firebird JSON serialization, TTL catalog whitelist, FastAPI Firebird gateway, Native Firebird client

### Community 27 - "HTTP write payload tests"
Cohesion: 0.24
Nodes (13): test_agreement_routes_validate_machine_arrays(), test_create_agreement_rejects_invalid_fields(), test_create_agreement_requires_machines_array(), test_create_cpc_accepts_optional_period(), test_create_cpc_does_not_require_client(), test_create_cpc_validates_input(), test_create_machine_reports_missing_client(), create_machine() (+5 more)

### Community 28 - "Public metadata models"
Cohesion: 0.24
Nodes (6): create_router(), service_info(), DatabaseInfo, HealthResponse, PoolInfo, ServiceInfo

### Community 29 - "Order wire models"
Cohesion: 0.17
Nodes (3): create_router(), Order, OrderPage

### Community 31 - "Invoice wire models"
Cohesion: 0.18
Nodes (3): create_router(), Invoice, InvoicePage

### Community 32 - "Decimal response contracts"
Cohesion: 0.17
Nodes (5): test_agreements_accepts_decimal_strings(), fake_fetch(), test_invoices_accepts_decimal_strings(), test_machines_accepts_decimal_strings(), test_orders_accepts_decimal_strings()

### Community 33 - "Reserved write transactions"
Cohesion: 0.18
Nodes (4): _Connection, _Pool, test_reserved_write_failure_rolls_back(), test_reserved_write_starts_after_rollback_and_commits()

### Community 34 - "Write permission gate"
Cohesion: 0.25
Nodes (9): WritesDisabled, test_create_agreement_reports_disabled_writes(), create_agreement(), test_create_client_reports_disabled_writes_as_403(), create_client(), test_create_machine_reports_disabled_writes_as_403(), create_machine(), test_machine_client_path_respects_write_gate() (+1 more)

### Community 39 - "OpenAPI browser tester"
Cohesion: 0.33
Nodes (6): Abortable requests, Editable JSON request body, In-memory API key, OpenAPI-driven route forms, Public API tester, Public metadata and health routes

### Community 40 - "Parameterized insert builder"
Cohesion: 0.50
Nodes (3): build_insert(), test_build_insert_quotes_identifiers_and_binds_values(), test_build_insert_requires_a_column()

## Knowledge Gaps
- **15 isolated node(s):** `ks-adapter`, `Central database service`, `Offline fake database testing`, `SQL and transaction assertions`, `Locked uv environment` (+10 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 314 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AppSettings` connect `Application settings and routing` to `Configuration validation`, `Live database integration`, `Service write tests`, `Schema cache and types`, `Application wiring and errors`, `Serialization and fixtures`, `Service modules and errors`, `Shared query execution`, `CPC wire models`, `Agreement wire models`, `Authentication and error rendering`, `Client wire models`, `Machine wire models`, `Generic query tests`, `Public metadata models`, `Order wire models`, `Invoice wire models`?**
  _High betweenness centrality (0.115) - this node is a cross-community bridge._
- **Are the 53 inferred relationships involving `InvalidRequest` (e.g. with `AgreementsService` and `BaseDatabaseService`) actually correct?**
  _`InvalidRequest` has 53 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ks-adapter`, `Central database service`, `Offline fake database testing` to the rest of the system?**
  _15 weakly-connected nodes found - possible missing edges._
- **Should `Configuration validation` be split into smaller, more focused modules?**
  _Cohesion score 0.07425907425907426 - nodes in this community are weakly interconnected._
- **Why does `InvalidRequest` connect `Resource mutation services` to `Service write tests`, `Agreement machine linking`, `HTTP resource tests`, `SQL filtering and search`, `Parameterized insert builder`, `Agreement and CPC validation`, `Service modules and errors`, `Application settings and routing`, `Shared query execution`, `Curated column validation`, `Authentication and error rendering`, `Service schema error tests`, `Machine wire models`, `Generic query tests`?**
  _High betweenness centrality (0.107) - this node is a cross-community bridge._
- **Are the 50 inferred relationships involving `FakeService` (e.g. with `test_agreements_accepts_decimal_strings()` and `test_agreements_endpoint()`) actually correct?**
  _`FakeService` has 50 INFERRED edges - model-reasoned connections that need verification._
- **Should `Live database integration` be split into smaller, more focused modules?**
  _Cohesion score 0.07559107559107558 - nodes in this community are weakly interconnected._
## Generation notes

- Shared graph outputs are versioned in `graphify-out/`; caches, usage data, and machine-specific state are ignored.
- Integrity warning: raw extraction has 177 dangling-endpoint edges and 2 self-loop edges. The default undirected graph collapses 215 same-endpoint relationships. The graph is useful but does not preserve every raw relationship.
- `GRAPH_EXTRACTION.json` preserves the raw AST and semantic results; `GRAPH_HEALTH.json` records the complete diagnostic.
- All seven documents were read completely. The ignored Firebird database was excluded.
