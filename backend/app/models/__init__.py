"""Import every model module so Base.metadata is fully populated for Alembic
autogenerate and for create_all() in tests."""
from app.models.ai import AIConversation, AIMessage  # noqa: F401
from app.models.assessment import (  # noqa: F401
    Exam,
    ExamAnswer,
    ExamAttempt,
    Question,
    QuestionOption,
    Quiz,
    QuizAnswer,
    QuizAttempt,
)
from app.models.certificate import Certificate  # noqa: F401
from app.models.discussion import DiscussionReply, DiscussionThread, DiscussionVote  # noqa: F401
from app.models.gamification import (  # noqa: F401
    Achievement,
    Badge,
    LeaderboardSnapshot,
    PointsLedger,
    Streak,
)
from app.models.lms import (  # noqa: F401
    Course,
    CourseProgress,
    CourseSection,
    Enrollment,
    Lesson,
    LessonProgress,
    LessonResource,
)
from app.models.practice import PracticeAnswer, PracticeSession, QuestionBookmark  # noqa: F401
from app.models.social import (  # noqa: F401
    ChatMember,
    ChatMessage,
    ChatRoom,
    MessageRead,
    Notification,
    NotificationPreference,
)
from app.models.system import (  # noqa: F401
    AnalyticsEvent,
    AuditLog,
    FileObject,
    SupportTicket,
    SystemSetting,
)
from app.models.timetable import TimetableEntry  # noqa: F401
from app.models.user import (  # noqa: F401
    EmailVerification,
    PasswordReset,
    Permission,
    Profile,
    RefreshToken,
    Role,
    RolePermission,
    Session,
    User,
    UserRole,
)
