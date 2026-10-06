# Import all models so Alembic & SQLAlchemy can discover them for autogenerate
from app.core.database import Base  # noqa: F401
from app.models.organization import Organization  # noqa: F401
from app.models.user import User, RefreshToken  # noqa: F401
from app.models.invitation import Invitation, InvitationStatus  # noqa: F401
from app.models.project import (  # noqa: F401
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
from app.models.message import Conversation, ConversationParticipant, Message  # noqa: F401
from app.models.notification import Notification, NotificationType  # noqa: F401
from app.models.activity import Activity  # noqa: F401
from app.models.attachment import Attachment  # noqa: F401
from app.models.meta import (  # noqa: F401
    MetaConnection,
    MetaConnectionStatus,
    MetaCampaign,
    MetaAdSet,
    MetaAd,
    MetaDailyInsight,
    MetaInsightLevel,
)
