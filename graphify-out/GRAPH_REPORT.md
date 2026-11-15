# Graph Report - ksero-adapter  (2026-11-15)

## Corpus Check
- 63 files · ~59,333 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 2, .ini 1, .lock 1)

## Summary
- 1219 nodes · 3490 edges · 68 communities (34 shown, 34 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 117 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `72292442`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Configuration validation
- Live database integration
- Service write tests
- Schema cache and types
- HTTP resource tests
- InvalidRequest
- Application wiring and errors
- SQL filtering and search
- Serialization and fixtures
- Agreement and CPC validation
- base.py
- Application settings and routing
- BaseDatabaseService
- YAML configuration
- Curated column validation
- Fake service facade
- Connection pool lifecycle
- create_router
- Documented write safeguards
- pool.py
- create_router
- test_cpc_sync.py
- Service schema error tests
- Client wire models
- WritesDisabled
- make_service
- Documented read safeguards
- parametrize
- schemas/__init__.py
- create_router
- Scripted database transactions
- create_router
- Decimal response contracts
- Reserved write transactions
- create_router
- .sync_cpc_from_machine
- migrate-firebird-2.5-to-5.sh
- OpenAPI browser tester
- Exception
- Database test isolation
- API tester delivery
- test_create_client_rolls_back_when_serialization_fails
- Locked uv dependencies
- Documented HTTP error mapping
- Adapter project overview
- schema.py
- _FakeCursor
- quote_identifier
- test_order_search_list_stays_within_the_firebird_message_limit
- test_create_machine_reuses_the_curated_column_lists
- require_api_key
- service/invoices.py
- service/orders.py

## God Nodes (most connected - your core abstractions)
1. `_Pool` - 160 edges
2. `make_projection_service()` - 138 edges
3. `DatabaseService` - 96 edges
4. `FakeService` - 94 edges
5. `create_app()` - 86 edges
6. `InvalidRequest` - 62 edges
7. `make_settings()` - 54 edges
8. `TableInfo` - 52 edges
9. `load_config()` - 41 edges
10. `AppSettings` - 40 edges

## Surprising Connections (you probably didn't know these)
- `Read-only reads` --references--> `ensure_read_only()`  [EXTRACTED]
  AGENTS.md → adapter/sql.py
- `Central database service` --references--> `DatabaseService`  [EXTRACTED]
  AGENTS.md → adapter/service/__init__.py
- `Shared pool and schema cache` --references--> `DatabaseService`  [EXTRACTED]
  docs/ARCHITECTURE.md → adapter/service/__init__.py
- `Shared pool and schema cache` --references--> `BaseDatabaseService`  [EXTRACTED]
  docs/ARCHITECTURE.md → adapter/service/base.py
- `Atomic write transactions` --references--> `ConnectionPool`  [EXTRACTED]
  docs/ARCHITECTURE.md → adapter/pool.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Agreement allocation and linking** — docs_architecture_protected_agreement_reservation, docs_architecture_lowest_unused_agreement_id, docs_architecture_atomic_machine_link_replacement [EXTRACTED 1.00]
- **Curated write safety** — docs_configuration_opt_in_write_enablement, agents_bound_sql_values, docs_architecture_atomic_write_transactions, agents_sql_and_transaction_assertions [EXTRACTED 1.00]

## Communities (68 total, 34 thin omitted)

### Community 0 - "Configuration validation"
Cohesion: 0.07
Nodes (52): _apply_env_overrides(), _bool(), _build_settings(), _check_keys(), ConfigError, _database_settings(), _expand_env(), _float() (+44 more)

### Community 1 - "Live database integration"
Cohesion: 0.06
Nodes (64): ApiSettings, DatabaseSettings, resolve_database_path(), DatabaseService, Central database service, delete_agreement(), delete_client(), delete_machine() (+56 more)

### Community 2 - "Service write tests"
Cohesion: 0.07
Nodes (73): _client_insert(), make_projection_service(), _Pool, test_create_agreement_binds_values_and_merges_legacy_defaults(), test_create_agreement_default_payment_profile(), test_create_agreement_requires_business_and_client_columns(), test_create_agreement_requires_write_permission(), test_create_agreement_reserves_table_before_allocating_id() (+65 more)

### Community 3 - "Schema cache and types"
Cohesion: 0.12
Nodes (14): TableNotFound, describe_type(), SchemaCache, _FakePool, test_describe_type_blobs(), test_describe_type_numerics(), test_describe_type_plain_types(), test_describe_type_strings_respect_charset_width() (+6 more)

### Community 4 - "HTTP resource tests"
Cohesion: 0.07
Nodes (53): test_agreement_machines_required_only_for_creation(), test_agreements_endpoint(), test_agreements_endpoint_defaults(), test_agreements_rejects_out_of_range_limit(), test_clients_endpoint(), test_clients_endpoint_defaults(), test_clients_rejects_out_of_range_limit(), test_cpc_create_schema_derives_client_from_agreement() (+45 more)

### Community 5 - "InvalidRequest"
Cohesion: 0.09
Nodes (6): InvalidRequest, AgreementsService, ClientsService, CpcSettlementService, build_update(), test_build_update_quotes_identifiers_and_requires_assignments()

### Community 6 - "Application wiring and errors"
Cohesion: 0.09
Nodes (30): create_app(), client(), fake_service(), make_settings(), settings(), test_agreements_requires_api_key(), test_all_cpc_routes_require_api_key(), test_api_key_is_enforced_when_configured() (+22 more)

### Community 7 - "SQL filtering and search"
Cohesion: 0.10
Nodes (29): build_next_available_id(), build_search(), build_where(), Filter, _like_pattern(), parse_filters(), _scalar(), test_build_search_accepts_exactly_the_budgeted_number_of_columns() (+21 more)

### Community 8 - "Serialization and fixtures"
Cohesion: 0.14
Nodes (16): row_to_dict(), serialize_rows(), to_jsonable(), unique_column_names(), test_binary_blob_falls_back_to_base64(), test_bytearray_and_memoryview_are_supported(), test_bytes_are_decoded_with_configured_encoding(), test_datetime_conversion() (+8 more)

### Community 9 - "Agreement and CPC validation"
Cohesion: 0.11
Nodes (31): test_agreement_service_rejects_invalid_machine_arrays(), test_cpc_database_failure_rolls_back(), test_cpc_validates_record_key(), test_cpc_writes_are_disabled_by_default(), test_create_agreement_allocation_failure_rolls_back(), test_create_agreement_rejects_invalid_payload(), test_create_cpc_defaults_missing_period_from_database_date(), test_create_cpc_rejects_invalid_agreement_before_insert() (+23 more)

### Community 10 - "base.py"
Cohesion: 0.11
Nodes (15): AdapterError, ColumnNotFound, DatabaseUnavailable, QueryNotAllowed, RecordConflict, RecordNotFound, _insert_plan(), _insert_cpc_on_cursor() (+7 more)

### Community 11 - "Application settings and routing"
Cohesion: 0.21
Nodes (3): AppSettings, get_service(), page_limit()

### Community 13 - "YAML configuration"
Cohesion: 0.05
Nodes (40): api, allow_writes, api_key, blob_encoding, cors_origins, decimal_as_string, default_limit, max_limit (+32 more)

### Community 14 - "Curated column validation"
Cohesion: 0.12
Nodes (28): ColumnInfo, TableInfo, test_secondary_database_queries_are_isolated_and_parameterized(), test_create_agreement_defaults_number_to_generated_id_and_current_year(), test_create_agreement_defaults_start_date_and_active_flag(), test_create_agreement_preserves_supplied_date_and_active_flag(), test_create_client_requires_the_name_column(), test_create_client_skips_columns_missing_from_the_schema() (+20 more)

### Community 18 - "Documented write safeguards"
Cohesion: 0.16
Nodes (11): SQL and transaction assertions, Lowest unused agreement ID, Opt-in write enablement, Resource API key authentication, Agreement CRUD, Client CRUD, Database current date defaults, Legacy delete cascades (+3 more)

### Community 20 - "create_router"
Cohesion: 0.14
Nodes (5): create_router(), Agreement, AgreementCreate, AgreementPage, AgreementUpdate

### Community 21 - "test_cpc_sync.py"
Cohesion: 0.16
Nodes (16): replace(), make_sync_service(), test_sync_accepts_inclusive_date_boundaries(), test_sync_failures_roll_back_without_insert(), test_sync_rejects_ineligible_reading_date_without_writing(), test_sync_rejects_missing_reading_date_without_writing(), test_sync_rejects_reversed_range_before_database_access(), test_sync_requires_valid_dates_in_http_query() (+8 more)

### Community 22 - "Service schema error tests"
Cohesion: 0.20
Nodes (6): _StubSchema, test_create_agreement_link_failure_rolls_back(), test_create_agreement_links_machines_in_same_transaction(), test_update_agreement_can_link_machines_without_changing_columns(), test_update_agreement_empty_machine_array_clears_all_links(), test_update_agreement_updates_supplied_fields_and_links_machines()

### Community 23 - "Client wire models"
Cohesion: 0.15
Nodes (5): create_router(), Client, ClientCreate, ClientPage, ClientUpdate

### Community 24 - "WritesDisabled"
Cohesion: 0.25
Nodes (9): WritesDisabled, test_create_agreement_reports_disabled_writes(), create_agreement(), test_create_client_reports_disabled_writes_as_403(), create_client(), test_create_machine_reports_disabled_writes_as_403(), create_machine(), test_machine_client_path_respects_write_gate() (+1 more)

### Community 25 - "make_service"
Cohesion: 0.12
Nodes (17): make_service(), make_settings(), test_describe_table_includes_columns(), test_fetch_rows_builds_count_and_page_queries(), test_fetch_rows_serialises_decimals_and_dates(), test_fetch_rows_uses_default_limit(), test_fetch_rows_validates_limit_and_offset(), test_fetch_rows_validates_order_by() (+9 more)

### Community 26 - "Documented read safeguards"
Cohesion: 0.14
Nodes (4): Firebird JSON serialization, TTL catalog whitelist, FastAPI Firebird gateway, Native Firebird client

### Community 27 - "parametrize"
Cohesion: 0.21
Nodes (15): test_agreement_routes_validate_machine_arrays(), test_create_agreement_rejects_invalid_fields(), test_create_agreement_requires_machines_array(), test_create_cpc_accepts_optional_period(), test_create_cpc_does_not_require_client(), test_create_cpc_validates_input(), test_create_machine_rejects_invalid_required_identity(), test_create_machine_reports_missing_client() (+7 more)

### Community 28 - "schemas/__init__.py"
Cohesion: 0.09
Nodes (13): create_router(), service_info(), Cpc, CpcCreate, CpcPage, CpcUpdate, CpcValues, Invoice (+5 more)

### Community 29 - "create_router"
Cohesion: 0.11
Nodes (8): create_router(), create_client_machine(), DatabaseMachine, DatabaseMachinePage, Machine, MachineCreate, MachinePage, MachineUpdate

### Community 32 - "Decimal response contracts"
Cohesion: 0.17
Nodes (5): test_agreements_accepts_decimal_strings(), fake_fetch(), test_invoices_accepts_decimal_strings(), test_machines_accepts_decimal_strings(), test_orders_accepts_decimal_strings()

### Community 33 - "Reserved write transactions"
Cohesion: 0.13
Nodes (8): _configure_macos_transactions(), _ClientAPI, _Connection, _Pool, test_macos_transaction_binding_preserves_handles_and_tpb(), test_macos_transaction_binding_rejects_multiple_database_arguments(), test_reserved_write_failure_rolls_back(), test_reserved_write_starts_after_rollback_and_commits()

### Community 34 - "create_router"
Cohesion: 0.20
Nodes (3): create_router(), Order, OrderPage

### Community 36 - "migrate-firebird-2.5-to-5.sh"
Cohesion: 0.36
Nodes (7): checksum(), die(), ISC_USER, run25(), run5(), migrate-firebird-2.5-to-5.sh script, usage()

### Community 39 - "OpenAPI browser tester"
Cohesion: 0.33
Nodes (6): Abortable requests, Editable JSON request body, In-memory API key, OpenAPI-driven route forms, Public API tester, Public metadata and health routes

### Community 40 - "Exception"
Cohesion: 0.10
Nodes (10): _adapter_error_handler(), _firebird_error_handler(), test_cpc_write_errors_are_rendered(), test_delete_agreement_maps_service_errors(), test_delete_client_reports_domain_errors(), test_delete_machine_maps_service_errors(), test_update_agreement_reports_domain_errors(), test_update_client_reports_domain_errors() (+2 more)

### Community 52 - "schema.py"
Cohesion: 0.22
Nodes (4): _char_length(), _clean_text(), _optional_int(), _row_dict()

### Community 56 - "quote_identifier"
Cohesion: 0.20
Nodes (5): build_delete(), quote_identifier(), test_build_delete_quotes_identifiers_and_binds_the_key(), test_quote_identifier(), test_quote_identifier_rejects_empty()

### Community 62 - "require_api_key"
Cohesion: 0.25
Nodes (4): create_router(), AuthenticationError, require_api_key(), check_api_key()

## Knowledge Gaps
- **16 isolated node(s):** `ISC_USER`, `ks-adapter`, `Project-relative database path`, `Central database service`, `SQL and transaction assertions` (+11 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 371 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **34 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AppSettings` connect `Application settings and routing` to `Configuration validation`, `Live database integration`, `create_router`, `Schema cache and types`, `Service write tests`, `Application wiring and errors`, `base.py`, `Connection pool lifecycle`, `create_router`, `create_router`, `Client wire models`, `make_service`, `schemas/__init__.py`, `create_router`, `require_api_key`, `create_router`?**
  _High betweenness centrality (0.099) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `create_app()` (e.g. with `_adapter_error_handler()` and `lifespan()`) actually correct?**
  _`create_app()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ISC_USER`, `ks-adapter`, `Project-relative database path` to the rest of the system?**
  _16 weakly-connected nodes found - possible missing edges._
- **Should `Configuration validation` be split into smaller, more focused modules?**
  _Cohesion score 0.06639427987742594 - nodes in this community are weakly interconnected._
- **Why does `DatabaseService` connect `Live database integration` to `Configuration validation`, `service/orders.py`, `Service write tests`, `.sync_cpc_from_machine`, `InvalidRequest`, `Application wiring and errors`, `Application settings and routing`, `BaseDatabaseService`, `Curated column validation`, `Connection pool lifecycle`, `test_cpc_sync.py`, `make_service`, `Documented read safeguards`, `service/invoices.py`?**
  _High betweenness centrality (0.091) - this node is a cross-community bridge._
- **Should `Live database integration` be split into smaller, more focused modules?**
  _Cohesion score 0.06446886446886448 - nodes in this community are weakly interconnected._
- **Why does `InvalidRequest` connect `InvalidRequest` to `Service write tests`, `.sync_cpc_from_machine`, `HTTP resource tests`, `SQL filtering and search`, `base.py`, `Application settings and routing`, `BaseDatabaseService`, `test_cpc_sync.py`, `quote_identifier`, `create_router`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._