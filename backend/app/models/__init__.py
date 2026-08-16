"""Import every model module so Base.metadata is fully populated for Alembic autogenerate and tests."""
from app.models.ai import AIConversation, AIMessage  # noqa: F401
from app.models.ai_practice import AIGeneratedQuestion, AIGeneratedQuestionOption, AIMockAnswer, AIMockSession  # noqa: F401
from app.models.assessment import Exam, ExamAnswer, ExamAttempt, Question, QuestionOption, Quiz, QuizAnswer, QuizAttempt  # noqa: F401
from app.models.attendance import AttendanceRecord, AttendanceSession  # noqa: F401
from app.models.certificate import Certificate  # noqa: F401
from app.models.challenge import DailyChallenge, DailyChallengeAttempt  # noqa: F401
from app.models.contest import Contest, ContestAnswer, ContestAttempt, ContestCertificate  # noqa: F401
from app.models.discussion import DiscussionReply, DiscussionThread, DiscussionVote  # noqa: F401
from app.models.gamification import Achievement, Badge, LeaderboardSnapshot, PointsLedger, Streak  # noqa: F401
from app.models.lms import Course, CourseProgress, CourseSection, Enrollment, Lesson, LessonProgress, LessonResource  # noqa: F401
from app.models.practice import PracticeAnswer, PracticeSession, QuestionBookmark  # noqa: F401
from app.models.scheduling import RegistrationWindow, ScheduledExamConfig  # noqa: F401
from app.models.social import ChatMember, ChatMessage, ChatRoom, MessageRead, Notification, NotificationPreference, PushSubscription  # noqa: F401
from app.models.system import AnalyticsEvent, AuditLog, FileObject, SupportTicket, SystemSetting  # noqa: F401
from app.models.timetable import TimetableEntry  # noqa: F401
from app.models.user import EmailVerification, PasswordReset, Permission, Profile, RefreshToken, Role, RolePermission, Session, User, UserRole  # noqa: F401
