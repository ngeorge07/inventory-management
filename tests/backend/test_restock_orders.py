"""
Tests for restocking order API endpoints.
"""
import pytest


@pytest.fixture
def sample_restock_payload():
    """A valid create-restock-order request body."""
    return {
        "items": [
            {
                "item_sku": "WDG-001",
                "item_name": "Industrial Widget Type A",
                "quantity": 150,
                "unit_cost": 45.0,
                "lead_time_days": 18,
            },
            {
                "item_sku": "GSK-203",
                "item_name": "High-Temperature Gasket",
                "quantity": 100,
                "unit_cost": 8.5,
                "lead_time_days": 9,
            },
        ],
        "budget": 100000,
    }


class TestRestockOrderEndpoints:
    """Test suite for restocking order endpoints."""

    def test_demand_includes_restock_fields(self, client):
        """Demand forecasts should now expose unit_cost and lead_time_days."""
        response = client.get("/api/demand")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        for forecast in data:
            assert "unit_cost" in forecast
            assert "lead_time_days" in forecast
            assert isinstance(forecast["unit_cost"], (int, float))
            assert isinstance(forecast["lead_time_days"], int)

    def test_create_restock_order(self, client, sample_restock_payload):
        """Posting a valid order returns a Submitted order with computed fields."""
        response = client.post("/api/restock-orders", json=sample_restock_payload)
        assert response.status_code == 200

        order = response.json()
        assert order["status"] == "Submitted"
        assert order["order_number"].startswith("RST-2026-")
        assert order["item_count"] == 2

        # total_value = 150*45 + 100*8.5 = 6750 + 850 = 7600
        assert abs(order["total_value"] - 7600.0) < 0.01

        # Lead time is the max across items (18 vs 9)
        assert order["lead_time_days"] == 18

        # expected_delivery must be after order_date
        assert order["expected_delivery"] > order["order_date"]
        assert "T" in order["expected_delivery"]

    def test_create_restock_order_empty_items(self, client):
        """An empty items list is rejected with 400."""
        response = client.post("/api/restock-orders", json={"items": []})
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data

    def test_create_restock_order_missing_items(self, client):
        """A body missing the required items field is a validation error."""
        response = client.post("/api/restock-orders", json={"budget": 5000})
        assert response.status_code == 422

    def test_get_restock_orders_lists_submitted(self, client, sample_restock_payload):
        """Submitted orders are returned by the list endpoint, newest first."""
        # Submit two orders
        first = client.post("/api/restock-orders", json=sample_restock_payload).json()
        second = client.post("/api/restock-orders", json=sample_restock_payload).json()

        response = client.get("/api/restock-orders")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2

        order_numbers = [o["order_number"] for o in data]
        assert first["order_number"] in order_numbers
        assert second["order_number"] in order_numbers

        # Newest first: the most recently submitted appears before the earlier one
        assert order_numbers.index(second["order_number"]) < order_numbers.index(
            first["order_number"]
        )
