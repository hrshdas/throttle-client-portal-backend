import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import uuid
from datetime import datetime, timezone, timedelta, date
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, engine, Base
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.project import (
    Project,
    Task,
    ProjectMilestone,
    TaskApprovalHistory,
    TaskComment,
    ProjectStatus,
    TaskStatus,
    TaskPriority,
    ApprovalStatus,
    MilestoneStatus,
)
from app.models.message import Conversation, ConversationParticipant, Message
from app.models.notification import Notification, NotificationType
from app.models.activity import Activity


COMPANIES = [
    {"name": "BLUEFORCE", "slug": "blueforce", "users": [("Raj", "raj@blueforce.com", UserRole.CLIENT_ADMIN, "Founder"), ("Priya", "priya@blueforce.com", UserRole.CLIENT, "Marketing Manager")]},
    {"name": "Acme Corp", "slug": "acme", "users": [("John", "john@acme.com", UserRole.CLIENT_ADMIN, "Founder"), ("Sarah", "sarah@acme.com", UserRole.CLIENT, "Product Lead")]},
    {"name": "Vertex Labs", "slug": "vertex", "users": [("Alex", "alex@vertex.com", UserRole.CLIENT_ADMIN, "CTO"), ("Elena", "elena@vertex.com", UserRole.CLIENT, "Designer")]},
    {"name": "Test Company", "slug": "testcompany", "users": [("Test User", "user@testcompany.com", UserRole.CLIENT_ADMIN, "Founder")]},
]


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # Check if already seeded
        res = await session.execute(select(User).where(User.email == "admin@throttle.agency"))
        if res.scalar_one_or_none():
            print("Database already seeded!")
            return

        print("Seeding Throttle Database Phase 2...")

        # 1. Create Agency Org
        agency_org = Organization(
            id=str(uuid.uuid4()),
            name="Throttle Agency",
            slug="throttle-agency",
        )
        session.add(agency_org)

        # 2. Create Admin User
        admin_user = User(
            id=str(uuid.uuid4()),
            organization_id=agency_org.id,
            name="Throttle Admin",
            email="admin@throttle.agency",
            hashed_password=hash_password("admin123"),
            role=UserRole.THROTTLE_ADMIN,
            is_active=True,
        )
        session.add(admin_user)

        # 3. Create Client Companies & Users
        default_pwd_hash = hash_password("password123")
        now = datetime.now(timezone.utc)
        today = date.today()

        for comp_data in COMPANIES:
            org = Organization(
                id=str(uuid.uuid4()),
                name=comp_data["name"],
                slug=comp_data["slug"],
            )
            session.add(org)
            await session.flush()

            created_users = []
            for name, email, role, title in comp_data["users"]:
                u = User(
                    id=str(uuid.uuid4()),
                    organization_id=org.id,
                    name=name,
                    email=email.lower(),
                    hashed_password=default_pwd_hash,
                    role=role,
                    is_active=True,
                )
                session.add(u)
                created_users.append(u)

            # Create Projects for Tenant
            proj1 = Project(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                name=f"{comp_data['name']} Creative Production",
                description=f"Complete visual overhaul & ad design system for {comp_data['name']}.",
                status=ProjectStatus.RUNNING,
                progress=65,
                next_step="Awaiting review of September Ad Creatives",
                expected_date=today + timedelta(days=14),
            )
            session.add(proj1)

            # Create Milestones for Project
            m1 = ProjectMilestone(
                id=str(uuid.uuid4()),
                project_id=proj1.id,
                organization_id=org.id,
                title="Creative Strategy",
                description="Finalized visual direction & brand messaging.",
                status=MilestoneStatus.COMPLETED,
                expected_date=today - timedelta(days=5),
                completed_at=now - timedelta(days=5),
            )
            m2 = ProjectMilestone(
                id=str(uuid.uuid4()),
                project_id=proj1.id,
                organization_id=org.id,
                title="Creative Production",
                description="Production of static and video ad assets.",
                status=MilestoneStatus.IN_PROGRESS,
                expected_date=today + timedelta(days=3),
            )
            m3 = ProjectMilestone(
                id=str(uuid.uuid4()),
                project_id=proj1.id,
                organization_id=org.id,
                title="Campaign Launch",
                description="Launch new Meta and Google ad campaigns.",
                status=MilestoneStatus.UPCOMING,
                expected_date=today + timedelta(days=12),
            )
            session.add_all([m1, m2, m3])

            # Tasks for Tenant
            t1 = Task(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                project_id=proj1.id,
                title="Review September Ad Creatives",
                description="Please review the new ad concepts and approve or request changes.",
                status=TaskStatus.READY_FOR_REVIEW,
                priority=TaskPriority.HIGH,
                assigned_to_user_id=created_users[0].id,
                created_by_user_id=admin_user.id,
                due_date=today + timedelta(days=2),
                requires_client_approval=True,
                approval_status=ApprovalStatus.PENDING,
            )
            t2 = Task(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                project_id=proj1.id,
                title="Finalize Typography Guidelines",
                description="Review font pairings and line height ratios.",
                status=TaskStatus.IN_PROGRESS,
                priority=TaskPriority.MEDIUM,
                assigned_to_user_id=created_users[0].id,
                created_by_user_id=admin_user.id,
                due_date=today + timedelta(days=5),
                requires_client_approval=False,
                approval_status=ApprovalStatus.NOT_REQUIRED,
            )
            t3 = Task(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                project_id=proj1.id,
                title="Approve iOS UI Components",
                description="Sign off on glassmorphism card components.",
                status=TaskStatus.COMPLETED,
                priority=TaskPriority.HIGH,
                assigned_to_user_id=created_users[0].id,
                created_by_user_id=admin_user.id,
                due_date=today - timedelta(days=2),
                requires_client_approval=True,
                approval_status=ApprovalStatus.APPROVED,
                completed_at=now - timedelta(days=2),
            )
            session.add_all([t1, t2, t3])

            # Task Comments
            tc1 = TaskComment(
                id=str(uuid.uuid4()),
                task_id=t1.id,
                organization_id=org.id,
                user_id=admin_user.id,
                message="Hi team, the ad concepts are uploaded. Please review Creative 4 in particular.",
            )
            session.add(tc1)

            # Task Approval History for completed task
            h1 = TaskApprovalHistory(
                id=str(uuid.uuid4()),
                task_id=t3.id,
                organization_id=org.id,
                user_id=created_users[0].id,
                action="APPROVED",
                comment="Looks crisp and elegant. Approved!",
                created_at=now - timedelta(days=2),
            )
            session.add(h1)

            # 1-on-1 Encrypted Direct Conversations & Messages for EACH Tenant User
            from app.core.crypto import encrypt_message

            for u in created_users:
                conv = Conversation(
                    id=str(uuid.uuid4()),
                    organization_id=org.id,
                    title=f"Direct: {u.name} & Throttle Admin",
                    is_direct=True,
                    is_encrypted=True,
                )
                session.add(conv)

                # Add 1-on-1 participants (Client User <-> Admin)
                p_admin = ConversationParticipant(
                    id=str(uuid.uuid4()),
                    conversation_id=conv.id,
                    user_id=admin_user.id,
                )
                p_user = ConversationParticipant(
                    id=str(uuid.uuid4()),
                    conversation_id=conv.id,
                    user_id=u.id,
                )
                session.add_all([p_admin, p_user])

                msg1 = Message(
                    id=str(uuid.uuid4()),
                    conversation_id=conv.id,
                    organization_id=org.id,
                    sender_user_id=admin_user.id,
                    message=encrypt_message(f"Hi {u.name}, welcome to your 1-on-1 encrypted channel with Throttle Admin."),
                    created_at=now - timedelta(days=1),
                    read_at=now - timedelta(days=1),
                )
                msg2 = Message(
                    id=str(uuid.uuid4()),
                    conversation_id=conv.id,
                    organization_id=org.id,
                    sender_user_id=u.id,
                    message=encrypt_message(f"Thanks! Excited to work together on our projects."),
                    created_at=now - timedelta(hours=3),
                    read_at=now - timedelta(hours=3),
                )
                session.add_all([msg1, msg2])

            # Targeted Notifications for Tenant Users
            n1 = Notification(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                recipient_user_id=created_users[0].id,
                type=NotificationType.TASK_APPROVAL_REQUIRED,
                title="Task Review Required",
                message="September Ad Creatives are ready for your review.",
                entity_type="task",
                entity_id=t1.id,
                is_read=False,
            )
            session.add(n1)

            # Activities for Tenant
            act1 = Activity(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                actor_user_id=admin_user.id,
                type="task_created",
                entity_type="task",
                entity_id=t1.id,
                description=f"Throttle Admin created task: Review September Ad Creatives",
                created_at=now - timedelta(hours=4),
            )
            act2 = Activity(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                actor_user_id=created_users[0].id,
                type="task_approved",
                entity_type="task",
                entity_id=t3.id,
                description=f"{created_users[0].name} approved task: Approve iOS UI Components",
                created_at=now - timedelta(days=2),
            )
            session.add_all([act1, act2])

            # Seed Meta Connection & Analytics Data for BLUEFORCE
            if comp_data["slug"] == "blueforce":
                from app.models.meta import MetaConnection, MetaConnectionStatus, MetaCampaign, MetaDailyInsight, MetaInsightLevel

                meta_conn = MetaConnection(
                    id=str(uuid.uuid4()),
                    organization_id=org.id,
                    meta_user_id="meta_user_998877",
                    business_id="biz_44332211",
                    ad_account_id="act_1020304050",
                    ad_account_name="BLUEFORCE Official Meta Ads",
                    encrypted_access_token=encrypt_message("EAABsbCS78...mock_token"),
                    token_expires_at=now + timedelta(days=60),
                    status=MetaConnectionStatus.SYNCED,
                    last_synced_at=now,
                )
                session.add(meta_conn)

                # Seed 3 Campaigns for Blueforce
                c1 = MetaCampaign(
                    id=str(uuid.uuid4()),
                    organization_id=org.id,
                    ad_account_id="act_1020304050",
                    meta_campaign_id="cmp_101",
                    name="Q3 Performance Max - Conversions",
                    status="ACTIVE",
                    objective="OUTCOME_SALES",
                )
                c2 = MetaCampaign(
                    id=str(uuid.uuid4()),
                    organization_id=org.id,
                    ad_account_id="act_1020304050",
                    meta_campaign_id="cmp_102",
                    name="Retargeting High-Intent Visitors",
                    status="ACTIVE",
                    objective="OUTCOME_LEADS",
                )
                c3 = MetaCampaign(
                    id=str(uuid.uuid4()),
                    organization_id=org.id,
                    ad_account_id="act_1020304050",
                    meta_campaign_id="cmp_103",
                    name="Brand Awareness & Video Views",
                    status="PAUSED",
                    objective="OUTCOME_AWARENESS",
                )
                session.add_all([c1, c2, c3])

                # Seed 30 days of ACCOUNT & CAMPAIGN insights
                import random
                rng = random.Random(42)  # Deterministic seed for repeatable insights

                for day_offset in range(30):
                    d = today - timedelta(days=29 - day_offset)
                    # Account level
                    spend_acc = round(rng.uniform(450.0, 850.0), 2)
                    impressions_acc = rng.randint(25000, 50000)
                    reach_acc = int(impressions_acc * rng.uniform(0.75, 0.9))
                    clicks_acc = rng.randint(800, 1800)
                    link_clicks_acc = int(clicks_acc * rng.uniform(0.65, 0.85))
                    ctr_acc = round((clicks_acc / impressions_acc) * 100, 2)
                    cpc_acc = round(spend_acc / clicks_acc, 2)
                    cpm_acc = round((spend_acc / impressions_acc) * 1000, 2)
                    leads_acc = rng.randint(15, 45)
                    cpl_acc = round(spend_acc / leads_acc, 2)
                    conversions_acc = rng.randint(20, 60)
                    conv_val_acc = round(spend_acc * rng.uniform(2.8, 4.2), 2)
                    roas_acc = round(conv_val_acc / spend_acc, 2)

                    acc_insight = MetaDailyInsight(
                        id=str(uuid.uuid4()),
                        organization_id=org.id,
                        ad_account_id="act_1020304050",
                        meta_campaign_id=None,
                        level=MetaInsightLevel.ACCOUNT,
                        date=d,
                        spend=spend_acc,
                        impressions=impressions_acc,
                        reach=reach_acc,
                        clicks=clicks_acc,
                        link_clicks=link_clicks_acc,
                        ctr=ctr_acc,
                        cpc=cpc_acc,
                        cpm=cpm_acc,
                        leads=leads_acc,
                        cpl=cpl_acc,
                        conversions=conversions_acc,
                        conversion_value=conv_val_acc,
                        roas=roas_acc,
                    )
                    session.add(acc_insight)

                    # Campaign level for c1
                    spend_c1 = round(spend_acc * 0.6, 2)
                    imp_c1 = int(impressions_acc * 0.6)
                    clk_c1 = int(clicks_acc * 0.65)
                    c1_insight = MetaDailyInsight(
                        id=str(uuid.uuid4()),
                        organization_id=org.id,
                        ad_account_id="act_1020304050",
                        meta_campaign_id="cmp_101",
                        level=MetaInsightLevel.CAMPAIGN,
                        date=d,
                        spend=spend_c1,
                        impressions=imp_c1,
                        reach=int(imp_c1 * 0.8),
                        clicks=clk_c1,
                        link_clicks=int(clk_c1 * 0.8),
                        ctr=round((clk_c1 / imp_c1) * 100, 2) if imp_c1 else 0.0,
                        cpc=round(spend_c1 / clk_c1, 2) if clk_c1 else 0.0,
                        cpm=round((spend_c1 / imp_c1) * 1000, 2) if imp_c1 else 0.0,
                        leads=int(leads_acc * 0.7),
                        cpl=round(spend_c1 / (leads_acc * 0.7), 2) if leads_acc else 0.0,
                        conversions=int(conversions_acc * 0.7),
                        conversion_value=round(conv_val_acc * 0.7, 2),
                        roas=round((conv_val_acc * 0.7) / spend_c1, 2) if spend_c1 else 0.0,
                    )
                    session.add(c1_insight)

        await session.commit()
        print("Seeding Phase 2 completed successfully!")
        print("--------------------------------------------------")
        print("Admin Login: admin@throttle.agency / admin123")
        print("Sample Client Logins (password: password123):")
        print(" - raj@blueforce.com (BLUEFORCE)")
        print(" - john@acme.com (Acme Corp)")
        print(" - user@testcompany.com (Test Company)")
        print("--------------------------------------------------")


if __name__ == "__main__":
    asyncio.run(seed())
