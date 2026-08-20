"""Import every model module so Base.metadata is fully populated for Alembic autogenerate and tests."""
from app.models.ai import AIConversation, AIMessage  # noqa: F401
from app.models.ai_practice import (  # noqa: F401
    AIGeneratedQuestion,
    AIGeneratedQuestionOption,
    AIMockAnswer,
    AIMockSession,
)
from app.models.assessment import Question, QuestionOption  # noqa: F401
from app.models.campus_timetable import CampusTimetableEntry, CampusTimetableSource  # noqa: F401
from app.models.challenge import DailyChallenge, DailyChallengeAttempt  # noqa: F401
from app.models.contest import (  # noqa: F401
    Contest,
    ContestAnswer,
    ContestAttempt,
    ContestCertificate,
)
from app.models.elimination import (  # noqa: F401
    EliminationAnswer,
    EliminationBattle,
    EliminationInvitation,
    EliminationParticipant,
    EliminationRound,
)
from app.models.exam_platform import (  # noqa: F401
    Subject,
    Topic,
    TopicDifficultyEvaluation,
    University,
)
from app.models.gamification import (  # noqa: F401
    Achievement,
    Badge,
    LeaderboardSnapshot,
    PointsLedger,
    Streak,
)
from app.models.practice import PracticeAnswer, PracticeSession, QuestionBookmark  # noqa: F401
from app.models.scheduling import AIExamRegistrationWindow  # noqa: F401
from app.models.social import (  # noqa: F401
    ChatMember,
    ChatMessage,
    ChatRoom,
    MessageRead,
    Notification,
    NotificationPreference,
    PushSubscription,
)
from app.models.social_graph import FollowRequest  # noqa: F401
from app.models.system import (  # noqa: F401
    AnalyticsEvent,
    AuditLog,
    FileObject,
    SupportTicket,
    SystemSetting,
)
from app.models.user import (  # noqa: F401
    EmailVerification,
    InstructorApplication,
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
