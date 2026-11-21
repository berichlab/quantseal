# Security Policy

## Security Model

**QuantSeal by berichlab** is designed specifically for safe self-hosted execution of LLM-assisted quantitative research:

1. **Zero Arbitrary Code Execution (`Zero-exec`)**: Strategy candidates are strictly declarative JSON ASTs validated against a bounded grammar (`quantseal/discovery/spec.py`). Keys such as `src`, `code`, `python`, `exec`, `eval`, `compile`, `lambda`, and dunder attributes (`__`) are unconditionally rejected.
2. **Fail-Closed External MCP Connectors**: External MCP servers default to Streamable HTTP / SSE only (`QUANTSEAL_ALLOW_STDIO_MCP=false`), preventing arbitrary local subprocess execution unless explicitly opted in by the server operator.
3. **Secret Redaction**: Prompts, audit trails, external MCP headers, and API responses redact common API key patterns (`sk-...`, `AIza...`, `Bearer ...`, `x-api-key`) and never return raw stored credentials via API responses.
4. **Self-Hosted Access Control**: Always configure a strong `QUANTSEAL_ADMIN_PASSWORD` and serve behind HTTPS (e.g., Hostinger Traefik / reverse proxy) before exposing port 8000 on a public network.
5. **No Live Order Execution**: QuantSeal does not store brokerage keys or place live financial orders.

## Reporting a Vulnerability

Please open a private GitHub Security Advisory on `berichlab/quantseal` rather than posting exploit details in a public issue. We aim to acknowledge reports within 72 hours.
