type MockPayload = {
  action?: unknown;
  [key: string]: unknown;
};

type MockAction = {
  actionId: string;
  actionType: string;
  priority: string;
  practiceId: string;
  status: string;
  patientId: string | null;
  patientName: string | null;
  patientRequestId: string | null;
  timeLabel: string;
  sourceSummary: string;
  sourceMessage: string | null;
  draftMessage: string | null;
  finalMessage: string | null;
  approvedAt: string | null;
  approvedBy: string | null;
  completedAt: string | null;
  completionNote: string | null;
  createdAt: string;
  updatedAt: string;
  externalDraftId: string | null;
  externalSentMessageId: string | null;
  metadata: Record<string, unknown>;
  sourceProvider: string;
  sourceThreadId: string | null;
  sourceMessageId: string | null;
};

const mockPracticeId = "practice_mock_doctor";

type MockIntegration = {
  integrationId: string;
  provider: string;
  status: string;
  accountEmail: string | null;
  calendarId: string | null;
  lastSyncAt: string | null;
  lastError: string | null;
  requiredScopes: string[];
  writeMode: string;
  connectedAt: string | null;
};

const nowIso = () => new Date().toISOString();

const actions: MockAction[] = [
  {
    actionId: "act_001",
    actionType: "appointment_request",
    priority: "new",
    practiceId: mockPracticeId,
    status: "needs_approval",
    patientId: "p10",
    patientName: "Rachel Davies",
    patientRequestId: "seed-request-rachel-davies",
    timeLabel: "9:41 AM",
    sourceSummary: "New patient referred by GP, wants initial consultation",
    sourceMessage:
      "Hi, I was referred by Dr. Patel at the Angel Medical Centre. I'd like to book an initial consultation at your earliest convenience. I'm flexible on days but prefer afternoons if possible. Thank you, Rachel",
    sourceProvider: "gmail",
    sourceThreadId: "gmail-thread-rachel-davies",
    sourceMessageId: "gmail-message-rachel-davies",
    draftMessage:
      "Dear Rachel,\n\nThank you for getting in touch, and welcome. I have the following afternoon slots available:\n\n- Wednesday 30 Apr at 2:00 PM\n- Friday 2 May at 3:15 PM\n- Monday 5 May at 2:30 PM\n\nInitial consultations are 45 minutes. Please let me know which works best and I will confirm your booking.\n\nWarm regards,\nDr. Shalini's Clinic",
    externalDraftId: null,
    externalSentMessageId: null,
    metadata: {
      request_type: "appointment_request",
      urgency_level: "routine",
      risk_level: "low",
      requires_doctor_review: false,
      suggested_next_action: "Review proposed availability windows and approve the reply text.",
      patient_emotional_tone: "neutral",
      triage_category: "appointment_request",
      triage_confidence: "0.72",
      triage_reason: "Message matched patient scheduling language.",
    },
    finalMessage: null,
    approvedAt: null,
    approvedBy: null,
    completedAt: null,
    completionNote: null,
    createdAt: "2026-05-02T08:41:00+00:00",
    updatedAt: "2026-05-02T08:41:00+00:00",
  },
  {
    actionId: "act_002",
    actionType: "reschedule_cancellation",
    priority: "action",
    practiceId: mockPracticeId,
    status: "needs_approval",
    patientId: "p8",
    patientName: "Fatima Ali",
    patientRequestId: "seed-request-fatima-ali",
    timeLabel: "8:15 AM",
    sourceSummary: "Wants to move Friday appointment to next week",
    sourceMessage:
      "Hi, I'm afraid something has come up and I won't be able to make my Friday appointment. Could we reschedule to sometime next week? Monday or Tuesday would be ideal. Thanks, Fatima",
    sourceProvider: "gmail",
    sourceThreadId: "gmail-thread-fatima-ali",
    sourceMessageId: "gmail-message-fatima-ali",
    draftMessage:
      "Dear Fatima,\n\nOf course, no problem at all. I can offer the following options for next week:\n\n- Monday 5 May at 11:00 AM\n- Tuesday 6 May at 10:30 AM\n- Tuesday 6 May at 3:00 PM\n\nPlease let me know your preference.\n\nBest wishes,\nDr. Shalini's Clinic",
    externalDraftId: null,
    externalSentMessageId: null,
    metadata: {
      request_type: "reschedule_cancellation",
      urgency_level: "soon",
      risk_level: "low",
      requires_doctor_review: false,
      suggested_next_action: "Review the draft and confirm the scheduling next step with the patient.",
      patient_emotional_tone: "neutral",
      triage_category: "reschedule_cancellation",
      triage_confidence: "0.86",
      triage_reason: "Message is about changing an existing appointment.",
    },
    finalMessage: null,
    approvedAt: null,
    approvedBy: null,
    completedAt: null,
    completionNote: null,
    createdAt: "2026-05-02T07:15:00+00:00",
    updatedAt: "2026-05-02T07:15:00+00:00",
  },
  {
    actionId: "act_003",
    actionType: "nhs",
    priority: "info",
    practiceId: mockPracticeId,
    status: "proposed",
    patientId: null,
    patientName: null,
    patientRequestId: "seed-request-nhs-clinic",
    timeLabel: "7:30 AM",
    sourceSummary: "NHS clinic confirmed for Wednesday",
    sourceMessage: "Wednesday 30 Apr, 8:30 AM - 1:00 PM\nSt Mary's Hospital, Praed Street\n4 patients scheduled",
    sourceProvider: "google_calendar",
    sourceThreadId: null,
    sourceMessageId: null,
    draftMessage: null,
    externalDraftId: null,
    externalSentMessageId: null,
    metadata: {
      request_type: "schedule_note",
      urgency_level: "routine",
      risk_level: "low",
      requires_doctor_review: false,
      suggested_next_action: "No external calendar action is available in the MVP.",
      patient_emotional_tone: "neutral",
      triage_category: "schedule_note",
      triage_confidence: "0.80",
      triage_reason: "Calendar note loaded as read-only context.",
    },
    finalMessage: null,
    approvedAt: null,
    approvedBy: null,
    completedAt: null,
    completionNote: "Calendar write intentionally deferred from MVP.",
    createdAt: "2026-05-02T06:30:00+00:00",
    updatedAt: "2026-05-02T06:30:00+00:00",
  },
  {
    actionId: "act_004",
    actionType: "follow_up",
    priority: "info",
    practiceId: mockPracticeId,
    status: "needs_approval",
    patientId: "p9",
    patientName: "Priya Sharma",
    patientRequestId: "seed-request-priya-sharma",
    timeLabel: "Auto",
    sourceSummary: "Follow-up due - last seen 4 weeks ago",
    sourceMessage: null,
    sourceProvider: "gmail",
    sourceThreadId: "gmail-thread-priya-sharma",
    sourceMessageId: null,
    draftMessage:
      "Dear Priya,\n\nI hope you are well. It has been about four weeks since your last visit and I would like to schedule a follow-up to review your progress. I have availability on:\n\n- Friday 2 May at 10:00 AM\n- Monday 5 May at 9:30 AM\n\nPlease let me know if either works, or suggest a time that suits you better.\n\nBest wishes,\nDr. Shalini's Clinic",
    externalDraftId: null,
    externalSentMessageId: null,
    metadata: {
      request_type: "follow_up",
      urgency_level: "routine",
      risk_level: "low",
      requires_doctor_review: false,
      suggested_next_action: "Review the follow-up draft and decide the next admin step.",
      patient_emotional_tone: "neutral",
      triage_category: "follow_up",
      triage_confidence: "0.80",
      triage_reason: "Follow-up is due based on prior clinic timing.",
    },
    finalMessage: null,
    approvedAt: null,
    approvedBy: null,
    completedAt: null,
    completionNote: null,
    createdAt: "2026-05-02T06:00:00+00:00",
    updatedAt: "2026-05-02T06:00:00+00:00",
  },
];

const basePatients = [
  {
    patientId: "p1",
    name: "Emma Richardson",
    email: "emma.r@gmail.com",
    phone: "07412 345 678",
    lastVisit: "28 Apr 2026",
    nextAppt: "-",
    visits: 4,
    status: "active",
    notes: "Reviewing hormone panel results. TSH slightly elevated - may need dose adjustment. Prefers morning slots.",
  },
  {
    patientId: "p2",
    name: "Lucy Chen",
    email: "lucy.chen@outlook.com",
    phone: "07891 234 567",
    lastVisit: "28 Apr 2026",
    nextAppt: "-",
    visits: 1,
    status: "new",
    notes: "Referred by Dr. Patel at Angel Medical Centre. Irregular cycles and pelvic discomfort. GP referral letter on file.",
  },
  {
    patientId: "p3",
    name: "Sarah Mitchell",
    email: "s.mitchell@yahoo.com",
    phone: "07723 456 789",
    lastVisit: "28 Apr 2026",
    nextAppt: "-",
    visits: 3,
    status: "active",
    notes: "Follow-up on ultrasound. Small ovarian cyst detected - likely functional. Monitoring plan discussed.",
  },
  {
    patientId: "p8",
    name: "Fatima Ali",
    email: "fatima.ali@gmail.com",
    phone: "07978 901 234",
    lastVisit: "4 Apr 2026",
    nextAppt: "Fri 2 May, 11:00 AM",
    visits: 3,
    status: "active",
    notes: "Endometriosis management. Hormonal treatment - review symptom diary. May discuss surgical referral.",
  },
  {
    patientId: "p9",
    name: "Priya Sharma",
    email: "priya.sharma@gmail.com",
    phone: "07089 012 345",
    lastVisit: "31 Mar 2026",
    nextAppt: "-",
    visits: 6,
    status: "overdue",
    notes: "Long-term patient. PCOS management with metformin. Follow-up overdue - 4 weeks since last visit.",
  },
  {
    patientId: "p10",
    name: "Rachel Davies",
    email: "rachel.d@gmail.com",
    phone: "07190 123 456",
    lastVisit: "-",
    nextAppt: "Pending",
    visits: 0,
    status: "new",
    notes: "New enquiry via email. Referred by Dr. Patel, Angel Medical Centre. Prefers afternoon appointments.",
  },
];

const patients = basePatients.map((patient) => {
  const timeline = actions
    .filter((action) => action.patientId === patient.patientId && action.patientRequestId)
    .map((action) => ({
      actionId: action.actionId,
      createdAt: action.createdAt,
      description: action.sourceMessage || action.sourceSummary,
      kind: "patient_request",
      patientRequestId: action.patientRequestId || "",
      requestType: action.actionType,
      sourceMessageId: action.sourceMessageId,
      sourceProvider: action.sourceProvider,
      status: action.status,
      timeLabel: action.timeLabel,
      timelineId: `request-${action.patientRequestId}`,
      title: action.sourceSummary,
      updatedAt: action.updatedAt,
    }));
  return {
    ...patient,
    requestCount: timeline.length,
    openRequestCount: timeline.filter((entry) => entry.status !== "completed").length,
    lastRequestAt: timeline[0]?.createdAt || null,
    timeline,
  };
});

type MockScheduleEvent = {
  eventId: string;
  startTime: string;
  endTime: string;
  patientName: string;
  patientId: string | null;
  appointmentType: string;
  externalCalendarId: string;
  externalEventId: string;
  lastSyncedAt: string;
  sourceProvider: string;
  status: string;
};

const scheduleEventsByDate: Record<string, { dayType: string; events: MockScheduleEvent[] }> = {
  "2026-05-08": {
    dayType: "private",
    events: [
      {
        eventId: "2026-05-08-0900",
        startTime: "09:00",
        endTime: "09:45",
        patientName: "Emma Richardson",
        patientId: "p1",
        appointmentType: "Follow-up",
        externalCalendarId: "primary",
        externalEventId: "gcal-2026-05-08-0900",
        lastSyncedAt: "2026-05-02T00:00:00+00:00",
        sourceProvider: "google_calendar",
        status: "upcoming",
      },
      {
        eventId: "2026-05-08-1330",
        startTime: "13:30",
        endTime: "14:00",
        patientName: "Sarah Mitchell",
        patientId: "p3",
        appointmentType: "Follow-up",
        externalCalendarId: "primary",
        externalEventId: "gcal-2026-05-08-1330",
        lastSyncedAt: "2026-05-02T00:00:00+00:00",
        sourceProvider: "google_calendar",
        status: "upcoming",
      },
    ],
  },
  "2026-05-11": {
    dayType: "nhs",
    events: [
      {
        eventId: "2026-05-11-0830",
        startTime: "08:30",
        endTime: "13:00",
        patientName: "NHS Clinic - St Mary's",
        patientId: null,
        appointmentType: "NHS Duty",
        externalCalendarId: "primary",
        externalEventId: "gcal-2026-05-11-0830",
        lastSyncedAt: "2026-05-02T00:00:00+00:00",
        sourceProvider: "google_calendar",
        status: "nhs",
      },
      {
        eventId: "2026-05-11-1400",
        startTime: "14:00",
        endTime: "14:45",
        patientName: "Available",
        patientId: null,
        appointmentType: "Open slot",
        externalCalendarId: "primary",
        externalEventId: "gcal-2026-05-11-1400",
        lastSyncedAt: "2026-05-02T00:00:00+00:00",
        sourceProvider: "google_calendar",
        status: "open",
      },
    ],
  },
  "2026-05-15": {
    dayType: "private",
    events: [
      {
        eventId: "2026-05-15-1000",
        startTime: "10:00",
        endTime: "10:45",
        patientName: "Available",
        patientId: null,
        appointmentType: "Open slot",
        externalCalendarId: "primary",
        externalEventId: "gcal-2026-05-15-1000",
        lastSyncedAt: "2026-05-02T00:00:00+00:00",
        sourceProvider: "google_calendar",
        status: "open",
      },
      {
        eventId: "2026-05-15-1100",
        startTime: "11:00",
        endTime: "11:30",
        patientName: "Fatima Ali",
        patientId: "p8",
        appointmentType: "Follow-up",
        externalCalendarId: "primary",
        externalEventId: "gcal-2026-05-15-1100",
        lastSyncedAt: "2026-05-02T00:00:00+00:00",
        sourceProvider: "google_calendar",
        status: "upcoming",
      },
    ],
  },
};

const scheduleDays = Array.from({ length: 14 }, (_, offset) => {
  const date = new Date(Date.UTC(2026, 4, 8 + offset, 12));
  const dayDate = date.toISOString().slice(0, 10);
  const dayNumber = date.toLocaleDateString("en-GB", { day: "numeric", timeZone: "UTC" });
  const weekdayShort = date.toLocaleDateString("en-GB", { timeZone: "UTC", weekday: "short" });
  const weekdayLong = date.toLocaleDateString("en-GB", { timeZone: "UTC", weekday: "long" });
  const monthShort = date.toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" });
  const schedule = scheduleEventsByDate[dayDate] || { dayType: "private", events: [] };
  return {
    dayDate,
    dayKey: `${weekdayShort} ${dayNumber}`,
    dayLabel: `${weekdayLong} ${dayNumber} ${monthShort}`,
    dayType: schedule.dayType,
    events: schedule.events,
  };
});

const settings = {
  availabilityRules: [
    { day: "Monday", enabled: true, hours: "9:00 AM - 5:00 PM", type: "Private" },
    { day: "Tuesday", enabled: true, hours: "9:00 AM - 5:00 PM", type: "Private" },
    { day: "Wednesday", enabled: true, hours: "8:30 AM - 5:00 PM", type: "NHS + Private" },
    { day: "Thursday", enabled: true, hours: "9:00 AM - 5:00 PM", type: "NHS" },
    { day: "Friday", enabled: true, hours: "9:00 AM - 4:30 PM", type: "Private" },
  ],
  appointmentTypes: [
    { name: "Initial Consultation", duration: "45 min", color: "#3b82f6" },
    { name: "Follow-up", duration: "20 min", color: "#10b981" },
    { name: "Scan / Procedure", duration: "30 min", color: "#8b5cf6" },
  ],
  preferences: [
    { label: "Buffer between appointments", value: "15 min" },
    { label: "Lunch break", value: "1:00 - 1:30 PM" },
    { label: "Max patients per day", value: "8" },
    { label: "Auto-send confirmations", value: "Off" },
  ],
};

const integrations: MockIntegration[] = [
  {
    integrationId: "google_calendar",
    provider: "google_calendar",
    status: "ready_to_connect",
    accountEmail: null,
    calendarId: "primary",
    lastSyncAt: null,
    lastError: null,
    requiredScopes: ["https://www.googleapis.com/auth/calendar.events.readonly"],
    writeMode: "read_only_source_of_truth",
    connectedAt: null,
  },
  {
    integrationId: "gmail",
    provider: "gmail",
    status: "ready_to_connect",
    accountEmail: null,
    calendarId: null,
    lastSyncAt: null,
    lastError: null,
    requiredScopes: ["https://www.googleapis.com/auth/gmail.readonly"],
    writeMode: "read_inbox_prepare_in_app_drafts",
    connectedAt: null,
  },
];

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function patientRequestFromAction(action: MockAction) {
  const requestType = typeof action.metadata.request_type === "string" ? action.metadata.request_type : action.actionType;
  const urgencyLevel = typeof action.metadata.urgency_level === "string" ? action.metadata.urgency_level : "routine";
  const riskLevel = typeof action.metadata.risk_level === "string" ? action.metadata.risk_level : "low";
  const patientEmotionalTone =
    typeof action.metadata.patient_emotional_tone === "string" ? action.metadata.patient_emotional_tone : "neutral";
  const suggestedNextAction =
    typeof action.metadata.suggested_next_action === "string"
      ? action.metadata.suggested_next_action
      : "Review this request before responding.";
  const triageCategory =
    typeof action.metadata.triage_category === "string" ? action.metadata.triage_category : requestType;
  const triageConfidence =
    typeof action.metadata.triage_confidence === "string" ? Number(action.metadata.triage_confidence) : 0.9;
  const triageReason =
    typeof action.metadata.triage_reason === "string"
      ? action.metadata.triage_reason
      : "Mock patient request generated from the demo action queue.";
  return {
    appointmentType: action.actionType === "follow_up" ? "Follow-up" : "Initial Consultation",
    approvedAt: action.approvedAt,
    approvedBy: action.approvedBy,
    completedAt: action.completedAt,
    completionNote: action.completionNote,
    createdAt: action.createdAt,
    draftMessage: action.draftMessage,
    durationMinutes: action.actionType === "follow_up" ? 20 : 45,
    finalMessage: action.finalMessage,
    intent: action.actionType,
    patientEmail: null,
    patientEmotionalTone,
    patientId: action.patientId,
    patientName: action.patientName,
    patientRequestId: action.patientRequestId || action.actionId,
    practiceId: action.practiceId,
    proposedWindows: [],
    requestConstraints: {},
    requestType,
    requiresDoctorReview: action.metadata.requires_doctor_review === true,
    riskLevel,
    sourceExcerpt: action.sourceMessage,
    sourceMessageId: action.sourceMessageId,
    sourceProvider: action.sourceProvider,
    sourceSubject: action.sourceSummary,
    sourceSummary: action.sourceSummary,
    sourceThreadId: action.sourceThreadId,
    status: action.status,
    suggestedNextAction,
    timeLabel: action.timeLabel,
    triageCategory,
    triageConfidence,
    triageReason,
    urgencyLevel,
    updatedAt: action.updatedAt,
  };
}

function assertPayload(payload: unknown): MockPayload {
  if (!payload || typeof payload !== "object") {
    throw new Error("mock payload must be an object");
  }
  return payload as MockPayload;
}

function approveAction(payload: MockPayload) {
  const actionId = typeof payload.actionId === "string" ? payload.actionId : "";
  if (!actionId) {
    throw new Error("actionId is required");
  }

  const action = actions.find((item) => item.actionId === actionId);
  if (!action) {
    throw new Error(`action not found: ${actionId}`);
  }

  const timestamp = nowIso();
  action.status = "completed";
  action.approvedAt = timestamp;
  action.approvedBy = typeof payload.approvedBy === "string" && payload.approvedBy ? payload.approvedBy : "Dr. Shalini";
  action.completedAt = timestamp;
  action.completionNote =
    "Doctor approved and stored this action. No external email or calendar action was taken by the MVP.";
  action.finalMessage =
    typeof payload.finalMessage === "string" && payload.finalMessage.trim()
      ? payload.finalMessage.trim()
      : action.draftMessage || action.sourceSummary;
  action.updatedAt = timestamp;

  return {
    action: clone(action),
    message: "approval stored; no external action was taken",
  };
}

export async function callMockAgent(agentName: string, rawPayload: unknown): Promise<unknown> {
  const payload = assertPayload(rawPayload);
  if (agentName !== "clinic_agent") {
    throw new Error(`No mock registered for ${agentName}`);
  }

  if (payload.action === "list_actions") {
    const includeCompleted = payload.includeCompleted === true;
    return {
      actions: clone(actions.filter((item) => includeCompleted || item.status !== "completed")),
      practiceId: mockPracticeId,
    };
  }
  if (payload.action === "list_patient_requests") {
    const includeCompleted = payload.includeCompleted === true;
    return {
      patientRequests: clone(
        actions
          .filter((item) => item.sourceProvider === "gmail")
          .filter((item) => includeCompleted || item.status !== "completed")
          .map(patientRequestFromAction),
      ),
      practiceId: mockPracticeId,
    };
  }
  if (payload.action === "approve_action") {
    return approveAction(payload);
  }
  if (payload.action === "list_patients") {
    return { patients: clone(patients) };
  }
  if (payload.action === "list_schedule") {
    return { days: clone(scheduleDays) };
  }
  if (payload.action === "list_settings") {
    return clone(settings);
  }
  if (payload.action === "list_integrations") {
    return {
      integrations: clone(integrations),
      safety: {
        calendarWrites: "disabled",
        gmailSends: "requires_explicit_approval",
        tokenStorage: "external_secret_store",
      },
    };
  }
  if (payload.action === "connect_google_workspace") {
    const connectedAt = new Date().toISOString();
    for (const integration of integrations) {
      integration.status = "connected";
      integration.accountEmail = "doctor@example.com";
      integration.connectedAt = connectedAt;
      integration.lastError = null;
    }
    return {
      integrations: clone(integrations),
      message: "Google account connected. Tokens were stored in the configured secret store.",
      practiceId: mockPracticeId,
    };
  }
  if (payload.action === "sync_google_calendar") {
    const syncedAt = new Date().toISOString();
    const calendarIntegration = integrations.find((item) => item.integrationId === "google_calendar");
    if (calendarIntegration) {
      calendarIntegration.status = "connected";
      calendarIntegration.lastSyncAt = syncedAt;
      calendarIntegration.lastError = null;
    }
    const eventsRead = scheduleDays.reduce((count, day) => count + day.events.length, 0);
    return {
      status: "synced",
      sourceOfTruth: "google_calendar",
      writeMode: "read_only_cache",
      externalWrites: 0,
      eventsRead,
      appointmentsCached: eventsRead,
      message: "Calendar read completed. The local schedule cache was refreshed; Google Calendar was not changed.",
      days: clone(scheduleDays),
    };
  }
  if (payload.action === "scan_gmail_inbox") {
    const syncedAt = new Date().toISOString();
    const gmailIntegration = integrations.find((item) => item.integrationId === "gmail");
    if (gmailIntegration) {
      gmailIntegration.status = "connected";
      gmailIntegration.lastSyncAt = syncedAt;
      gmailIntegration.lastError = null;
    }
    const gmailActions = actions.filter((item) => item.sourceProvider === "gmail");
    return {
      status: "synced",
      sourceOfTruth: "gmail",
      writeMode: "read_inbox_prepare_in_app_drafts",
      externalWrites: 0,
      messagesScanned: gmailActions.length,
      proposedActions: gmailActions.length,
      message: "Gmail read completed. In-app action drafts were prepared; no email was sent or drafted in Gmail.",
      actions: clone(gmailActions),
      patientRequests: clone(gmailActions.map(patientRequestFromAction)),
      practiceId: mockPracticeId,
    };
  }

  throw new Error(`unsupported mock action: ${String(payload.action)}`);
}
