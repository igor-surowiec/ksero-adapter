# Development and testing

Install development packages with `python -m pip install -r
requirements-dev.txt`.

Check configuration and database connectivity with `python -m ks_adapter
--check`.

```bash
python -m pytest                              # unit + API, no database
KS_TEST_DB_PATH=BAZAMS.FDB python -m pytest   # adds the live Firebird tests
KS_TEST_DB_PATH=BAZAMS.FDB KS_TEST_DB_WRITABLE=1 python -m pytest
                                              # + the create-client tests
```

The write tests insert a disposable contractor and delete it again, which is why
they need the extra opt-in variable.


Run write tests against a disposable database copy. See
[AGENTS.md](../AGENTS.md) for the transaction and cleanup rules, and
[ARCHITECTURE.md](ARCHITECTURE.md) for the implementation reference.
