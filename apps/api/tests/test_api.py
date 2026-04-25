from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_models_lists_three_rba_engines():
    data = client.get("/models").json()
    ids = [m["id"] for m in data["rba"]]
    assert ids == ["bos", "mos", "four_factor"]
    assert data["mla"] == []


def test_score_bos_endpoint():
    payload = {
        "universe": "TEST",
        "rows": [
            {"ticker": "A", "vol_avg_3m": 1_000_000, "target_return": 25,
             "dvd_yld_ind": 7, "altman_z": 3.0, "analyst_sent": 4.5},
            {"ticker": "B", "vol_avg_3m": 500_000, "target_return": 10,
             "dvd_yld_ind": 4, "altman_z": 1.7, "analyst_sent": 3.5},
            {"ticker": "C", "vol_avg_3m": 350_000, "target_return": 0,
             "dvd_yld_ind": 4, "altman_z": 1.7, "analyst_sent": 3.5},
            {"ticker": "D", "vol_avg_3m": 100_000, "target_return": -50,
             "dvd_yld_ind": 1, "altman_z": 0.5, "analyst_sent": 1.0},
        ],
    }
    r = client.post("/score?model=bos", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["model_version"] == "rba-bos-1.0.0"
    assert body["n_rows"] == 4
    assert body["n_scored"] == 4
    quartiles = {row["ticker"]: row["quartile"] for row in body["results"]}
    assert quartiles["A"] == 1
    assert quartiles["D"] == 4


def test_score_rejects_empty_rows():
    r = client.post("/score?model=bos", json={"universe": "T", "rows": []})
    assert r.status_code == 400


def test_score_rejects_unknown_model():
    r = client.post(
        "/score?model=quantum_woo",
        json={"universe": "T", "rows": [{"ticker": "X"}]},
    )
    # FastAPI Literal validation -> 422
    assert r.status_code in (400, 422)
