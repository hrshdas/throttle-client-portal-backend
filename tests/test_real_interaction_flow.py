import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_full_phase2_client_admin_interaction_workflow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # --- 0. LOGINS ---
        # Admin Login
        admin_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@throttle.agency", "password": "admin123"},
        )
        assert admin_login.status_code == 200
        admin_token = admin_login.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Raj (BLUEFORCE) Login
        raj_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "raj@blueforce.com", "password": "password123"},
        )
        assert raj_login.status_code == 200
        raj_token = raj_login.json()["access_token"]
        raj_headers = {"Authorization": f"Bearer {raj_token}"}

        # Test User (Acme) Login
        test_user_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "john@acme.com", "password": "password123"},
        )
        assert test_user_login.status_code == 200
        test_user_token = test_user_login.json()["access_token"]
        test_user_headers = {"Authorization": f"Bearer {test_user_token}"}

        # Get Raj's profile & org ID
        raj_profile = await client.get("/api/v1/client/me", headers=raj_headers)
        assert raj_profile.status_code == 200
        blueforce_org_id = raj_profile.json()["organization"]["id"]
        raj_user_id = raj_profile.json()["user"]["id"]

        # Get Test User's org ID
        test_profile = await client.get("/api/v1/client/me", headers=test_user_headers)
        test_user_id = test_profile.json()["user"]["id"]

        # --- SCENARIO 1: ADMIN CREATES A TASK FOR BLUEFORCE ---
        create_task_res = await client.post(
            "/api/v1/tasks",
            headers=admin_headers,
            json={
                "organization_id": blueforce_org_id,
                "title": "Review October Meta Ad Creatives",
                "description": "Please review new video concepts.",
                "priority": "HIGH",
                "assigned_to_user_id": raj_user_id,
                "requires_client_approval": True,
            },
        )
        assert create_task_res.status_code == 200, create_task_res.text
        task_id = create_task_res.json()["id"]
        assert create_task_res.json()["approval_status"] == "PENDING"
        assert create_task_res.json()["human_approval_status"] == "Awaiting your review"

        # --- SCENARIO 2: RAJ SEES THE TASK ---
        raj_tasks_res = await client.get("/api/v1/tasks", headers=raj_headers)
        assert raj_tasks_res.status_code == 200
        raj_task_ids = [t["id"] for t in raj_tasks_res.json()]
        assert task_id in raj_task_ids

        # --- SCENARIO 3: RAJ COMMENTS ON THE TASK ---
        raj_comment_res = await client.post(
            f"/api/v1/tasks/{task_id}/comments",
            headers=raj_headers,
            json={"message": "Can we make Creative 4's headline larger?"},
        )
        assert raj_comment_res.status_code == 200
        assert raj_comment_res.json()["message"] == "Can we make Creative 4's headline larger?"
        assert raj_comment_res.json()["user_id"] == raj_user_id

        # --- SCENARIO 4: ADMIN SEES RAJ'S COMMENT ---
        admin_task_detail = await client.get(f"/api/v1/tasks/{task_id}", headers=admin_headers)
        assert admin_task_detail.status_code == 200
        comments = admin_task_detail.json()["comments"]
        assert any("headline larger" in c["message"] for c in comments)

        # --- SCENARIO 5: ADMIN REPLIES TO COMMENT ---
        admin_reply_res = await client.post(
            f"/api/v1/tasks/{task_id}/comments",
            headers=admin_headers,
            json={"message": "Yes, we'll update it today."},
        )
        assert admin_reply_res.status_code == 200

        # --- SCENARIO 6: RAJ RECEIVES NOTIFICATION ---
        raj_notifs_res = await client.get("/api/v1/notifications", headers=raj_headers)
        assert raj_notifs_res.status_code == 200
        raj_notifs = raj_notifs_res.json()
        assert any(n["type"] == "TASK_COMMENT_ADDED" for n in raj_notifs)

        # --- SCENARIO 7: RAJ REQUESTS CHANGES ---
        req_changes_res = await client.post(
            f"/api/v1/tasks/{task_id}/request-changes",
            headers=raj_headers,
            json={"comment": "Please make headline on Creative 4 slightly larger."},
        )
        assert req_changes_res.status_code == 200
        assert req_changes_res.json()["approval_status"] == "CHANGES_REQUESTED"
        assert req_changes_res.json()["human_approval_status"] == "Changes requested"

        # --- SCENARIO 8: ADMIN RECEIVES NOTIFICATION FOR CHANGES REQUESTED ---
        admin_notifs_res = await client.get("/api/v1/notifications", headers=admin_headers)
        assert admin_notifs_res.status_code == 200
        admin_notifs = admin_notifs_res.json()
        assert any(n["type"] == "CHANGES_REQUESTED" for n in admin_notifs)

        # --- SCENARIO 9: ADMIN UPDATES TASK ---
        update_task_res = await client.patch(
            f"/api/v1/tasks/{task_id}",
            headers=admin_headers,
            json={"description": "Updated creatives with enlarged headline on Creative 4."},
        )
        assert update_task_res.status_code == 200

        # --- SCENARIO 10: RAJ APPROVES THE TASK ---
        approve_res = await client.post(
            f"/api/v1/tasks/{task_id}/approve",
            headers=raj_headers,
            json={"comment": "Headline looks great now. Approved!"},
        )
        assert approve_res.status_code == 200
        assert approve_res.json()["approval_status"] == "APPROVED"
        assert approve_res.json()["status"] == "COMPLETED"

        # --- SCENARIO 11: ADMIN RECEIVES APPROVAL NOTIFICATION ---
        admin_notifs_2 = await client.get("/api/v1/notifications", headers=admin_headers)
        assert any(n["type"] == "TASK_APPROVED" for n in admin_notifs_2.json())

        # --- SCENARIO 12: APPROVAL HISTORY IS PRESERVED ---
        final_task_detail = await client.get(f"/api/v1/tasks/{task_id}", headers=raj_headers)
        history = final_task_detail.json()["approval_history"]
        actions = [h["action"] for h in history]
        assert "CHANGES_REQUESTED" in actions
        assert "APPROVED" in actions

        # --- SCENARIO 13: ACTIVITY FEED UPDATES AUTOMATICALLY ---
        act_res = await client.get("/api/v1/activities", headers=raj_headers)
        assert act_res.status_code == 200
        activities = act_res.json()
        act_types = [a["type"] for a in activities]
        assert "task_created" in act_types or "changes_requested" in act_types or "task_approved" in act_types

        # --- SCENARIO 14 & 15: 1-ON-1 DIRECT ENCRYPTED CHAT & REAL SENDER IDS ---
        conv_res = await client.get("/api/v1/conversations", headers=raj_headers)
        assert conv_res.status_code == 200
        conv_data = conv_res.json()[0]
        conv_id = conv_data["id"]
        assert conv_data["is_direct"] is True
        assert conv_data["is_encrypted"] is True

        post_msg_res = await client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            headers=raj_headers,
            json={"message": "Can we increase the Meta campaign budget?"},
        )
        assert post_msg_res.status_code == 200
        assert post_msg_res.json()["sender_user_id"] == raj_user_id
        assert post_msg_res.json()["message"] == "Can we increase the Meta campaign budget?"

        get_msgs_res = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=raj_headers)
        assert get_msgs_res.status_code == 200
        messages = get_msgs_res.json()
        assert any(m["message"] == "Can we increase the Meta campaign budget?" for m in messages)

        # --- SCENARIO 16, 17, 18, 19: TENANT & 1-ON-1 ISOLATION SECURITY ---
        # 16. Create task for Test Company
        test_task_create = await client.post(
            "/api/v1/tasks",
            headers=admin_headers,
            json={
                "organization_id": test_profile.json()["organization"]["id"],
                "title": "Secret Test Company Task",
                "assigned_to_user_id": test_user_id,
            },
        )
        test_task_id = test_task_create.json()["id"]

        # 16. Raj cannot view Test Company task by ID
        cross_task_res = await client.get(f"/api/v1/tasks/{test_task_id}", headers=raj_headers)
        assert cross_task_res.status_code == 404

        # 17. Raj cannot view Test Company conversation
        test_conv_res = await client.get("/api/v1/conversations", headers=test_user_headers)
        test_conv_id = test_conv_res.json()[0]["id"]
        cross_chat_res = await client.get(f"/api/v1/conversations/{test_conv_id}/messages", headers=raj_headers)
        assert cross_chat_res.status_code in (403, 404)

        # 18. Raj cannot approve Test Company task
        cross_approve_res = await client.post(f"/api/v1/tasks/{test_task_id}/approve", headers=raj_headers, json={})
        assert cross_approve_res.status_code == 404

        # 19. Test Company user cannot access Blueforce task
        test_cross_task = await client.get(f"/api/v1/tasks/{task_id}", headers=test_user_headers)
        assert test_cross_task.status_code == 404

        # --- SCENARIO 20: TEST USER CAN SEND 1-ON-1 TEXT TO ADMIN CLEANLY ---
        test_conv_res = await client.get("/api/v1/conversations", headers=test_user_headers)
        assert test_conv_res.status_code == 200
        test_conv = test_conv_res.json()[0]
        assert test_conv["id"] != conv_id  # Completely isolated from Blueforce

        test_post = await client.post(
            f"/api/v1/conversations/{test_conv['id']}/messages",
            headers=test_user_headers,
            json={"message": "Hello Throttle Admin from Test Company!"},
        )
        assert test_post.status_code == 200
        assert test_post.json()["message"] == "Hello Throttle Admin from Test Company!"

        # --- SCENARIO 21: ADMIN CAN ACCESS ALL AUTHORIZED ORGANIZATIONS ---
        admin_orgs = await client.get("/api/v1/admin/organizations", headers=admin_headers)
        assert admin_orgs.status_code == 200
        assert len(admin_orgs.json()) >= 2
