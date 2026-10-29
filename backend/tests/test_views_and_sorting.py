"""Column sorting on the lists, the board's filters, and saved pipeline views."""
from fastapi.testclient import TestClient

from app.main import app


def _opp(client, ref, title, account_id, **kw):
    r = client.post("/api/opportunities", json={"title": title, "account_id": account_id,
                                                "brand_id": ref["brands"]["METRICSHUB"], **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _as(client, email, role="sales") -> TestClient:
    client.post("/api/users", json={"email": email, "full_name": email.split("@")[0].title(), "role": role,
                                    "password": "view-pass-123"})
    c = TestClient(app)
    token = c.post("/api/auth/login", data={"username": email, "password": "view-pass-123"}).json()["access_token"]
    c.headers["Authorization"] = f"Bearer {token}"
    return c


def test_list_sorting(client, ref):
    zed = client.post("/api/accounts", json={"name": "Zed Sorting Ltd"}).json()
    abe = client.post("/api/accounts", json={"name": "abe sorting sa"}).json()
    _opp(client, ref, "Sorting B", zed["id"], expected_close_date="2027-03-01")
    _opp(client, ref, "Sorting A", abe["id"], expected_close_date="2027-01-01")
    _opp(client, ref, "Sorting C", abe["id"])  # no close date: last whichever the direction

    def titles(**params):
        items = client.get("/api/opportunities", params={"q": "Sorting", **params}).json()["items"]
        return [o["title"] for o in items]

    assert titles(sort="title", desc=False) == ["Sorting A", "Sorting B", "Sorting C"]
    assert titles(sort="close", desc=False) == ["Sorting A", "Sorting B", "Sorting C"]
    assert titles(sort="close", desc=True) == ["Sorting B", "Sorting A", "Sorting C"]
    assert titles(sort="account", desc=False)[-1] == "Sorting B"  # account names compare without case
    for key in ("brand", "stage", "platform", "amount", "arr", "weighted", "owner", "created_at", "nonsense"):
        assert len(titles(sort=key)) == 3, key

    names = [a["name"] for a in client.get("/api/accounts", params={"q": "sorting", "sort": "name"}).json()["items"]]
    assert names == ["abe sorting sa", "Zed Sorting Ltd"]
    for key in ("open_deals", "contacts", "owner", "domain", "country"):
        r = client.get("/api/accounts", params={"q": "sorting", "sort": key, "desc": True})
        assert r.status_code == 200 and r.json()["total"] == 2, key
    top = client.get("/api/accounts", params={"q": "sorting", "sort": "open_deals", "desc": True}).json()["items"]
    assert top[0]["name"] == "abe sorting sa"  # 2 open deals
    for key in ("account", "role", "source", "name"):
        assert client.get("/api/contacts", params={"sort": key}).status_code == 200, key


def test_board_filters(client, ref):
    acc = client.post("/api/accounts", json={"name": "Board Filters Inc"}).json()
    _opp(client, ref, "Board big renewal", acc["id"], deal_type="expansion", route_to_market="reseller",
         expected_close_date="2027-06-30", line_items=[{"product_id": ref["products"]["MH-PS-DAY"]["id"],
                                                        "quantity": 10, "unit_price": "1000"}])
    _opp(client, ref, "Board small new", acc["id"], deal_type="new", route_to_market="direct")

    def board(**params):
        cols = client.get("/api/opportunities/board", params={"q": "Board ", **params}).json()["columns"]
        return sorted(i["title"] for c in cols for i in c["items"])

    assert board() == ["Board big renewal", "Board small new"]
    assert board(deal_type=["renewal", "expansion"]) == ["Board big renewal"]
    assert board(route_to_market="direct") == ["Board small new"]
    assert board(min_amount=5000) == ["Board big renewal"]
    assert board(close_from="2027-06-01", close_to="2027-06-30") == ["Board big renewal"]
    assert board(no_close_date=True) == ["Board small new"]
    assert board(brand_id=[ref["brands"]["SENTRY"]]) == []
    cols = client.get("/api/opportunities/board", params={"hide_closed": True}).json()["columns"]
    assert cols and all(c["stage"]["kind"] == "open" for c in cols)
    ordered = client.get("/api/opportunities/board", params={"q": "Board ", "sort": "amount"}).json()["columns"]
    assert ordered[0]["items"][0]["title"] == "Board big renewal"


def test_saved_views(client):
    ana = _as(client, "ana.views@helixops.ai")
    bob = _as(client, "bob.views@helixops.ai", role="readonly")
    filters = {"deal_types": ["renewal"], "close": "this_quarter", "mine": True, "hide_closed": True, "sort": "amount"}

    mine = ana.post("/api/views", json={"name": "My renewals", "filters": filters})
    assert mine.status_code == 201, mine.text
    v = mine.json()
    assert v["editable"] and not v["shared"] and v["filters"]["deal_types"] == ["renewal"]
    assert v["filters"]["close"] == "this_quarter" and v["owner_name"] == "Ana.Views"
    assert ana.post("/api/views", json={"name": "my RENEWALS"}).status_code == 409
    assert ana.post("/api/views", json={"name": "Bad", "filters": {"close": "someday"}}).status_code == 422

    assert bob.get("/api/views").json() == []  # private until shared
    assert bob.patch(f"/api/views/{v['id']}", json={"shared": True}).status_code == 404
    assert ana.patch(f"/api/views/{v['id']}", json={"shared": True}).json()["shared"]

    seen = bob.get("/api/views").json()
    assert [x["name"] for x in seen] == ["My renewals"] and not seen[0]["editable"]
    assert bob.patch(f"/api/views/{v['id']}", json={"name": "Hijack"}).status_code == 403
    assert bob.delete(f"/api/views/{v['id']}").status_code == 403
    assert bob.post("/api/views", json={"name": "Bob's view"}).status_code == 201  # read-only users keep views too
    assert [x["name"] for x in bob.get("/api/views").json()] == ["Bob's view", "My renewals"]  # own first

    edited = ana.patch(f"/api/views/{v['id']}", json={"name": "Renewals this quarter",
                                                     "filters": {**filters, "min_amount": "10000"}}).json()
    assert edited["name"] == "Renewals this quarter" and edited["filters"]["min_amount"] == "10000"
    assert client.get("/api/views").json()[-1]["editable"]  # administrators can fix shared views
    assert ana.delete(f"/api/views/{v['id']}").status_code == 204
    assert all(x["id"] != v["id"] for x in bob.get("/api/views").json())
