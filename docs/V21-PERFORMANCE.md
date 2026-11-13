# V20 / V21 performance comparison

Synthetic Flask/SQLite measurements in the same Linux environment, using the same installed Python dependencies. Baseline is V20 commit `63e5814`. No live production data, IIS, Windows filesystem, SMTP or browser-rendering time is included.

Each row is the median of five warm requests after one excluded warm-up. Dashboard/list/customer tests use 300 quotations and 30 customers. Quotation opening/saving use 100 quotations and one customer; saves change the title and use the current stale-edit token. Benchmarks ran while other automated verification was occurring, so CPU contention, SQLite caching and other noise affect timings. These are observed samples, not controlled load-test results or a production latency guarantee.

| Operation | V20 median ms | V21 median ms | Change |
| --- | ---: | ---: | ---: |
| Dashboard | 232.93 | 237.24 | +1.9% |
| Quotation list | 739.83 | 644.89 | -12.8% |
| Customer list | 230.94 | 195.47 | -15.4% |
| Customer workspace | 214.59 | 179.84 | -16.2% |
| Quotation opening | 40.26 | 59.88 | +48.7% |
| Quotation saving | 50.61 | 46.77 | -7.6% |

Deterministic query counts are more useful than small timing changes here:

| Operation | V20 SQL statements/request | V21 SQL statements/request |
| --- | ---: | ---: |
| Open saved quotation | 1,060 | 279 |
| Save changed quotation | 967 | 82 |

Ownership, sharing and workflow grants are fetched in batches during record-list authorization/redaction. The scope is one evaluation, one connection and one current user; it is reset before later mutation checks. The existing quotation-list family scan is grouped once rather than rescanned per family. No long-lived permission cache or pricing rewrite was added.

The quotation list and customer-page samples improved; the dashboard and quotation-opening timings did not. Saving SQL work dropped substantially, but its wall-clock sample is influenced by contention. The V21 interface sends no additional polling requests for favorites, validity badges, timelines or global search: these are server-rendered views/forms. Existing workflow/PDF/notification polling is retained. Recent-view tracking adds a small indexed write and pruning on successful record-page views.

Raw samples and response sizes are in [v21-measurements](v21-measurements/). V21 list HTML is larger because it includes validity, copy and favorite tools. This tradeoff is recorded rather than hidden.

Reproduce from the V21 source with its virtual environment:

```sh
.venv/bin/python tests/performance_v15.py
.venv/bin/python tests/performance_v21.py
CIRRUS_BENCH_SOURCE=/path/to/read-only-v20 .venv/bin/python tests/performance_v21.py
```

Run the first script from the V20 checkout with the same interpreter for the baseline page sample, using `PYTHONDONTWRITEBYTECODE=1` to avoid generated cache files there. Use dedicated, otherwise idle runs on Windows for deployment-specific performance decisions. Do not benchmark against production writes.
