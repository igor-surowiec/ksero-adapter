# Graph Report - ksero-adapter  (2026-11-15)

## Corpus Check
- 61 files · ~55,676 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 3 file(s) not represented in the graph (top: (none) 1, .ini 1, .lock 1)

## Summary
- 1169 nodes · 3384 edges · 54 communities (31 shown, 23 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 254 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `bcf1fd2e`
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
- Shared query execution
- YAML configuration
- Curated column validation
- Fake service facade
- Connection pool lifecycle
- CPC wire models
- Documented write safeguards
- Firebird driver transactions
- Agreement wire models
- AdapterError
- Service schema error tests
- Client wire models
- create_router
- test_service.py
- Documented read safeguards
- parametrize
- create_router
- routes/machines.py
- Scripted database transactions
- pydantic
- Decimal response contracts
- Reserved write transactions
- service/machines_database.py
- test_machines_database.py
- migrate-firebird-2.5-to-5.sh
- OpenAPI browser tester
- quote_identifier
- Database test isolation
- API tester delivery
- Serialization rollback tests
- Locked uv dependencies
- Curated paginated projections
- Documented HTTP error mapping
- Adapter project overview
- service/invoices.py

## God Nodes (most connected - your core abstractions)
1. `_Pool` - 156 edges
2. `make_projection_service()` - 136 edges
3. `InvalidRequest` - 100 edges
4. `FakeService` - 98 edges
5. `DatabaseService` - 92 edges
6. `create_app()` - 80 edges
7. `make_settings()` - 48 edges
8. `TableInfo` - 47 edges
9. `load_config()` - 41 edges
10. `AppSettings` - 40 edges

## Surprising Connections (you probably didn't know these)
- `Read-only reads` --references--> `ensure_read_only()`  [EXTRACTED]
  AGENTS.md → adapter/sql.py
- `Lazy database startup` --references--> `create_app()`  [EXTRACTED]
  docs/ARCHITECTURE.md → adapter/app.py
- `Central database service` --references--> `DatabaseService`  [EXTRACTED]
  AGENTS.md → adapter/service/__init__.py
- `Shared pool and schema cache` --references--> `DatabaseService`  [EXTRACTED]
  docs/ARCHITECTURE.md → adapter/service/__init__.py
- `Shared pool and schema cache` --references--> `BaseDatabaseService`  [EXTRACTED]
  docs/ARCHITECTURE.md → adapter/service/base.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Agreement allocation and linking** — docs_architecture_protected_agreement_reservation, docs_architecture_lowest_unused_agreement_id, docs_architecture_atomic_machine_link_replacement [EXTRACTED 1.00]
- **Curated write safety** — docs_configuration_opt_in_write_enablement, agents_bound_sql_values, docs_architecture_atomic_write_transactions, agents_sql_and_transaction_assertions [EXTRACTED 1.00]

## Communities (54 total, 23 thin omitted)

### Community 0 - "Configuration validation"
Cohesion: 0.07
Nodes (53): _apply_env_overrides(), _bool(), _build_settings(), _check_keys(), ConfigError, _database_settings(), _expand_env(), replace() (+45 more)

### Community 1 - "Live database integration"
Cohesion: 0.06
Nodes (63): ApiSettings, DatabaseSettings, resolve_database_path(), DatabaseService, Central database service, delete_agreement(), delete_client(), delete_machine() (+55 more)

### Community 2 - "Service write tests"
Cohesion: 0.07
Nodes (53): WritesDisabled, make_projection_service(), _Pool, test_cpc_writes_are_disabled_by_default(), test_create_agreement_binds_values_and_merges_legacy_defaults(), test_create_agreement_default_payment_profile(), test_create_agreement_requires_business_and_client_columns(), test_create_agreement_requires_write_permission() (+45 more)

### Community 3 - "Schema cache and types"
Cohesion: 0.07
Nodes (19): _char_length(), _clean_text(), describe_type(), _optional_int(), _row_dict(), SchemaCache, _FakeConnection, _FakeCursor (+11 more)

### Community 4 - "HTTP resource tests"
Cohesion: 0.07
Nodes (51): test_agreement_machines_required_only_for_creation(), test_agreements_endpoint(), test_agreements_endpoint_defaults(), test_agreements_rejects_out_of_range_limit(), test_clients_endpoint(), test_clients_endpoint_defaults(), test_clients_rejects_out_of_range_limit(), test_cpc_create_schema_derives_client_from_agreement() (+43 more)

### Community 5 - "InvalidRequest"
Cohesion: 0.09
Nodes (8): DatabaseUnavailable, InvalidRequest, RecordConflict, RecordNotFound, AgreementsService, ClientsService, CpcSettlementService, MachinesService

### Community 6 - "Application wiring and errors"
Cohesion: 0.09
Nodes (31): create_app(), make_settings(), test_agreements_requires_api_key(), test_all_cpc_routes_require_api_key(), test_api_key_is_enforced_when_configured(), test_api_tester_is_html_at_exact_prefix_without_db_access(), test_clients_requires_api_key(), test_cors_allows_client_delete() (+23 more)

### Community 7 - "SQL filtering and search"
Cohesion: 0.09
Nodes (31): build_next_available_id(), build_search(), build_where(), Filter, _like_pattern(), parse_filters(), _scalar(), test_build_delete_quotes_identifiers_and_binds_the_key() (+23 more)

### Community 8 - "Serialization and fixtures"
Cohesion: 0.14
Nodes (16): row_to_dict(), serialize_rows(), to_jsonable(), unique_column_names(), test_binary_blob_falls_back_to_base64(), test_bytearray_and_memoryview_are_supported(), test_bytes_are_decoded_with_configured_encoding(), test_datetime_conversion() (+8 more)

### Community 9 - "Agreement and CPC validation"
Cohesion: 0.12
Nodes (28): test_agreement_service_rejects_invalid_machine_arrays(), test_cpc_database_failure_rolls_back(), test_cpc_validates_record_key(), test_create_agreement_allocation_failure_rolls_back(), test_create_agreement_rejects_invalid_payload(), test_create_cpc_defaults_missing_period_from_database_date(), test_create_cpc_rejects_invalid_agreement_before_insert(), test_create_cpc_rejects_invalid_input() (+20 more)

### Community 10 - "base.py"
Cohesion: 0.13
Nodes (12): ColumnNotFound, QueryNotAllowed, _insert_plan(), build_delete(), build_insert(), build_update(), ensure_read_only(), strip_sql_literals() (+4 more)

### Community 11 - "Application settings and routing"
Cohesion: 0.13
Nodes (5): create_router(), AppSettings, get_service(), page_limit(), create_router()

### Community 13 - "YAML configuration"
Cohesion: 0.05
Nodes (40): api, allow_writes, api_key, blob_encoding, cors_origins, decimal_as_string, default_limit, max_limit (+32 more)

### Community 14 - "Curated column validation"
Cohesion: 0.12
Nodes (28): ColumnInfo, TableInfo, test_secondary_database_queries_are_isolated_and_parameterized(), test_create_agreement_defaults_number_to_generated_id_and_current_year(), test_create_agreement_defaults_start_date_and_active_flag(), test_create_agreement_preserves_supplied_date_and_active_flag(), test_create_client_requires_the_name_column(), test_create_client_skips_columns_missing_from_the_schema() (+20 more)

### Community 17 - "CPC wire models"
Cohesion: 0.13
Nodes (6): create_router(), Cpc, CpcCreate, CpcPage, CpcUpdate, CpcValues

### Community 18 - "Documented write safeguards"
Cohesion: 0.16
Nodes (11): SQL and transaction assertions, Lowest unused agreement ID, Opt-in write enablement, Resource API key authentication, Agreement CRUD, Client CRUD, Database current date defaults, Legacy delete cascades (+3 more)

### Community 20 - "Agreement wire models"
Cohesion: 0.14
Nodes (5): create_router(), Agreement, AgreementCreate, AgreementPage, AgreementUpdate

### Community 21 - "AdapterError"
Cohesion: 0.19
Nodes (6): _adapter_error_handler(), _firebird_error_handler(), AdapterError, AuthenticationError, require_api_key(), check_api_key()

### Community 22 - "Service schema error tests"
Cohesion: 0.12
Nodes (12): TableNotFound, _StubSchema, test_create_agreement_link_failure_rolls_back(), test_create_agreement_links_machines_in_same_transaction(), test_fetch_agreements_validates_arguments(), test_fetch_clients_validates_arguments(), test_fetch_invoices_validates_arguments(), test_fetch_machines_validates_arguments() (+4 more)

### Community 23 - "Client wire models"
Cohesion: 0.17
Nodes (5): create_router(), Client, ClientCreate, ClientPage, ClientUpdate

### Community 25 - "test_service.py"
Cohesion: 0.07
Nodes (36): _client_insert(), make_service(), make_settings(), test_create_client_accepts_upper_cased_field_names(), test_create_client_inserts_the_supplied_columns(), test_create_client_prefers_supplied_values_over_the_defaults(), test_create_client_rejects_unknown_and_over_long_values(), test_create_cpc_merges_legacy_profile_and_commits() (+28 more)

### Community 27 - "parametrize"
Cohesion: 0.11
Nodes (20): test_agreement_routes_validate_machine_arrays(), test_cpc_write_errors_are_rendered(), test_create_agreement_rejects_invalid_fields(), test_create_agreement_requires_machines_array(), test_create_cpc_accepts_optional_period(), test_create_cpc_does_not_require_client(), test_create_cpc_validates_input(), test_create_machine_reports_missing_client() (+12 more)

### Community 28 - "create_router"
Cohesion: 0.24
Nodes (6): create_router(), service_info(), DatabaseInfo, HealthResponse, PoolInfo, ServiceInfo

### Community 29 - "routes/machines.py"
Cohesion: 0.27
Nodes (4): Machine, MachineCreate, MachinePage, MachineUpdate

### Community 31 - "pydantic"
Cohesion: 0.09
Nodes (6): create_router(), create_router(), Invoice, InvoicePage, Order, OrderPage

### Community 32 - "Decimal response contracts"
Cohesion: 0.17
Nodes (5): test_agreements_accepts_decimal_strings(), fake_fetch(), test_invoices_accepts_decimal_strings(), test_machines_accepts_decimal_strings(), test_orders_accepts_decimal_strings()

### Community 33 - "Reserved write transactions"
Cohesion: 0.13
Nodes (8): _configure_macos_transactions(), _ClientAPI, _Connection, _Pool, test_macos_transaction_binding_preserves_handles_and_tpb(), test_macos_transaction_binding_rejects_multiple_database_arguments(), test_reserved_write_failure_rolls_back(), test_reserved_write_starts_after_rollback_and_commits()

### Community 35 - "test_machines_database.py"
Cohesion: 0.12
Nodes (9): DatabaseMachine, DatabaseMachinePage, client(), fake_service(), settings(), test_secondary_database_http_contract(), test_secondary_database_http_validation(), test_secondary_database_is_optional_and_reports_unavailable() (+1 more)

### Community 36 - "migrate-firebird-2.5-to-5.sh"
Cohesion: 0.36
Nodes (7): checksum(), die(), ISC_USER, run25(), run5(), migrate-firebird-2.5-to-5.sh script, usage()

### Community 39 - "OpenAPI browser tester"
Cohesion: 0.33
Nodes (6): Abortable requests, Editable JSON request body, In-memory API key, OpenAPI-driven route forms, Public API tester, Public metadata and health routes

### Community 40 - "quote_identifier"
Cohesion: 0.22
Nodes (3): quote_identifier(), test_quote_identifier(), test_quote_identifier_rejects_empty()

## Knowledge Gaps
- **16 isolated node(s):** `ISC_USER`, `ks-adapter`, `Project-relative database path`, `Central database service`, `SQL and transaction assertions` (+11 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 353 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `DatabaseService` connect `Live database integration` to `Configuration validation`, `service/machines_database.py`, `test_machines_database.py`, `Service write tests`, `InvalidRequest`, `Application wiring and errors`, `Application settings and routing`, `Shared query execution`, `Curated column validation`, `Connection pool lifecycle`, `service/invoices.py`, `Client wire models`, `test_service.py`, `Documented read safeguards`, `routes/machines.py`?**
  _High betweenness centrality (0.099) - this node is a cross-community bridge._
- **Are the 52 inferred relationships involving `InvalidRequest` (e.g. with `AgreementsService` and `ClientsService`) actually correct?**
  _`InvalidRequest` has 52 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ISC_USER`, `ks-adapter`, `Project-relative database path` to the rest of the system?**
  _16 weakly-connected nodes found - possible missing edges._
- **Should `Configuration validation` be split into smaller, more focused modules?**
  _Cohesion score 0.06541822721598002 - nodes in this community are weakly interconnected._
- **Why does `AppSettings` connect `Application settings and routing` to `Configuration validation`, `Live database integration`, `Schema cache and types`, `test_machines_database.py`, `Application wiring and errors`, `base.py`, `Connection pool lifecycle`, `CPC wire models`, `Agreement wire models`, `AdapterError`, `Client wire models`, `create_router`, `test_service.py`, `create_router`, `routes/machines.py`, `pydantic`?**
  _High betweenness centrality (0.094) - this node is a cross-community bridge._
- **Are the 51 inferred relationships involving `FakeService` (e.g. with `test_agreements_accepts_decimal_strings()` and `test_agreements_endpoint()`) actually correct?**
  _`FakeService` has 51 INFERRED edges - model-reasoned connections that need verification._
- **Should `Live database integration` be split into smaller, more focused modules?**
  _Cohesion score 0.06435137895812053 - nodes in this community are weakly interconnected._