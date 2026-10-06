import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_tenant_isolation_projects():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Login as Raj (BLUEFORCE)
        raj_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "raj@blueforce.com", "password": "password123"},
        )
        assert raj_login.status_code == 200, raj_login.text
        raj_token = raj_login.json()["access_token"]
        raj_headers = {"Authorization": f"Bearer {raj_token}"}

        # 2. Login as John (Acme Corp)
        john_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "john@acme.com", "password": "password123"},
        )
        assert john_login.status_code == 200
        john_token = john_login.json()["access_token"]
        john_headers = {"Authorization": f"Bearer {john_token}"}

        # 3. Get John's projects
        john_projs_res = await client.get("/api/v1/projects", headers=john_headers)
        assert john_projs_res.status_code == 200
        john_projects = john_projs_res.json()
        assert isinstance(john_projects, list)
        if len(john_projects) > 0:
            acme_project_id = john_projects[0]["id"]

            # 4. Raj attempts to view John's project directly by ID
            cross_tenant_res = await client.get(
                f"/api/v1/projects/{acme_project_id}",
                headers=raj_headers,
            )
            # MUST BE 404 (Not Found / Access Denied)
            assert cross_tenant_res.status_code == 404

        # 5. Raj lists his projects -> should only see BLUEFORCE projects
        raj_projs_res = await client.get("/api/v1/projects", headers=raj_headers)
        assert raj_projs_res.status_code == 200


@pytest.mark.asyncio
async def test_tenant_isolation_messages():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        raj_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "raj@blueforce.com", "password": "password123"},
        )
        raj_token = raj_login.json()["access_token"]
        raj_headers = {"Authorization": f"Bearer {raj_token}"}

        # Login as John (Acme Corp)
        john_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "john@acme.com", "password": "password123"},
        )
        john_token = john_login.json()["access_token"]
        john_headers = {"Authorization": f"Bearer {john_token}"}

        # John lists conversations
        john_msgs_res = await client.get("/api/v1/conversations", headers=john_headers)
        assert john_msgs_res.status_code == 200
        john_msgs = john_msgs_res.json()

        # Verify John CANNOT see Raj's conversation
        for m in john_msgs:
            assert "Secret Blueforce Message" not in str(m)
