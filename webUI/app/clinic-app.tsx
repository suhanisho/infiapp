"use client";

import { useEffect, useMemo, useState } from "react";
import { signIn, signOut } from "next-auth/react";
import type {
  ClinicAgentApproveActionOutput,
  ClinicAgentApproveAndSendGmailOutput,
  ClinicAgentApproveSendAndBookCalendarOutput,
  ClinicAgentListActionsOutput,
  ClinicAgentListIntegrationsOutput,
  ClinicAgentListPatientsOutput,
  ClinicAgentListScheduleOutput,
  ClinicAgentListSettingsOutput,
  ClinicAgentScanGmailInboxOutput,
  ClinicAgentSyncGoogleCalendarOutput,
} from "@/src/lib/generated/mockAgents";
import { googleProviderId } from "@/src/lib/auth/providers";

type ClinicAction = ClinicAgentListActionsOutput["actions"][number];
type Patient = ClinicAgentListPatientsOutput["patients"][number];
type ScheduleDay = ClinicAgentListScheduleOutput["days"][number];
type Settings = ClinicAgentListSettingsOutput;
type Integration = ClinicAgentListIntegrationsOutput["integrations"][number];
type Tab = "actions" | "schedule" | "patients";
type ScheduleEvent = ScheduleDay["events"][number];

const SCHEDULE_DAYS_PER_PAGE = 7;

const emptySettings: Settings = {
  appointmentTypes: [],
  availabilityRules: [],
  preferences: [],
};

async function loadJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  const body = (await response.json()) as T & { error?: string };
  if (!response.ok) {
    throw new Error(body.error || "Request failed");
  }
  return body;
}

function statusLabel(status: string) {
  if (status === "needs_approval") {
    return "Needs approval";
  }
  if (status === "completed") {
    return "Completed";
  }
  if (status === "proposed") {
    return "Review";
  }
  if (status === "active") {
    return "Active";
  }
  if (status === "new") {
    return "New";
  }
  if (status === "overdue") {
    return "Follow-up due";
  }
  return status.replaceAll("_", " ");
}

function actionTypeLabel(type: string) {
  const labels: Record<string, string> = {
    appointment_request: "Appointment",
    billing_payment: "Billing",
    enquiry: "New enquiry",
    follow_up: "Follow-up",
    general_logistics: "Logistics",
    prescription_admin_request: "Prescription/admin",
    reschedule: "Reschedule",
    reschedule_cancellation: "Reschedule",
    nhs: "NHS note",
    reminder: "Follow-up",
    routine_clinical_question: "Clinical question",
    test_report_result_query: "Results query",
    urgent_clinical_concern: "Urgent clinical",
  };
  return labels[type] || type;
}

function priorityClass(priority: string) {
  if (priority === "urgent") {
    return "tone-red";
  }
  if (priority === "clinical") {
    return "tone-purple";
  }
  if (priority === "admin") {
    return "tone-neutral";
  }
  if (priority === "new") {
    return "tone-blue";
  }
  if (priority === "action") {
    return "tone-orange";
  }
  if (priority === "info") {
    return "tone-green";
  }
  return "tone-neutral";
}

function initials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0])
    .join("")
    .slice(0, 2);
}

function metadataValue(action: ClinicAction, key: string) {
  const metadata = action.metadata || {};
  return metadata[key];
}

function metadataString(action: ClinicAction, key: string, fallback = "") {
  const value = metadataValue(action, key);
  return typeof value === "string" && value ? value : fallback;
}

function metadataBoolean(action: ClinicAction, key: string) {
  return metadataValue(action, key) === true;
}

function metadataIsFalse(action: ClinicAction, key: string) {
  const value = metadataValue(action, key);
  return value === false || value === "false";
}

function metadataRecord(action: ClinicAction, key: string) {
  const value = metadataValue(action, key);
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function requestConstraintSummary(action: ClinicAction) {
  const directSummary = metadataString(action, "constraint_summary");
  if (directSummary) {
    return directSummary;
  }
  const constraints = metadataRecord(action, "request_constraints");
  const summary = constraints.constraint_summary;
  if (typeof summary === "string" && summary) {
    return summary;
  }
  const earliestAt = constraints.earliest_appointment_at;
  if (typeof earliestAt === "string" && earliestAt) {
    return `Earliest appointment: ${new Date(earliestAt).toLocaleString([], {
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      month: "short",
    })}`;
  }
  return "";
}

function actionNeedsDoctorReview(action: ClinicAction) {
  return (
    metadataBoolean(action, "requires_doctor_review") ||
    metadataString(action, "risk_level") === "high" ||
    metadataString(action, "urgency_level") === "urgent" ||
    action.priority === "urgent" ||
    action.priority === "clinical"
  );
}

function actionSortRank(action: ClinicAction) {
  if (metadataString(action, "urgency_level") === "urgent" || action.priority === "urgent") {
    return 0;
  }
  if (actionNeedsDoctorReview(action)) {
    return 1;
  }
  if (action.priority === "action") {
    return 2;
  }
  if (action.priority === "new") {
    return 3;
  }
  return 4;
}

function nextAttentionSummary(openActions: ClinicAction[]) {
  const urgent = openActions.filter((action) => actionSortRank(action) === 0).length;
  const clinical = openActions.filter((action) => actionNeedsDoctorReview(action)).length;
  if (urgent > 0) {
    return `${urgent} urgent item${urgent === 1 ? "" : "s"} should be reviewed first.`;
  }
  if (clinical > 0) {
    return `${clinical} clinical review item${clinical === 1 ? "" : "s"} need your attention.`;
  }
  if (openActions.length > 0) {
    return `${openActions.length} open action${openActions.length === 1 ? "" : "s"} ready for review.`;
  }
  return "No open actions waiting for review.";
}

function activeScheduleEvents(days: ScheduleDay[]) {
  const events: ScheduleEvent[] = [];
  for (const day of days) {
    for (const event of day.events) {
      if (event.status !== "open") {
        events.push(event);
      }
    }
  }
  return events;
}

function scheduleDayId(day: ScheduleDay) {
  return day.dayDate || day.dayKey;
}

function localIsoDate(value = new Date()) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function weekRangeLabel(days: ScheduleDay[]) {
  if (days.length === 0) {
    return "";
  }
  const first = days[0].dayLabel.replace(/^[A-Za-z]+ /, "");
  const last = days[days.length - 1].dayLabel.replace(/^[A-Za-z]+ /, "");
  return `${first} - ${last}`;
}

function scheduleEventsForToday(days: ScheduleDay[]) {
  const todayIso = localIsoDate();
  const todayByDate = days.find((day) => day.dayDate === todayIso);
  if (todayByDate) {
    return activeScheduleEvents([todayByDate]);
  }
  const todayLabel = new Date()
    .toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      weekday: "long",
    })
    .replace(",", "");
  const today = days.find((day) => day.dayLabel === todayLabel);
  return activeScheduleEvents(today ? [today] : days.slice(0, 1));
}

function roundsGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) {
    return "Good morning, Doctor";
  }
  if (hour < 18) {
    return "Good afternoon, Doctor";
  }
  return "Good evening, Doctor";
}

function roundsDateLabel() {
  const parts = new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    weekday: "long",
  }).formatToParts(new Date());
  const weekday = parts.find((part) => part.type === "weekday")?.value || "";
  const day = parts.find((part) => part.type === "day")?.value || "";
  const month = parts.find((part) => part.type === "month")?.value || "";
  return `${weekday} · ${day} ${month} · ready for rounds`;
}

function briefingCopy(openActions: ClinicAction[], scheduleEvents: ScheduleEvent[]) {
  const appointmentCopy =
    scheduleEvents.length === 0
      ? "Calendar context has not been read yet."
      : scheduleEvents.length === 1
        ? `One appointment is on the calendar at ${scheduleEvents[0].startTime}.`
        : `${scheduleEvents.length} appointments are on the calendar; next at ${scheduleEvents[0].startTime}.`;
  return `${appointmentCopy} ${nextAttentionSummary(openActions)}`;
}

function Rounds({
  actions,
  days,
  loading,
  onApprove,
  onBook,
  onSend,
  approvingId,
  bookingId,
  sendingId,
}: {
  actions: ClinicAction[];
  days: ScheduleDay[];
  loading: boolean;
  onApprove: (action: ClinicAction, finalMessage: string) => Promise<void>;
  onBook: (action: ClinicAction, finalMessage: string) => Promise<void>;
  onSend: (action: ClinicAction, finalMessage: string) => Promise<void>;
  approvingId: string | null;
  bookingId: string | null;
  sendingId: string | null;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [draftEdits, setDraftEdits] = useState<Record<string, string>>({});
  const openActions = useMemo(
    () =>
      [...actions]
        .filter((action) => action.status !== "completed")
        .sort((first, second) => actionSortRank(first) - actionSortRank(second)),
    [actions],
  );
  const pendingCount = openActions.length;
  const clinicalReviewCount = openActions.filter(actionNeedsDoctorReview).length;
  const scheduleEvents = scheduleEventsForToday(days);
  const schedulePreview = scheduleEvents.slice(0, 3);

  useEffect(() => {
    setDraftEdits((current) => {
      const next = { ...current };
      for (const action of actions) {
        if (action.draftMessage && next[action.actionId] === undefined) {
          next[action.actionId] = action.finalMessage || action.draftMessage;
        }
      }
      return next;
    });
  }, [actions]);

  return (
    <section className="screen-panel rounds-panel" aria-labelledby="rounds-title">
      <div className="section-heading rounds-heading">
        <h1 id="rounds-title">{roundsGreeting()}</h1>
        <p className="date-line">{roundsDateLabel()}</p>
      </div>

      <div className="briefing">
        <span className="briefing-label">Today · Briefing</span>
        <p>{briefingCopy(openActions, scheduleEvents)}</p>
        <div className="briefing-metrics" aria-label="Rounds summary">
          <span>
            <strong>{scheduleEvents.length}</strong>
            <small>Appointment{scheduleEvents.length === 1 ? "" : "s"}</small>
          </span>
          <span>
            <strong>{pendingCount}</strong>
            <small>Action{pendingCount === 1 ? "" : "s"}</small>
          </span>
          {clinicalReviewCount > 0 ? (
            <span>
              <strong>{clinicalReviewCount}</strong>
              <small>Review</small>
            </span>
          ) : null}
        </div>
      </div>

      <div className="rounds-block">
        <div className="rounds-block-title">Schedule</div>
        {schedulePreview.length > 0 ? (
          <div className="rounds-schedule-list">
            {schedulePreview.map((event) => (
              <article key={event.eventId} className="rounds-schedule-item">
                <time>{event.startTime}</time>
                <span>
                  <strong>{event.patientName}</strong>
                  <small>{event.appointmentType}</small>
                </span>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">Read Calendar to load today's appointment context.</div>
        )}
      </div>

      <div className="queue-heading">
        <h2>Needs your attention</h2>
        <span>{pendingCount}</span>
      </div>

      {loading ? <div className="empty-state">Loading patient requests...</div> : null}

      <div className="stack-list">
        {openActions.map((action) => {
          const expanded = expandedId === action.actionId;
          const draftValue = draftEdits[action.actionId] ?? action.finalMessage ?? action.draftMessage ?? "";
          const urgency = metadataString(action, "urgency_level", "routine");
          const risk = metadataString(action, "risk_level", "low");
          const triageReason = metadataString(action, "triage_reason");
          const suggestedNextAction = metadataString(action, "suggested_next_action");
          const emotionalTone = metadataString(action, "patient_emotional_tone", "neutral");
          const constraintSummary = requestConstraintSummary(action);
          const bookingLabel = metadataString(action, "booking_candidate_label");
          const bookingUnavailableReason = metadataString(action, "booking_candidate_unavailable_reason");
          const canBookCalendar =
            action.sourceProvider === "gmail" &&
            Boolean(metadataString(action, "booking_candidate_start_at")) &&
            !metadataIsFalse(action, "booking_candidate_available");
          const actionBusy =
            approvingId === action.actionId || sendingId === action.actionId || bookingId === action.actionId;
          return (
            <article key={action.actionId} className={`action-card priority-${action.priority}`}>
              <button
                type="button"
                className="action-card-button"
                onClick={() => setExpandedId(expanded ? null : action.actionId)}
                aria-expanded={expanded}
              >
                <span className="action-chip-row">
                  <span className={`type-marker ${priorityClass(action.priority)}`}>
                    {actionTypeLabel(action.actionType)}
                  </span>
                  <span className={`status-pill status-${action.status}`}>{urgency}</span>
                </span>
                <span className="action-card-copy">
                  <strong>{action.patientName || action.sourceSummary}</strong>
                  <small>{action.patientName ? action.sourceSummary : action.sourceMessage}</small>
                </span>
                <span className="action-card-footer">
                  <span>{action.timeLabel || statusLabel(action.status)}</span>
                  <span>{expanded ? "Close" : "Review"}</span>
                </span>
              </button>

              {expanded ? (
                <div className="expanded-content">
                  <div className="triage-strip" aria-label="Triage details">
                    <span className={`status-pill ${risk === "high" ? "tone-red" : risk === "medium" ? "tone-purple" : "tone-green"}`}>Risk: {risk}</span>
                    <span className="status-pill">{actionNeedsDoctorReview(action) ? "Doctor review" : "Admin review"}</span>
                    <span className="status-pill">Tone: {emotionalTone.replaceAll("_", " ")}</span>
                  </div>

                  {triageReason || suggestedNextAction ? (
                    <div className="detail-block">
                      <span>Triage</span>
                      {triageReason ? <p>{triageReason}</p> : null}
                      {suggestedNextAction ? <p>{suggestedNextAction}</p> : null}
                    </div>
                  ) : null}

                  {constraintSummary ? (
                    <div className="detail-block">
                      <span>Patient context</span>
                      <p>{constraintSummary}</p>
                    </div>
                  ) : null}

                  {bookingLabel ? (
                    <div className="detail-block">
                      <span>Proposed booking</span>
                      <p>
                        {bookingLabel}
                        {bookingUnavailableReason ? ` · ${bookingUnavailableReason}` : ""}
                      </p>
                    </div>
                  ) : null}

                  {action.sourceMessage ? (
                    <div className="detail-block">
                      <span>Source</span>
                      <p>{action.sourceMessage}</p>
                    </div>
                  ) : null}

                  {action.draftMessage ? (
                    <div className="detail-block draft-block">
                      <span>Draft reply</span>
                      <textarea
                        className="draft-editor"
                        value={draftValue}
                        onChange={(event) =>
                          setDraftEdits((current) => ({
                            ...current,
                            [action.actionId]: event.target.value,
                          }))
                        }
                        rows={10}
                      />
                    </div>
                  ) : null}

                  {action.draftMessage ? (
                    <div className="action-controls">
                      {canBookCalendar ? (
                        <button
                          type="button"
                          className="primary-button"
                          onClick={() => void onBook(action, draftValue)}
                          disabled={actionBusy}
                        >
                          {bookingId === action.actionId ? "Booking..." : "Approve, send & book"}
                        </button>
                      ) : null}
                      {action.sourceProvider === "gmail" ? (
                        <button
                          type="button"
                          className={canBookCalendar ? "secondary-button" : "primary-button"}
                          onClick={() => void onSend(action, draftValue)}
                          disabled={actionBusy}
                        >
                          {sendingId === action.actionId ? "Sending..." : "Approve & send Gmail"}
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className={action.sourceProvider === "gmail" ? "secondary-button" : "primary-button"}
                        onClick={() => void onApprove(action, draftValue)}
                        disabled={actionBusy}
                      >
                        {approvingId === action.actionId ? "Saving..." : "Approve and store"}
                      </button>
                    </div>
                  ) : (
                    <p className="audit-note">Calendar updates are not part of this MVP.</p>
                  )}
                </div>
              ) : null}
            </article>
          );
        })}
      </div>

      {!loading && openActions.length === 0 ? <div className="empty-state">No open actions need attention.</div> : null}
    </section>
  );
}

function Schedule({ days }: { days: ScheduleDay[] }) {
  const [weekStartIndex, setWeekStartIndex] = useState(0);
  const [selectedKey, setSelectedKey] = useState(days[0] ? scheduleDayId(days[0]) : "");
  const totalWeeks = Math.max(1, Math.ceil(days.length / SCHEDULE_DAYS_PER_PAGE));
  const maxWeekStartIndex = Math.max(0, (totalWeeks - 1) * SCHEDULE_DAYS_PER_PAGE);
  const safeWeekStartIndex = Math.min(weekStartIndex, maxWeekStartIndex);
  const visibleDays = days.slice(safeWeekStartIndex, safeWeekStartIndex + SCHEDULE_DAYS_PER_PAGE);
  const selectedDay =
    visibleDays.find((day) => scheduleDayId(day) === selectedKey) ||
    days.find((day) => scheduleDayId(day) === selectedKey) ||
    visibleDays[0] ||
    days[0];

  useEffect(() => {
    if (weekStartIndex > maxWeekStartIndex) {
      setWeekStartIndex(maxWeekStartIndex);
    }
  }, [maxWeekStartIndex, weekStartIndex]);

  useEffect(() => {
    if (visibleDays.length === 0) {
      return;
    }
    if (!visibleDays.some((day) => scheduleDayId(day) === selectedKey)) {
      setSelectedKey(scheduleDayId(visibleDays[0]));
    }
  }, [selectedKey, visibleDays]);

  return (
    <section className="screen-panel" aria-labelledby="schedule-title">
      <div className="section-title-row">
        <h1 id="schedule-title">This Week</h1>
        <span className="quiet-badge">Read only</span>
      </div>

      <div className="schedule-week-controls">
        <button
          type="button"
          className="week-nav-button"
          disabled={safeWeekStartIndex === 0}
          onClick={() => setWeekStartIndex(Math.max(0, safeWeekStartIndex - SCHEDULE_DAYS_PER_PAGE))}
        >
          Previous
        </button>
        <div>
          <span>Week {Math.floor(safeWeekStartIndex / SCHEDULE_DAYS_PER_PAGE) + 1}</span>
          <strong>{weekRangeLabel(visibleDays)}</strong>
        </div>
        <button
          type="button"
          className="week-nav-button"
          disabled={safeWeekStartIndex >= maxWeekStartIndex}
          onClick={() => setWeekStartIndex(Math.min(maxWeekStartIndex, safeWeekStartIndex + SCHEDULE_DAYS_PER_PAGE))}
        >
          Next
        </button>
      </div>

      <div className="day-tabs" role="tablist" aria-label="Schedule days">
        {visibleDays.map((day) => (
          <button
            type="button"
            key={scheduleDayId(day)}
            className={`day-tab ${selectedDay && scheduleDayId(selectedDay) === scheduleDayId(day) ? "is-selected" : ""}`}
            onClick={() => setSelectedKey(scheduleDayId(day))}
          >
            <span>{day.dayKey.split(" ")[0]}</span>
            <strong>{day.dayKey.split(" ")[1]}</strong>
            {day.dayType === "nhs" ? <em>NHS</em> : null}
          </button>
        ))}
      </div>

      {selectedDay ? (
        <>
          <div className="day-summary">
            <span>{selectedDay.dayLabel}</span>
            <strong>{selectedDay.dayType === "nhs" ? "NHS day" : "Private day"}</strong>
          </div>
          <div className="timeline">
            {selectedDay.events.map((event) => (
              <article key={event.eventId} className={`timeline-item event-${event.status}`}>
                <time>{event.startTime}</time>
                <div>
                  <strong>{event.patientName}</strong>
                  <span>
                    {event.appointmentType} · {event.startTime} - {event.endTime}
                  </span>
                </div>
              </article>
            ))}
            {selectedDay.events.length === 0 ? <div className="empty-state">No appointments on this day.</div> : null}
          </div>
        </>
      ) : (
        <div className="empty-state">No schedule loaded.</div>
      )}
    </section>
  );
}

function timelineDateLabel(value: string) {
  if (!value) {
    return "";
  }
  return new Date(value).toLocaleString([], {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
  });
}

function Patients({ patients }: { patients: Patient[] }) {
  const [query, setQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const filteredPatients = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return patients;
    }
    return patients.filter(
      (patient) =>
        patient.name.toLowerCase().includes(normalized) || patient.email.toLowerCase().includes(normalized),
    );
  }, [patients, query]);

  return (
    <section className="screen-panel" aria-labelledby="patients-title">
      <div className="section-heading compact">
        <h1 id="patients-title">Patients</h1>
        <p>{patients.length} total patients</p>
      </div>

      <label className="search-field">
        <span>Search</span>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name or email" />
      </label>

      <div className="stack-list">
        {filteredPatients.map((patient) => {
          const expanded = expandedId === patient.patientId;
          const timeline = patient.timeline || [];
          const openRequestCount = patient.openRequestCount || 0;
          const requestCount = patient.requestCount || 0;
          const patientSummary =
            openRequestCount > 0
              ? `${openRequestCount} open request${openRequestCount === 1 ? "" : "s"}`
              : requestCount > 0
                ? `${requestCount} request${requestCount === 1 ? "" : "s"} in timeline`
                : patient.visits === 0
                  ? "No visits yet"
                  : `${patient.visits} visits · Last: ${patient.lastVisit}`;
          return (
            <article key={patient.patientId} className="patient-card">
              <button
                type="button"
                className="row-button"
                onClick={() => setExpandedId(expanded ? null : patient.patientId)}
                aria-expanded={expanded}
              >
                <span className={`avatar avatar-${patient.status}`}>{initials(patient.name)}</span>
                <span className="row-copy">
                  <strong>{patient.name}</strong>
                  <small>{patientSummary}</small>
                </span>
                <span className={`status-pill status-${patient.status}`}>{statusLabel(patient.status)}</span>
              </button>

              {expanded ? (
                <div className="expanded-content patient-detail">
                  <dl>
                    <div>
                      <dt>Phone</dt>
                      <dd>{patient.phone}</dd>
                    </div>
                    <div>
                      <dt>Email</dt>
                      <dd>{patient.email}</dd>
                    </div>
                    <div>
                      <dt>Next</dt>
                      <dd>{patient.nextAppt}</dd>
                    </div>
                  </dl>
                  <p>{patient.notes}</p>
                  {timeline.length > 0 ? (
                    <div className="patient-timeline">
                      <span>Request timeline</span>
                      {timeline.map((entry) => (
                        <article key={entry.timelineId}>
                          <strong>{entry.title}</strong>
                          <small>
                            {actionTypeLabel(entry.requestType)} · {statusLabel(entry.status)}
                            {entry.createdAt ? ` · ${timelineDateLabel(entry.createdAt)}` : ""}
                          </small>
                          <p>{entry.description}</p>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="audit-note">No patient requests have been linked yet.</p>
                  )}
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function integrationLabel(provider: string) {
  if (provider === "google_calendar") {
    return "Google Calendar";
  }
  if (provider === "gmail") {
    return "Gmail";
  }
  return provider;
}

function lastReadLabel(value: string | null) {
  if (!value) {
    return "Not read yet";
  }
  return `Last read ${new Date(value).toLocaleString([], {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
  })}`;
}

function connectedIntegrationState(integrations: Integration[]) {
  const connectedAt = new Date().toISOString();
  return integrations.map((integration) => ({
    ...integration,
    status: "connected",
    accountEmail: integration.accountEmail || "doctor@example.com",
    connectedAt: integration.connectedAt || connectedAt,
    lastError: null,
  }));
}

function workspaceHasContent(actions: ClinicAction[], patients: Patient[], days: ScheduleDay[], integrations: Integration[]) {
  const hasOpenOrHistoricWork = actions.length > 0 || patients.length > 0;
  const hasScheduleEvents = days.some((day) => day.events.length > 0);
  const hasCompletedRead = integrations.some((integration) => Boolean(integration.lastSyncAt));
  return hasOpenOrHistoricWork || hasScheduleEvents || hasCompletedRead;
}

function OnboardingScreen({
  googleConnected,
  googleAuthAvailable,
  mockAuthAvailable,
  onConnectGoogle,
  onScanGmail,
  onSyncCalendar,
  onSkip,
  scanningGmail,
  syncingCalendar,
}: {
  googleConnected: boolean;
  googleAuthAvailable: boolean;
  mockAuthAvailable: boolean;
  onConnectGoogle: () => void;
  onScanGmail: () => Promise<void>;
  onSyncCalendar: () => Promise<void>;
  onSkip: () => void;
  scanningGmail: boolean;
  syncingCalendar: boolean;
}) {
  return (
    <section className="onboarding-panel" aria-labelledby="onboarding-title">
      <div className="onboarding-hero">
        <span className="eyebrow">First run</span>
        <h1 id="onboarding-title">Set up today&apos;s clinic view</h1>
        <p>Connect Google, then read Calendar and Gmail to prepare the first Rounds briefing.</p>
      </div>

      <div className="onboarding-steps">
        <article>
          <span className={googleConnected ? "step-dot is-done" : "step-dot"} />
          <div>
            <strong>Google Workspace</strong>
            <small>{googleConnected ? "Connected" : "Not connected"}</small>
          </div>
          <button
            type="button"
            className="secondary-button"
            disabled={!googleAuthAvailable && !mockAuthAvailable}
            onClick={onConnectGoogle}
          >
            {googleConnected ? "Reconnect" : "Connect"}
          </button>
        </article>

        <article>
          <span className="step-dot" />
          <div>
            <strong>Calendar</strong>
            <small>Appointments source of truth</small>
          </div>
          <button
            type="button"
            className="secondary-button"
            disabled={!googleConnected || syncingCalendar}
            onClick={() => void onSyncCalendar()}
          >
            {syncingCalendar ? "Reading..." : "Read"}
          </button>
        </article>

        <article>
          <span className="step-dot" />
          <div>
            <strong>Gmail</strong>
            <small>Patient requests and drafts</small>
          </div>
          <button
            type="button"
            className="secondary-button"
            disabled={!googleConnected || scanningGmail}
            onClick={() => void onScanGmail()}
          >
            {scanningGmail ? "Scanning..." : "Scan"}
          </button>
        </article>
      </div>

      <div className="onboarding-footer">
        <span>Nothing is sent or changed without approval.</span>
        <button type="button" className="connect-link" onClick={onSkip}>
          Open empty workspace
        </button>
      </div>
    </section>
  );
}

function SettingsDrawer({
  settings,
  integrations,
  doctorEmail,
  doctorName,
  googleAuthAvailable,
  mockAuthAvailable,
  onConnectGoogle,
  onScanGmail,
  onSyncCalendar,
  onClose,
  scanningGmail,
  syncingCalendar,
}: {
  settings: Settings;
  integrations: Integration[];
  doctorEmail: string;
  doctorName: string;
  googleAuthAvailable: boolean;
  mockAuthAvailable: boolean;
  onConnectGoogle: () => void;
  onScanGmail: () => Promise<void>;
  onSyncCalendar: () => Promise<void>;
  onClose: () => void;
  scanningGmail: boolean;
  syncingCalendar: boolean;
}) {
  const googleConnected = integrations.some((integration) => integration.status === "connected");

  return (
    <>
      <button type="button" className="drawer-backdrop" aria-label="Close settings" onClick={onClose} />
      <aside className="settings-drawer" aria-label="Clinic settings">
        <div className="doctor-header">
          <div className="doctor-avatar">S</div>
          <div>
            <strong>{doctorName}</strong>
            <span>{doctorEmail}</span>
          </div>
        </div>

        <div className="settings-group">
          <h2>Google Workspace</h2>
          {integrations.map((integration) => (
            <div key={integration.integrationId} className="settings-row split">
              <strong>{integrationLabel(integration.provider)}</strong>
              <em>{integration.status === "ready_to_connect" ? "Ready" : statusLabel(integration.status)}</em>
              <small>
                {integration.writeMode.replaceAll("_", " ")} · {lastReadLabel(integration.lastSyncAt)}
              </small>
            </div>
          ))}
          <div className="integration-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={!googleConnected || syncingCalendar}
              onClick={() => void onSyncCalendar()}
            >
              {syncingCalendar ? "Reading..." : "Read Calendar"}
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={!googleConnected || scanningGmail}
              onClick={() => void onScanGmail()}
            >
              {scanningGmail ? "Scanning..." : "Scan Gmail"}
            </button>
          </div>
          <button
            type="button"
            className="connect-link"
            disabled={!googleAuthAvailable && !mockAuthAvailable}
            onClick={onConnectGoogle}
          >
            {googleAuthAvailable ? "Reconnect Google" : "Connect Google"}
          </button>
        </div>

        <div className="settings-group">
          <h2>Weekly Availability</h2>
          {settings.availabilityRules.map((rule) => (
            <div key={rule.day} className="settings-row">
              <span className={`dot ${rule.type.includes("NHS") ? "dot-blue" : "dot-green"}`} />
              <strong>{rule.day}</strong>
              <small>{rule.hours}</small>
              <em>{rule.type}</em>
            </div>
          ))}
        </div>

        <div className="settings-group">
          <h2>Appointment Types</h2>
          {settings.appointmentTypes.map((type) => (
            <div key={type.name} className="settings-row">
              <span className="dot" style={{ backgroundColor: type.color }} />
              <strong>{type.name}</strong>
              <em>{type.duration}</em>
            </div>
          ))}
        </div>

        <div className="settings-group">
          <h2>Preferences</h2>
          {settings.preferences.map((preference) => (
            <div key={preference.label} className="settings-row split">
              <strong>{preference.label}</strong>
              <em>{preference.value}</em>
            </div>
          ))}
        </div>

        <button type="button" className="signout-button" onClick={() => void signOut({ callbackUrl: "/" })}>
          Sign out
        </button>
      </aside>
    </>
  );
}

async function loadClinicSnapshot() {
  const [actionData, patientData, scheduleData, settingsData, integrationData] = await Promise.all([
    loadJson<ClinicAgentListActionsOutput>("/api/clinic/actions?includeCompleted=true"),
    loadJson<ClinicAgentListPatientsOutput>("/api/clinic/patients"),
    loadJson<ClinicAgentListScheduleOutput>("/api/clinic/schedule"),
    loadJson<ClinicAgentListSettingsOutput>("/api/clinic/settings"),
    loadJson<ClinicAgentListIntegrationsOutput>("/api/clinic/integrations"),
  ]);
  return { actionData, patientData, scheduleData, settingsData, integrationData };
}

export function ClinicApp({
  doctorEmail,
  doctorName,
  googleAuthAvailable,
  mockAuthAvailable,
}: {
  doctorEmail: string;
  doctorName: string;
  googleAuthAvailable: boolean;
  mockAuthAvailable: boolean;
}) {
  const [tab, setTab] = useState<Tab>("actions");
  const [menuOpen, setMenuOpen] = useState(false);
  const [actions, setActions] = useState<ClinicAction[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [days, setDays] = useState<ScheduleDay[]>([]);
  const [settings, setSettings] = useState<Settings>(emptySettings);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [bookingId, setBookingId] = useState<string | null>(null);
  const [sendingId, setSendingId] = useState<string | null>(null);
  const [syncingCalendar, setSyncingCalendar] = useState(false);
  const [scanningGmail, setScanningGmail] = useState(false);
  const [onboardingDismissed, setOnboardingDismissed] = useState(false);

  useEffect(() => {
    async function loadClinicData() {
      setLoading(true);
      setError("");
      try {
        const { actionData, patientData, scheduleData, settingsData, integrationData } = await loadClinicSnapshot();
        setActions(actionData.actions);
        setPatients(patientData.patients);
        setDays(scheduleData.days);
        setSettings(settingsData);
        setIntegrations(integrationData.integrations);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load clinic data");
      } finally {
        setLoading(false);
      }
    }

    void loadClinicData();
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const googleOAuthStatus = params.get("googleOAuth");
    if (!googleOAuthStatus) {
      return;
    }

    if (googleOAuthStatus === "connected") {
      setNotice("Google authorization completed. Checking the saved connection...");
      void (async () => {
        try {
          const integrationData = await loadJson<ClinicAgentListIntegrationsOutput>("/api/clinic/integrations");
          const connected = integrationData.integrations.some((integration) => integration.status === "connected");
          setIntegrations(integrationData.integrations);
          if (connected) {
            setNotice("Google connected. Gmail and calendar updates only happen after you approve a specific action.");
          } else {
            setError(
              "Google authorization completed, but the backend did not save the connection. Try Reconnect Google again.",
            );
          }
        } catch (refreshError) {
          setError(refreshError instanceof Error ? refreshError.message : "Unable to check Google connection");
        }
      })();
    } else {
      setError(params.get("reason") || "Google connection did not complete.");
    }
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.hash}`);
  }, []);

  async function approveAction(action: ClinicAction, finalMessage: string) {
    setApprovingId(action.actionId);
    setError("");
    try {
      const response = await fetch(`/api/clinic/actions/${action.actionId}/approve`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          approvedBy: "Dr. Shalini",
          finalMessage: finalMessage.trim() || action.draftMessage || action.sourceSummary,
        }),
      });
      const body = (await response.json()) as ClinicAgentApproveActionOutput & { error?: string };
      if (!response.ok) {
        throw new Error(body.error || "Unable to approve action");
      }
      setActions((current) => current.map((item) => (item.actionId === body.action.actionId ? body.action : item)));
    } catch (approveError) {
      setError(approveError instanceof Error ? approveError.message : "Unable to approve action");
    } finally {
      setApprovingId(null);
    }
  }

  async function approveAndSendGmail(action: ClinicAction, finalMessage: string) {
    const messageToSend = finalMessage.trim() || action.draftMessage || action.sourceSummary;
    const confirmed = window.confirm("Send this edited reply to the patient now through Gmail?");
    if (!confirmed) {
      return;
    }

    setSendingId(action.actionId);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`/api/clinic/actions/${action.actionId}/send`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          approvedBy: "Dr. Shalini",
          finalMessage: messageToSend,
        }),
      });
      const body = (await response.json()) as ClinicAgentApproveAndSendGmailOutput & { error?: string };
      if (!response.ok) {
        throw new Error(body.error || "Unable to send Gmail reply");
      }
      setActions((current) => current.map((item) => (item.actionId === body.action.actionId ? body.action : item)));
      setNotice("Gmail reply sent after your approval.");
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : "Unable to send Gmail reply");
    } finally {
      setSendingId(null);
    }
  }

  async function approveSendAndBookCalendar(action: ClinicAction, finalMessage: string) {
    const messageToSend = finalMessage.trim() || action.draftMessage || action.sourceSummary;
    const bookingLabel = metadataString(action, "booking_candidate_label", "the selected appointment slot");
    const confirmed = window.confirm(
      `Book ${bookingLabel} in Google Calendar and send this edited Gmail confirmation now?`,
    );
    if (!confirmed) {
      return;
    }

    setBookingId(action.actionId);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`/api/clinic/actions/${action.actionId}/book`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          approvedBy: "Dr. Shalini",
          finalMessage: messageToSend,
        }),
      });
      const body = (await response.json()) as ClinicAgentApproveSendAndBookCalendarOutput & { error?: string };
      if (!response.ok) {
        throw new Error(body.error || "Unable to book appointment");
      }
      setActions((current) => current.map((item) => (item.actionId === body.action.actionId ? body.action : item)));
      const [scheduleData, patientData] = await Promise.all([
        loadJson<ClinicAgentListScheduleOutput>("/api/clinic/schedule"),
        loadJson<ClinicAgentListPatientsOutput>("/api/clinic/patients"),
      ]);
      setDays(scheduleData.days);
      setPatients(patientData.patients);
      setNotice("Appointment booked in Google Calendar and Gmail confirmation sent after your approval.");
    } catch (bookError) {
      setError(bookError instanceof Error ? bookError.message : "Unable to book appointment");
    } finally {
      setBookingId(null);
    }
  }

  async function refreshIntegrations() {
    const integrationData = await loadJson<ClinicAgentListIntegrationsOutput>("/api/clinic/integrations");
    setIntegrations(integrationData.integrations);
  }

  async function syncGoogleCalendar() {
    setSyncingCalendar(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/clinic/integrations/google-calendar/sync", { method: "POST" });
      const body = (await response.json()) as ClinicAgentSyncGoogleCalendarOutput & { error?: string };
      if (!response.ok) {
        throw new Error(body.error || "Unable to read Google Calendar");
      }
      setDays(body.days);
      await refreshIntegrations();
      setTab("schedule");
      setNotice(`${body.eventsRead} calendar events read. Google Calendar was not changed.`);
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : "Unable to read Google Calendar");
    } finally {
      setSyncingCalendar(false);
    }
  }

  async function scanGmail() {
    setScanningGmail(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/clinic/integrations/gmail/scan", { method: "POST" });
      const body = (await response.json()) as ClinicAgentScanGmailInboxOutput & { error?: string };
      if (!response.ok) {
        throw new Error(body.error || "Unable to scan Gmail");
      }
      const [actionData, patientData] = await Promise.all([
        loadJson<ClinicAgentListActionsOutput>("/api/clinic/actions?includeCompleted=true"),
        loadJson<ClinicAgentListPatientsOutput>("/api/clinic/patients"),
      ]);
      setActions(actionData.actions);
      setPatients(patientData.patients);
      await refreshIntegrations();
      setTab("actions");
      setNotice(`${body.messagesScanned} Gmail messages scanned; ${body.proposedActions} in-app drafts prepared. Nothing was sent.`);
    } catch (scanError) {
      setError(scanError instanceof Error ? scanError.message : "Unable to scan Gmail");
    } finally {
      setScanningGmail(false);
    }
  }

  function connectGoogle() {
    if (googleAuthAvailable) {
      void signIn(googleProviderId, { callbackUrl: "/?googleOAuth=connected" });
      return;
    }
    if (mockAuthAvailable) {
      setIntegrations((current) => connectedIntegrationState(current));
      setNotice("Google connected. Gmail and calendar updates only happen after you approve a specific action.");
      return;
    }
    setError("Google OAuth is not configured yet.");
  }

  const googleConnected = integrations.some((integration) => integration.status === "connected");
  const showOnboarding =
    !loading && !onboardingDismissed && !workspaceHasContent(actions, patients, days, integrations);

  const tabs: { key: Tab; label: string }[] = [
    { key: "actions", label: "Rounds" },
    { key: "schedule", label: "Schedule" },
    { key: "patients", label: "Patients" },
  ];

  return (
    <main className="clinic-shell">
      {menuOpen ? (
        <SettingsDrawer
          settings={settings}
          integrations={integrations}
          doctorEmail={doctorEmail}
          doctorName={doctorName}
          googleAuthAvailable={googleAuthAvailable}
          mockAuthAvailable={mockAuthAvailable}
          onConnectGoogle={connectGoogle}
          onScanGmail={scanGmail}
          onSyncCalendar={syncGoogleCalendar}
          onClose={() => setMenuOpen(false)}
          scanningGmail={scanningGmail}
          syncingCalendar={syncingCalendar}
        />
      ) : null}

      <header className="app-header">
        <button type="button" className="brand-button" onClick={() => setMenuOpen(true)} aria-label="Open settings">
          S
        </button>
        <div>
          <strong>Dr. Shalini&apos;s Clinic</strong>
          <span>{doctorEmail}</span>
        </div>
        <span className="ai-badge">AI-powered</span>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}
      {notice ? <div className="notice-banner">{notice}</div> : null}

      <div className="app-content">
        {showOnboarding ? (
          <OnboardingScreen
            googleConnected={googleConnected}
            googleAuthAvailable={googleAuthAvailable}
            mockAuthAvailable={mockAuthAvailable}
            onConnectGoogle={connectGoogle}
            onScanGmail={scanGmail}
            onSyncCalendar={syncGoogleCalendar}
            onSkip={() => setOnboardingDismissed(true)}
            scanningGmail={scanningGmail}
            syncingCalendar={syncingCalendar}
          />
        ) : null}
        {!showOnboarding && tab === "actions" ? (
          <Rounds
            actions={actions}
            days={days}
            loading={loading}
            onApprove={approveAction}
            onBook={approveSendAndBookCalendar}
            onSend={approveAndSendGmail}
            approvingId={approvingId}
            bookingId={bookingId}
            sendingId={sendingId}
          />
        ) : null}
        {!showOnboarding && tab === "schedule" ? <Schedule days={days} /> : null}
        {!showOnboarding && tab === "patients" ? <Patients patients={patients} /> : null}
      </div>

      <nav className="bottom-nav" aria-label="Primary">
        {tabs.map((item) => (
          <button
            key={item.key}
            type="button"
            className={tab === item.key ? "is-active" : ""}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </nav>
    </main>
  );
}
