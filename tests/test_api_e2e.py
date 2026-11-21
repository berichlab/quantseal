"""End-to-end API tests covering auth, auto-demo bootstrap, single-shot validation, shadow ladder, and trade auditor."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from quantseal.api.main import create_app
from quantseal.config import Settings


def test_full_api_lifecycle(tmp_path: Path, monkeypatch):
    settings = Settings(
        admin_password="super-secret-quant-pass",
        data_dir=str(tmp_path / "qs_data"),
        auto_demo=True,
        scheduler_enabled=False,
    )
    app = create_app(settings=settings, start_scheduler=False)

    # Override dependency get_settings so routes use isolated test settings
    from quantseal.config import get_settings
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as client:
        # 1. Health is public
        h = client.get("/health")
        assert h.status_code == 200
        assert h.json()["status"] == "ok"

        # 2. Protected API requires auth
        assert client.get("/api/overview").status_code == 401

        # 3. Wrong password rejected; right password sets session cookie
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
        login = client.post("/api/auth/login", json={"password": "super-secret-quant-pass"})
        assert login.status_code == 200

        # 4. Demo workspace auto-seeded
        ov = client.get("/api/overview").json()
        assert ov["kpis"]["total_campaigns"] == 2
        assert ov["kpis"]["sealed_campaigns"] == 1
        assert ov["kpis"]["pending_validation"] == 1
        assert ov["kpis"]["active_shadow_strategies"] == 2
        assert ov["kpis"]["retired_strategies"] == 1
        assert ov["featured_shadow"] is not None

        # 5. Unlock single-shot validation on demo-pending-seal-v2, then verify second unlock is 409 Conflict
        v1 = client.post("/api/campaigns/demo-pending-seal-v2/validate-once")
        assert v1.status_code == 200
        assert v1.json()["validation_evaluated_once"] is True

        v2 = client.post("/api/campaigns/demo-pending-seal-v2/validate-once")
        assert v2.status_code == 409

        # 6. Shadow observation append & E-value recalculation
        obs = client.post(
            "/api/shadow/pullback_reclaim_null_v1/observations",
            json={
                "obs_date": "2026-11-20",
                "strategy_return_pct": 1.8,
                "benchmark_return_pct": 0.2,
                "note": "live test tick",
            },
        )
        assert obs.status_code == 200
        detail = client.get("/api/shadow/pullback_reclaim_null_v1").json()
        assert detail["observations_count"] == 35
        assert len(detail["series"]) == 35

        # 7. Standalone CSV Gate Auditor endpoint
        csv_lines = ["entry_date,symbol,sector,gross,net"]
        syms = ["AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA"]
        secs = ["Tech", "Tech", "Comm", "Cons", "Comm", "Semi"]
        for i in range(24):
            idx = i % len(syms)
            csv_lines.append(f"2026-05-{(i % 15) + 1:02d},{syms[idx]},{secs[idx]},1.6,1.3")
        audit = client.post("/api/audit/trades", json={"csv_text": "\n".join(csv_lines), "min_trades": 20})
        assert audit.status_code == 200
        body = audit.json()
        assert body["passed"] is True
        assert body["bootstrap_ci"]["passed"] is True
        assert body["cost_stress"]["1.5x"]["passed"] is True

        # 8. Settings update masks secrets
        upd = client.put(
            "/api/settings",
            json={"llm": {"provider": "openai", "model": "gpt-4o-mini", "api_key": "sk-live-secret-999999999999"}},
        )
        assert upd.status_code == 200
        s_json = upd.json()
        assert s_json["llm"]["api_key_configured"] is True
        assert "sk-live-secret-999999999999" not in str(s_json)
