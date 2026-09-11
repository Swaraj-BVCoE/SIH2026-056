from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routes import router
from db.database import get_db_session
from db.models import Base, FlightPrice


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db_session] = override_db
    with TestClient(app) as test_client:
        test_client.session_factory = Session
        yield test_client
    Base.metadata.drop_all(engine)


def test_empty_database_index_response(client):
    response = client.get("/api/index/latest")
    assert response.status_code == 200
    assert response.json()["value"] is None
    assert response.json()["routes_used"] == 0


def test_fare_pagination(client):
    with client.session_factory() as db:
        for i in range(3):
            db.add(FlightPrice(scraped_at=datetime(2026, 9, i + 1, tzinfo=timezone.utc), travel_date=date(2026, 10, 1),
                               origin="DEL", destination="BOM", airline="IndiGo", total_fare=4000 + i,
                               source_portal="indigo_direct", advance_days=30, is_outlier=False))
        db.commit()
    response = client.get("/api/fares?page=2&page_size=2")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["pages"] == 2
    assert len(body["items"]) == 1


def test_data_quality_counts(client):
    with client.session_factory() as db:
        db.add(FlightPrice(scraped_at=datetime.now(timezone.utc), travel_date=date(2026, 10, 1), origin="DEL", destination="BOM",
                           airline="IndiGo", total_fare=4000, source_portal="indigo_direct", advance_days=30, is_outlier=True))
        db.commit()
    body = client.get("/api/data-quality").json()
    assert body["raw_records"] == 1
    assert body["valid_records"] == 0
    assert body["outliers_detected"] == 1
