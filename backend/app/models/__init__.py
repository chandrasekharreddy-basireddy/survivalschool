"""Import every model module so Base.metadata is fully populated for Alembic autogenerate and tests."""
from app.models.ai import AIConversation, AIMessage  # noqa: F401
from app.models.ai_practice import (  # noqa: F401
    AIGeneratedQuestion,
    AIGeneratedQuestionOption,
    AIMockAnswer,
    AIMockSession,
)
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
from app.models.attendance import AttendanceRecord, AttendanceSession  # noqa: F401
from app.models.campus_timetable import CampusTimetableEntry, CampusTimetableSource  # noqa: F401
from app.models.certificate import Certificate  # noqa: F401
from app.models.challenge import DailyChallenge, DailyChallengeAttempt  # noqa: F401
from app.models.classroom import (  # noqa: F401
    Announcement,
    AnnouncementComment,
    Assignment,
    AssignmentComment,
    AssignmentSubmission,
)
from app.models.contest import (  # noqa: F401
    Contest,
    ContestAnswer,
    ContestAttempt,
    ContestCertificate,
)
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
from app.models.scheduling import RegistrationWindow, ScheduledExamConfig  # noqa: F401
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
from app.models.timetable import TimetableEntry  # noqa: F401
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
