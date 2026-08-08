# API gap analysis

Phase 1 needs no Java changes. It can investigate only symbols already represented
by a Java `Position`, because valuation lookup rejects untracked symbols. A future
public-company capability needs a Java-owned `GET /api/research/v1/companies/{symbol}/snapshot`
endpoint that exposes existing authoritative data without reimplementing calculations.
