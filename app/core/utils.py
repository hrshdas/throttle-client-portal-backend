HUMAN_STATUS_MAP = {
    "TODO": "Upcoming",
    "IN_PROGRESS": "We're working on it",
    "READY_FOR_REVIEW": "Ready for your review",
    "COMPLETED": "Completed",
    "CANCELLED": "Cancelled",
    "PLANNING": "Planning phase",
    "RUNNING": "In active campaign",
    "IN_DEVELOPMENT": "Under development",
    "PAUSED": "Paused",
}

HUMAN_APPROVAL_MAP = {
    "NOT_REQUIRED": "No review needed",
    "PENDING": "Awaiting your review",
    "APPROVED": "Approved",
    "CHANGES_REQUESTED": "Changes requested",
}


def get_human_status(status_val: str | None) -> str:
    if not status_val:
        return ""
    return HUMAN_STATUS_MAP.get(status_val, status_val.replace("_", " ").title())


def get_human_approval_status(approval_val: str | None) -> str:
    if not approval_val:
        return ""
    return HUMAN_APPROVAL_MAP.get(approval_val, approval_val.replace("_", " ").title())
