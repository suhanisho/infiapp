"use client";

import { useEffect, useMemo, useState } from "react";
import { signIn, signOut } from "next-auth/react";
import type {
  ClinicAgentApproveActionOutput,
  ClinicAgentListActionsOutput,
  ClinicAgentListIntegrationsOutput,
  ClinicAgentListPatientsOutput,
  ClinicAgentListScheduleOutput,
  ClinicAgentListSettingsOutput,
} from "@/src/lib/generated/mockAgents";
import { googleProviderId } from "@/src/lib/auth/providers";

type ClinicAction = ClinicAgentListActionsOutput["actions"][number];
type Patient = ClinicAgentListPatientsOutput["patients"][number];
type ScheduleDay = ClinicAgentListScheduleOutput["days"][number];
type Settings = ClinicAgentListSettingsOutput;
type Integration = ClinicAgentListIntegrationsOutput["integrations"][number];
type Tab = "actions" | "schedule" | "patients";

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
    enquiry: "New enquiry",
    reschedule: "Reschedule",
    nhs: "NHS note",
    reminder: "Follow-up",
  };
  return labels[type] || type;
}

function priorityClass(priority: string) {
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

function ActionQueue({
  actions,
  loading,
  onApprove,
  approvingId,
}: {
  actions: ClinicAction[];
  loading: boolean;
  onApprove: (action: ClinicAction) => Promise<void>;
  approvingId: string | null;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const pendingCount = actions.filter((action) => action.status !== "completed").length;

  return (
    <section className="screen-panel" aria-labelledby="actions-title">
      <div className="section-heading">
        <p className="date-line">Saturday 2 May, 1:42 PM</p>
        <h1 id="actions-title">
          {loading && actions.length === 0
            ? "Loading actions"
            : pendingCount > 0
              ? `${pendingCount} items need review`
              : "All actions completed"}
        </h1>
      </div>

      <div className="briefing">
        <span className="briefing-label">Today</span>
        <p>
          Four private appointments are on the schedule. Next patient: Sarah Mitchell at 1:30 PM. The clinic is free
          from 4:00 PM.
        </p>
      </div>

      {loading ? <div className="empty-state">Loading clinic actions...</div> : null}

      <div className="stack-list">
        {actions.map((action) => {
          const expanded = expandedId === action.actionId;
          const completed = action.status === "completed";
          return (
            <article key={action.actionId} className={`action-card ${completed ? "is-completed" : ""}`}>
              <button
                type="button"
                className="row-button"
                onClick={() => setExpandedId(expanded ? null : action.actionId)}
                aria-expanded={expanded}
              >
                <span className={`type-marker ${priorityClass(action.priority)}`}>{actionTypeLabel(action.actionType)}</span>
                <span className="row-copy">
                  <strong>{action.patientName || action.sourceSummary}</strong>
                  <small>{action.patientName ? action.sourceSummary : action.sourceMessage}</small>
                </span>
                <span className={`status-pill status-${action.status}`}>{statusLabel(action.status)}</span>
              </button>

              {expanded ? (
                <div className="expanded-content">
                  {action.sourceMessage ? (
                    <div className="detail-block">
                      <span>Source</span>
                      <p>{action.sourceMessage}</p>
                    </div>
                  ) : null}

                  {action.draftMessage ? (
                    <div className="detail-block draft-block">
                      <span>Draft reply</span>
                      <p>{action.finalMessage || action.draftMessage}</p>
                    </div>
                  ) : null}

                  {completed ? (
                    <p className="audit-note">{action.completionNote || "Completed action is stored for audit."}</p>
                  ) : action.draftMessage ? (
                    <div className="action-controls">
                      <button
                        type="button"
                        className="primary-button"
                        onClick={() => void onApprove(action)}
                        disabled={approvingId === action.actionId}
                      >
                        {approvingId === action.actionId ? "Saving..." : "Approve and store"}
                      </button>
                      <button type="button" className="secondary-button">
                        Edit draft
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
    </section>
  );
}

function Schedule({ days }: { days: ScheduleDay[] }) {
  const [selectedKey, setSelectedKey] = useState(days[0]?.dayKey || "");
  const selectedDay = days.find((day) => day.dayKey === selectedKey) || days[0];

  useEffect(() => {
    if (!selectedKey && days[0]) {
      setSelectedKey(days[0].dayKey);
    }
  }, [days, selectedKey]);

  return (
    <section className="screen-panel" aria-labelledby="schedule-title">
      <div className="section-title-row">
        <h1 id="schedule-title">This Week</h1>
        <span className="quiet-badge">Read only</span>
      </div>

      <div className="day-tabs" role="tablist" aria-label="Schedule days">
        {days.map((day) => (
          <button
            type="button"
            key={day.dayKey}
            className={`day-tab ${selectedDay?.dayKey === day.dayKey ? "is-selected" : ""}`}
            onClick={() => setSelectedKey(day.dayKey)}
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
          </div>
        </>
      ) : (
        <div className="empty-state">No schedule loaded.</div>
      )}
    </section>
  );
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
                  <small>
                    {patient.visits === 0 ? "No visits yet" : `${patient.visits} visits · Last: ${patient.lastVisit}`}
                  </small>
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

function SettingsDrawer({
  settings,
  integrations,
  doctorEmail,
  doctorName,
  googleAuthAvailable,
  mockAuthAvailable,
  onConnectGoogle,
  onClose,
}: {
  settings: Settings;
  integrations: Integration[];
  doctorEmail: string;
  doctorName: string;
  googleAuthAvailable: boolean;
  mockAuthAvailable: boolean;
  onConnectGoogle: () => void;
  onClose: () => void;
}) {
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
              <small>{integration.writeMode.replaceAll("_", " ")}</small>
            </div>
          ))}
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

  useEffect(() => {
    async function loadClinicData() {
      const initialParams = new URLSearchParams(window.location.search);
      const googleOAuthConnected = initialParams.get("googleOAuth") === "connected";
      setLoading(true);
      setError("");
      try {
        const [actionData, patientData, scheduleData, settingsData, integrationData] = await Promise.all([
          loadJson<ClinicAgentListActionsOutput>("/api/clinic/actions?includeCompleted=true"),
          loadJson<ClinicAgentListPatientsOutput>("/api/clinic/patients"),
          loadJson<ClinicAgentListScheduleOutput>("/api/clinic/schedule"),
          loadJson<ClinicAgentListSettingsOutput>("/api/clinic/settings"),
          loadJson<ClinicAgentListIntegrationsOutput>("/api/clinic/integrations"),
        ]);
        setActions(actionData.actions);
        setPatients(patientData.patients);
        setDays(scheduleData.days);
        setSettings(settingsData);
        setIntegrations(
          googleOAuthConnected ? connectedIntegrationState(integrationData.integrations) : integrationData.integrations,
        );
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
      setNotice("Google connected. Calendar and Gmail stay read-only until you approve a specific action.");
      setIntegrations((current) => connectedIntegrationState(current));
    } else {
      setError(params.get("reason") || "Google connection did not complete.");
    }
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.hash}`);
  }, []);

  async function approveAction(action: ClinicAction) {
    setApprovingId(action.actionId);
    setError("");
    try {
      const response = await fetch(`/api/clinic/actions/${action.actionId}/approve`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          approvedBy: "Dr. Shalini",
          finalMessage: action.draftMessage || action.sourceSummary,
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

  function connectGoogle() {
    if (googleAuthAvailable) {
      void signIn(googleProviderId, { callbackUrl: "/?googleOAuth=connected" });
      return;
    }
    if (mockAuthAvailable) {
      setIntegrations((current) => connectedIntegrationState(current));
      setNotice("Google connected. Calendar and Gmail stay read-only until you approve a specific action.");
      return;
    }
    setError("Google OAuth is not configured yet.");
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: "actions", label: "Actions" },
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
          onClose={() => setMenuOpen(false)}
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
        <span className="ai-badge">AI-assisted</span>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}
      {notice ? <div className="notice-banner">{notice}</div> : null}

      <div className="app-content">
        {tab === "actions" ? (
          <ActionQueue actions={actions} loading={loading} onApprove={approveAction} approvingId={approvingId} />
        ) : null}
        {tab === "schedule" ? <Schedule days={days} /> : null}
        {tab === "patients" ? <Patients patients={patients} /> : null}
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
