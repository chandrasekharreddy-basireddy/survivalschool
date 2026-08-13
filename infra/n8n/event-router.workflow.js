// Reference copy of the workflow created in the user's n8n instance via the
// n8n MCP tools. This file is NOT executed by n8n directly (n8n stores the
// workflow itself) -- it's checked into the repo so the automation logic is
// versioned and reviewable like any other code, per spec section 20.
import { workflow, node, trigger, switchCase, expr } from '@n8n/workflow-sdk';

const webhookTrigger = trigger({
  type: 'n8n-nodes-base.webhook',
  version: 2.1,
  config: {
    name: 'Survival School Event',
    parameters: {
      httpMethod: 'POST',
      path: 'survivalschool/events',
      responseMode: 'responseNode',
      authentication: 'none', // see docs/N8N.md: add headerAuth + N8N_WEBHOOK_SECRET before production
      options: {},
    },
  },
});

const routeByEvent = switchCase({
  version: 3.4,
  config: {
    name: 'Route by Event Type',
    parameters: {
      rules: {
        values: [
          { outputKey: 'student_registered', conditions: eq('student.registered') },
          { outputKey: 'course_enrolled', conditions: eq('course.enrolled') },
          { outputKey: 'quiz_completed', conditions: eq('quiz.completed') },
          { outputKey: 'exam_completed', conditions: eq('exam.completed') },
          { outputKey: 'certificate_issued', conditions: eq('certificate.issued') },
          { outputKey: 'inactivity_reminder', conditions: eq('student.inactive') },
        ],
      },
      options: { fallbackOutput: 'extra', renameFallbackOutput: 'Unhandled' },
    },
  },
});

function eq(value) {
  return {
    options: { caseSensitive: false, leftValue: '', typeValidation: 'strict' },
    conditions: [{ leftValue: expr('{{ $json.body.event_type }}'), operator: { type: 'string', operation: 'equals' }, rightValue: value }],
    combinator: 'and',
  };
}

function messageNode(name, subjectExpr, bodyExpr) {
  return node({
    type: 'n8n-nodes-base.set',
    version: 3.5,
    config: {
      name,
      parameters: {
        mode: 'manual',
        includeOtherFields: true,
        assignments: {
          assignments: [
            { id: 'subject', name: 'notification.subject', value: expr(subjectExpr), type: 'string' },
            { id: 'body', name: 'notification.body', value: expr(bodyExpr), type: 'string' },
            { id: 'recipient', name: 'notification.recipient', value: expr('{{ $json.body.email }}'), type: 'string' },
            { id: 'channel', name: 'notification.channel', value: 'email', type: 'string' },
          ],
        },
      },
    },
  });
}

const studentRegistered = messageNode(
  'Build: Welcome Email',
  '{{ "Verify your Survival School account" }}',
  '{{ "Welcome " + $json.body.full_name + " — verify your email to get started." }}'
);
const courseEnrolled = messageNode(
  'Build: Enrollment Email',
  '{{ "You are enrolled in " + $json.body.course_title }}',
  '{{ "Jump back in whenever you are ready: " + $json.body.course_url }}'
);
const quizCompleted = messageNode(
  'Build: Quiz Result Email',
  '{{ "Result: " + $json.body.assessment_title }}',
  '{{ "You scored " + $json.body.score_percent + "%." }}'
);
const examCompleted = messageNode(
  'Build: Exam Result Email',
  '{{ "Exam result: " + $json.body.assessment_title }}',
  '{{ "You scored " + $json.body.score_percent + "%." }}'
);
const certificateIssued = messageNode(
  'Build: Certificate Email',
  '{{ "Certificate earned: " + $json.body.course_title }}',
  '{{ "Certificate " + $json.body.certificate_number + " is ready to view and verify." }}'
);
const inactivityReminder = messageNode(
  'Build: Inactivity Reminder',
  '{{ "We saved your spot" }}',
  '{{ "You were " + $json.body.percent_complete + "% through " + $json.body.course_title + " — pick up where you left off." }}'
);

const respond = node({
  type: 'n8n-nodes-base.respondToWebhook',
  version: 1.5,
  config: {
    name: 'Respond',
    parameters: {
      respondWith: 'json',
      responseBody: expr('{{ $json.notification }}'),
      options: { responseCode: 200 },
    },
  },
});

export default workflow('survivalschool-event-router', 'Survival School — Event Router')
  .add(webhookTrigger)
  .to(
    routeByEvent
      .onCase(0, studentRegistered.to(respond))
      .onCase(1, courseEnrolled.to(respond))
      .onCase(2, quizCompleted.to(respond))
      .onCase(3, examCompleted.to(respond))
      .onCase(4, certificateIssued.to(respond))
      .onCase(5, inactivityReminder.to(respond))
      .onCase(6, respond) // fallback/unhandled — echo back as-is
  );
