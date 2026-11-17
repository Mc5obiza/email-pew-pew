import { useState } from "react";

const API_BASE =
  import.meta.env.VITE_API_BASE ||
  `${window.location.protocol}//${window.location.hostname}:8000`;

const emailBody = (draft) =>
  [draft.greeting, "", draft.body, "", draft.signature].filter(Boolean).join("\n").trim();

export default function BulkEmailPanel({
  resumeFile,
  senderName,
  senderEmail,
  gmailStatus
}) {
  const [spreadsheet, setSpreadsheet] = useState(null);
  const [filterText, setFilterText] = useState("");
  const [mode, setMode] = useState("review");
  const [drafts, setDrafts] = useState([]);
  const [skipped, setSkipped] = useState([]);
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");

  const setDraftStatus = (index, nextStatus, error = "") => {
    setDrafts((current) =>
      current.map((draft, draftIndex) =>
        draftIndex === index ? { ...draft, sendStatus: nextStatus, sendError: error } : draft
      )
    );
  };

  const sendDraft = async (draft, index) => {
    setDraftStatus(index, "sending");
    const body = draft.editedBody ?? emailBody(draft);
    try {
      const response = await fetch(`${API_BASE}/auth/gmail/send`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recipient: draft.recipient,
          subject: draft.editedSubject ?? draft.subject,
          body
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Gmail could not send this email.");
      }
      setDraftStatus(index, "sent");
      return true;
    } catch (error) {
      const explanation =
        error instanceof TypeError
          ? "Could not confirm Gmail's response. Check Sent mail before retrying to avoid duplicates."
          : error.message || "Gmail could not send this email.";
      setDraftStatus(index, "error", explanation);
      return false;
    }
  };

  const handleGenerate = async () => {
    setMessage("");
    if (!resumeFile) {
      setStatus("error");
      setMessage("Upload your resume in Step 1 before generating a batch.");
      return;
    }
    if (!spreadsheet) {
      setStatus("error");
      setMessage("Choose the Excel workbook containing the internship rows.");
      return;
    }
    if (mode === "auto" && gmailStatus !== "connected") {
      setStatus("error");
      setMessage("Connect Gmail before choosing automatic sending.");
      return;
    }
    if (
      mode === "auto" &&
      !window.confirm(
        "Automatic mode will send each generated email to the matching spreadsheet contact without individual review. Continue?"
      )
    ) {
      return;
    }

    setStatus("loading");
    setDrafts([]);
    setSkipped([]);
    try {
      const form = new FormData();
      form.append("resume_file", resumeFile);
      form.append("spreadsheet_file", spreadsheet);
      form.append("filter_text", filterText.trim());
      if (senderName.trim()) form.append("sender_name", senderName.trim());
      if (senderEmail.trim()) form.append("sender_email", senderEmail.trim());

      const response = await fetch(`${API_BASE}/generate-bulk-emails/from-files`, {
        method: "POST",
        body: form
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Could not generate the email batch.");
      }
      setDrafts(data.drafts.map((draft) => ({ ...draft, sendStatus: "pending" })));
      setSkipped(data.skipped || []);
      setStatus("success");

      if (mode === "auto") {
        let sent = 0;
        for (let index = 0; index < data.drafts.length; index += 1) {
          const delivered = await sendDraft(data.drafts[index], index);
          if (!delivered) {
            setMessage(
              `Stopped after ${sent} email(s) were sent. Review the failed item and check Gmail Sent mail before retrying.`
            );
            setStatus("error");
            return;
          }
          sent += 1;
        }
        setMessage(`Automatically sent ${sent} email(s).`);
      } else {
        setMessage(
          `Generated ${data.drafts.length} draft(s) for review.${data.skipped.length ? ` Skipped ${data.skipped.length} incomplete row(s).` : ""}`
        );
      }
    } catch (error) {
      setStatus("error");
      setMessage(error.message || "Could not generate the email batch.");
    }
  };

  const handleApprove = async (draft, index) => {
    if (gmailStatus !== "connected") {
      setMessage("Connect Gmail before approving and sending drafts.");
      setStatus("error");
      return;
    }
    const delivered = await sendDraft(draft, index);
    setMessage(
      delivered
        ? `Sent the email to ${draft.recipient}.`
        : `Could not confirm delivery to ${draft.recipient}. Check Gmail Sent mail before retrying.`
    );
    setStatus(delivered ? "success" : "error");
  };

  return (
    <section className="panel bulk-panel">
      <div className="panel-header">
        <h2>Generate emails from a spreadsheet</h2>
        <span className="badge">Bulk</span>
      </div>
      <p className="hint">
        Upload the internship workbook. The app scans every sheet for internship subject,
        company, and contact-email columns, then creates one personalized email per matching
        row. The same resume from Step 1 is used for every email.
      </p>

      <div className="field">
        <label htmlFor="internship-workbook">Internship workbook (.xlsx)</label>
        <input
          id="internship-workbook"
          type="file"
          accept=".xlsx"
          onChange={(event) => setSpreadsheet(event.target.files?.[0] || null)}
        />
      </div>

      <div className="field">
        <label htmlFor="internship-filter">Filter (optional)</label>
        <input
          id="internship-filter"
          type="text"
          placeholder="For example: BIO, Maroc, or AI"
          value={filterText}
          onChange={(event) => setFilterText(event.target.value)}
        />
        <span className="hint">
          Matches text in any column of each row. Leave empty to process all eligible rows.
        </span>
      </div>

      <fieldset className="bulk-modes">
        <legend>Sending mode</legend>
        <label>
          <input
            type="radio"
            name="bulk-mode"
            value="review"
            checked={mode === "review"}
            onChange={() => setMode("review")}
          />
          Generate drafts; I review and approve each email
        </label>
        <label>
          <input
            type="radio"
            name="bulk-mode"
            value="auto"
            checked={mode === "auto"}
            onChange={() => setMode("auto")}
          />
          Automatically send all generated emails
        </label>
      </fieldset>

      <button className="primary" type="button" onClick={handleGenerate} disabled={status === "loading"}>
        {status === "loading"
          ? "Reading workbook and generating..."
          : mode === "auto"
            ? "Generate and auto-send"
            : "Generate drafts for review"}
      </button>
      {status === "loading" ? (
        <p className="hint" aria-live="polite">
          Each matching row is analyzed separately. A large workbook may take several minutes.
        </p>
      ) : null}
      {message ? <p className={`message ${status}`} aria-live="polite">{message}</p> : null}

      {skipped.length ? (
        <details className="skipped-rows">
          <summary>Skipped rows ({skipped.length})</summary>
          <ul>
            {skipped.map((row) => (
              <li key={`${row.worksheet}-${row.row_number}`}>
                {row.worksheet}, row {row.row_number}: {row.reason}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {drafts.length ? (
        <div className="bulk-drafts">
          <h3>Email drafts ({drafts.length})</h3>
          {drafts.map((draft, index) => (
            <details className="bulk-draft" key={`${draft.worksheet}-${draft.row_number}`}>
              <summary>
                <span>{draft.company} — {draft.internship_subject}</span>
                <span className={`draft-status ${draft.sendStatus}`}>
                  {draft.sendStatus === "sent" ? "Sent" : draft.sendStatus}
                </span>
              </summary>
              <div className="bulk-draft-content">
                <p><strong>To:</strong> {draft.recipient}</p>
                <p><strong>Source:</strong> {draft.worksheet}, row {draft.row_number}</p>
                <div className="field">
                  <label htmlFor={`bulk-subject-${index}`}>Subject</label>
                  <input
                    id={`bulk-subject-${index}`}
                    value={draft.editedSubject ?? draft.subject}
                    disabled={draft.sendStatus === "sent" || draft.sendStatus === "sending"}
                    onChange={(event) => {
                      const editedSubject = event.target.value;
                      setDrafts((current) =>
                        current.map((item, itemIndex) =>
                          itemIndex === index ? { ...item, editedSubject } : item
                        )
                      );
                    }}
                  />
                </div>
                <div className="field">
                  <label htmlFor={`bulk-body-${index}`}>Email</label>
                  <textarea
                    id={`bulk-body-${index}`}
                    rows={9}
                    value={draft.editedBody ?? emailBody(draft)}
                    disabled={draft.sendStatus === "sent" || draft.sendStatus === "sending"}
                    onChange={(event) => {
                      const editedBody = event.target.value;
                      setDrafts((current) =>
                        current.map((item, itemIndex) =>
                          itemIndex === index ? { ...item, editedBody } : item
                        )
                      );
                    }}
                  />
                </div>
                {draft.sendError ? <p className="message error">{draft.sendError}</p> : null}
                {draft.sendStatus !== "sent" ? (
                  <button
                    className="primary"
                    type="button"
                    disabled={draft.sendStatus === "sending"}
                    onClick={() => handleApprove(draft, index)}
                  >
                    {draft.sendStatus === "sending"
                      ? "Sending..."
                      : mode === "auto"
                        ? "Retry this email"
                        : "Approve and send this email"}
                  </button>
                ) : null}
              </div>
            </details>
          ))}
        </div>
      ) : null}
    </section>
  );
}
