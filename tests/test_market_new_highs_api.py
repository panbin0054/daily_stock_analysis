from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints.market import NewHighResponse, NewHighStockItem
from api.v1.router import router


def test_new_highs_is_registered_and_forwards_query():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    response_data = NewHighResponse(
        items=[NewHighStockItem(code="605488", name="示例", price=49.27)],
        total=1,
        period="20d",
        update_time="2026-11-05 16:00:00",
    )
    with patch("api.v1.endpoints.market._fetch_new_high_stocks", return_value=response_data) as fetch:
        response = TestClient(app).get(
            "/api/v1/market/new-highs",
            params={"period": "20d", "page": 2, "page_size": 10, "sort_by": "price", "sort_order": "asc"},
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["code"] == "605488"
    fetch.assert_called_once_with(period="20d", page=2, page_size=10, sort_field="f2", sort_order=1)
