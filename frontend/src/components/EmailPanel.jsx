export default function EmailPanel({
  subject,
  onSubjectChange,
  recipientEmail,
  onRecipientEmailChange,
  editorRef,
  onEditorInput,
  onImproveWording,
  onMakeConcise,
  onAdaptTone,
  onRegenerate,
  onSend,
  gmailStatus,
  gmailEmail,
  gmailMessage,
  gmailMessageType,
  sendStatus,
  onConnectGmail,
  onDisconnectGmail
}) {
  return (
    <section className="panel panel-large">
      <div className="panel-header">
        <h2>Email draft</h2>
        <span className="badge">Step 2</span>
      </div>

      <div className="field">
        <label htmlFor="recipient-email">To</label>
        <input
          id="recipient-email"
          type="email"
          placeholder="recipient@example.com"
          value={recipientEmail}
          onChange={(event) => onRecipientEmailChange(event.target.value)}
        />
      </div>

      <div className="field">
        <label htmlFor="email-subject">Subject</label>
        <input
          id="email-subject"
          type="text"
          placeholder="Subject line"
          value={subject}
          onChange={(event) => onSubjectChange(event.target.value)}
        />
      </div>

      <div className="editor-toolbar">
        <button className="ghost" type="button" onClick={onImproveWording}>
          Improve wording
        </button>
        <button className="ghost" type="button" onClick={onMakeConcise}>
          Make concise
        </button>
        <button className="ghost" type="button" onClick={onAdaptTone}>
          Adapt tone
        </button>
      </div>

      <div
        ref={editorRef}
        className="editor"
        contentEditable
        suppressContentEditableWarning
        onInput={onEditorInput}
      />

      <div className="actions">
        <button className="ghost" type="button" onClick={onRegenerate}>
          Regenerate
        </button>
        <button
          className="primary"
          type="button"
          onClick={onSend}
          disabled={sendStatus === "sending" || gmailStatus !== "connected"}
        >
          {sendStatus === "sending" ? "Sending..." : "Send with Gmail"}
        </button>
      </div>

      <div className="gmail-connection" aria-live="polite">
        <div>
          <strong>
            {gmailStatus === "loading"
              ? "Checking Gmail connection..."
              : gmailStatus === "connected"
                ? `Connected as ${gmailEmail}`
                : gmailStatus === "connecting"
                  ? "Opening Google authorization..."
                  : gmailStatus === "disconnecting"
                    ? "Disconnecting Gmail..."
                    : gmailStatus === "error"
                      ? "Gmail connection needs attention"
                      : "Gmail is not connected"}
          </strong>
          {gmailMessage ? (
            <p className={`message ${gmailMessageType}`}>
              {gmailMessage}
            </p>
          ) : null}
        </div>
        {gmailStatus === "connected" ? (
          <button className="ghost" type="button" onClick={onDisconnectGmail}>
            Disconnect
          </button>
        ) : (
          <button
            className="ghost"
            type="button"
            onClick={onConnectGmail}
            disabled={["loading", "connecting", "disconnecting"].includes(gmailStatus)}
          >
            {gmailStatus === "connecting" ? "Connecting..." : "Connect Gmail"}
          </button>
        )}
      </div>

      <p className="hint">
        You can edit directly, highlight lines, or paste your own version. Sending uses the
        connected Gmail account and sends the current draft to the address above.
      </p>
    </section>
  );
}
