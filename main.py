
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import settings
from database import Base, engine
from exceptions import register_exception_handlers
# Register models with SQLAlchemy metadata
from models.user import User
from models.customer import Customer
from models.feedback import Feedback
from models.feedback_history import FeedbackHistory
from models.category import Category
from models.complaint import Complaint
from models.complaint_assignment_history import ComplaintAssignmentHistory
from models.complaint_comment import ComplaintComment
from models.complaint_status_history import ComplaintStatusHistory
from models.audit_log import AuditLog

# Import API routers
from routes.auth import router as auth_router
from routes.users import router as users_router
from routes.customers import router as customers_router
from routes.feedback import router as feedback_router
from routes.categories import router as categories_router
from routes.complaints import router as complaints_router
from routes.agent_assignments import router as agent_assignments_router
from routes.resolution_workflow import router as resolution_workflow_router
from routes.sla import router as sla_router
from routes.analytics import router as analytics_router
from routes.reports import router as reports_router
from routes.audit_logs import router as audit_logs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Customer feedback, complaint tracking, "
        "support workflows, and analytics API."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

register_exception_handlers(app)


# Authentication APIs
app.include_router(
    auth_router,
    prefix=settings.API_V1_PREFIX,
)

# User management APIs
app.include_router(
    users_router,
    prefix=settings.API_V1_PREFIX,
)

# Customer management APIs - Level 2
app.include_router(
    customers_router,
    prefix=settings.API_V1_PREFIX,
)

app.include_router(
    feedback_router,
    prefix=settings.API_V1_PREFIX,
)


app.include_router(
    categories_router,
    prefix=settings.API_V1_PREFIX,
)

app.include_router(
    complaints_router,
    prefix=settings.API_V1_PREFIX,
)


app.include_router(
    agent_assignments_router,
    prefix=settings.API_V1_PREFIX,
)




app.include_router(
    resolution_workflow_router,
    prefix=settings.API_V1_PREFIX,
)

app.include_router(
    sla_router,
    prefix=settings.API_V1_PREFIX,
)



app.include_router(
    analytics_router,
    prefix=settings.API_V1_PREFIX,
)

app.include_router(
    reports_router,
    prefix=settings.API_V1_PREFIX,
)


app.include_router(
    audit_logs_router,
    prefix=settings.API_V1_PREFIX,
)

@app.get("/", tags=["Health"])
def health_check():
    return {
        "message": "Customer Feedback & Complaint Management API",
        "status": "running",
    }
