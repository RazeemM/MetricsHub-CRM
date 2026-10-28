"""Health checks, the monitoring status (admin page, MetricsHub connector) and the Prometheus metrics."""
import base64
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import monitoring
from app.config import get_settings
from app.main import app

TOKEN = "monitoring-token-for-tests-0123456789"


@pytest.fixture
def settings(monkeypatch, tmp_path):
    s = get_settings()
    monkeypatch.setattr(s, "monitoring_token", TOKEN)
    monkeypatch.setattr(s, "backup_dir", str(tmp_path))
    monkeypatch.setattr(s, "mail_backend", "disabled")
    monkeypatch.setattr(s, "bulk_mail_backend", "")
    monitoring.reset()
    yield s
    monitoring.reset()


def _anonymous() -> TestClient:
    return TestClient(app)


def test_health_and_ready(client, settings, tmp_path):
    assert client.get("/api/health").json()["service"] == "metricshub-crm"
    (tmp_path / "crm-20261027-0200.dump").write_bytes(b"x" * 2048)
    r = _anonymous().get("/api/health/ready")
    assert r.status_code == 200 and r.json() == {"status": "ok", "checks": {
        "database": "ok", "migrations": "ok", "mail": "ok", "backups": "ok"}}

    old = time.time() - 60 * 3600  # two nights without a backup: failed, so not ready
    os.utime(tmp_path / "crm-20261027-0200.dump", (old, old))
    r = _anonymous().get("/api/health/ready")
    assert r.status_code == 503 and r.json()["checks"]["backups"] == "failed"
    assert "message" not in r.text  # details only for administrators and the monitoring token


def test_status_access(client, settings):
    anon = _anonymous()
    assert anon.get("/api/monitoring/status").status_code == 401
    assert anon.get("/api/monitoring/status", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert anon.get("/api/monitoring/status", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200
    basic = base64.b64encode(f"metricshub:{TOKEN}".encode()).decode()
    assert anon.get("/api/metrics", headers={"Authorization": f"Basic {basic}"}).status_code == 200
    assert client.get("/api/monitoring/status").status_code == 200  # signed-in administrator

    client.post("/api/users", json={"email": "seller@helixops.ai", "full_name": "Seller", "role": "sales",
                                    "password": "seller-pass-1"})
    token = anon.post("/api/auth/login", data={"username": "seller@helixops.ai", "password": "seller-pass-1"}).json()
    seller = {"Authorization": f"Bearer {token['access_token']}"}
    assert anon.get("/api/monitoring/status", headers=seller).status_code == 403

    settings.monitoring_token = ""  # no token configured: Basic and arbitrary Bearer values are refused
    assert anon.get("/api/metrics", headers={"Authorization": f"Basic {basic}"}).status_code == 401
    assert anon.get("/api/metrics", headers={"Authorization": "Bearer "}).status_code == 401


def test_status_statistics_and_mail_failures(client, settings, tmp_path):
    (tmp_path / "crm-20261028-0200.dump").write_bytes(b"x" * 4096)
    client.post("/api/accounts", json={"name": "Monitored Corp"})
    client.get("/api/accounts")
    client.get("/api/accounts/999999")  # 404

    s = client.get("/api/monitoring/status").json()
    assert s["status"] == "ok" and s["version"] == monitoring.VERSION and s["uptime_seconds"] >= 0
    assert s["http"]["requests"] >= 3 and s["http"]["client_errors"] >= 1 and s["http"]["average_ms"] is not None
    assert s["records"]["accounts"] >= 1 and s["users"]["enabled"] >= 1 and s["users"]["active_24h"] >= 1
    assert s["database"]["size_bytes"] > 0 and s["database"]["connections"] >= 1
    assert s["backups"]["count"] == 1 and s["backups"]["last_bytes"] == 4096 and s["backups"]["age_seconds"] < 60
    assert {"email", "forms", "recent", "tables"} <= s.keys()

    # A failed send (here: email not configured) shows on the mail check with its reason
    assert client.post("/api/mail/test", json={"to": "ops@helixops.ai"}).status_code == 422
    s = client.get("/api/monitoring/status").json()
    mail_check = next(c for c in s["checks"] if c["name"] == "mail")
    assert s["status"] == "degraded" and mail_check["status"] == "degraded"
    assert "not configured" in mail_check["message"] and s["email"]["transactional_failed"] == 1
    assert s["recent"]["mail_failures"][0]["error"].startswith("Email sending is not configured")
    assert client.get("/api/health/ready").status_code == 200  # degraded is still ready


def test_prometheus_metrics(client, settings):
    text = client.get("/api/metrics").text
    assert "# TYPE crm_up gauge" in text and "crm_up 1" in text
    assert 'crm_check_status{check="database",state="ok"} 1' in text
    assert 'crm_records{object="accounts"}' in text and "crm_database_size_bytes" in text
    assert 'crm_email_messages_total{purpose="transactional",state="sent"} 0' in text


def test_scheduler_check(settings, monkeypatch):
    monkeypatch.setattr(settings, "run_scheduler", True)
    monkeypatch.setattr(monitoring, "STARTED", time.time() - 3600)
    assert monitoring.check_scheduler()["status"] == "failed"
    monitoring.record_job("campaigns")
    assert monitoring.check_scheduler()["status"] == "ok"
    monitoring.job_runs["campaigns"] = time.time() - 600
    assert monitoring.check_scheduler()["status"] == "failed"


# ---------------------------------------------------------------- MetricsHub connector
CONNECTOR = Path(__file__).resolve().parents[2] / "monitoring/metricshub/connectors/MetricsHubCRM/MetricsHubCRM.yaml"


def _json2csv(doc, entry_key: str, properties: str) -> list[list[str]]:
    """What MetricsHub's json2Csv compute produces: the entry path, then each property (empty when missing/null)."""
    def walk(node, path):
        for part in [p for p in path.split("/") if p]:
            node = node.get(part) if isinstance(node, dict) else None
        return node
    entry = walk(doc, entry_key)
    rows = entry if isinstance(entry, list) else [entry]
    out = []
    for i, row in enumerate(rows):
        values = [walk(row, p) for p in properties.split(";")]
        out.append([f"{entry_key}[{i}]"] + ["" if v is None else str(v) for v in values])
    return out


@pytest.mark.skipif(not CONNECTOR.exists(), reason="connector not in this checkout")
def test_metricshub_connector_reads_the_status(client, settings, tmp_path):
    yaml = pytest.importorskip("yaml")
    (tmp_path / "crm-20261028-0200.dump").write_bytes(b"x" * 100)
    connector = yaml.safe_load(CONNECTOR.read_text(encoding="utf-8"))
    declared = connector["metrics"]
    assert connector["beforeAll"]["status"]["path"] == "/api/monitoring/status"
    doc = TestClient(app).get("/api/monitoring/status", headers={
        "Authorization": "Basic " + base64.b64encode(f"metricshub:{TOKEN}".encode()).decode()}).json()

    for name, monitor in connector["monitors"].items():
        job = monitor["simple"]
        (source,) = job["sources"].values()
        assert source["from"] == "${source::beforeAll.status}"
        (compute,) = source["computes"]
        rows = _json2csv(doc, compute["entryKey"], compute["properties"])
        assert rows, name
        columns = len(rows[0])
        for metric, ref in job["mapping"]["metrics"].items():
            base = metric.split("{")[0]
            assert base in declared, f"{metric} is not declared"
            col = int(ref.lstrip("$"))
            assert col <= columns, f"{name}: {metric} reads ${col}, only {columns} columns"
            for row in rows:
                value = row[col - 1]
                if isinstance(declared[base]["type"], dict):  # stateSet
                    assert value in declared[base]["type"]["stateSet"], f"{metric}: {value!r}"
                elif value != "":
                    float(value)  # numeric
        for attr, ref in job["mapping"].get("attributes", {}).items():
            if str(ref).startswith("$"):
                assert all(row[int(ref[1:]) - 1] for row in rows), f"{name}: attribute {attr} is empty"

    checks = _json2csv(doc, "/checks", "/name;/label;/status;/message")
    assert {r[1] for r in checks} >= {"database", "mail", "backups"}
