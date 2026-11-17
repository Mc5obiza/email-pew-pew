export default function InputPanel({
  resumeFile,
  onFileChange,
  companyDescription,
  onCompanyDescriptionChange,
  tone,
  onToneChange,
  toneOptions,
  senderName,
  onSenderNameChange,
  senderEmail,
  onSenderEmailChange,
  onGenerate,
  status,
  message
}) {
  const handleFileInput = (event) => {
    const file = event.target.files?.[0] || null;
    onFileChange(file);
  };

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Inputs</h2>
        <span className="badge">Step 1</span>
      </div>

      <div className="field">
        <label>Resume</label>
        <label className="upload">
          <input
            className="upload-input"
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={handleFileInput}
          />
          <span className="upload-cta">Choose file</span>
          <div className="upload-meta">
            <p>{resumeFile ? resumeFile.name : "Drop a PDF or DOCX"}</p>
            <span>We keep files local and only send to your backend.</span>
          </div>
        </label>
      </div>

      <div className="field">
        <label>Company description</label>
        <textarea
          placeholder="Paste the internship posting or a short company overview."
          rows={7}
          value={companyDescription}
          onChange={(event) => onCompanyDescriptionChange(event.target.value)}
        />
      </div>

      <div className="field split">
        <div>
          <label>Tone</label>
          <select value={tone} onChange={(event) => onToneChange(event.target.value)}>
            {toneOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label>Sender</label>
          <input
            type="text"
            placeholder="Your name"
            value={senderName}
            onChange={(event) => onSenderNameChange(event.target.value)}
          />
        </div>
      </div>

      <div className="field">
        <label>Email</label>
        <input
          type="email"
          placeholder="you@email.com"
          value={senderEmail}
          onChange={(event) => onSenderEmailChange(event.target.value)}
        />
      </div>

      <button className="primary" onClick={onGenerate} type="button">
        {status === "loading" ? "Generating..." : "Generate email"}
      </button>

      {message ? <p className={`message ${status}`}>{message}</p> : null}
    </section>
  );
}
