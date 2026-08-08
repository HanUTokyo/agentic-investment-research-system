# API integration

`StockPlatformClient` composes `GET /api/valuations/{symbol}` with the matching
holding in `GET /api/portfolio/export/v2`. Fundamentals and capital allocation use
the existing history APIs. Scenarios are unsaved `POST /api/valuations/{symbol}/evaluate`
calls; no Python code calculates DCF, FCFF, FCFE, ROE, or ROIC.

The checked-in contract is schema-only because the local Java server was unavailable
during bootstrap. Before public release, replace it with a reviewed, data-free
`/v3/api-docs` capture and run the adapter contract suite against it.
