import { useEffect, useMemo, useRef, useState } from "react";

import EmailPanel from "./components/EmailPanel";
import BulkEmailPanel from "./components/BulkEmailPanel";
import InputPanel from "./components/InputPanel";
import Topbar from "./components/Topbar";

const API_BASE =
  import.meta.env.VITE_API_BASE ||
  `${window.location.protocol}//${window.location.hostname}:8000`;

const toneOptions = [
  "Startup",
  "Corporate",
  "AI Company",
  "Data Company",
  "Formal"
];

export default function App() {
  const [resumeFile, setResumeFile] = useState(null);
  const [companyDescription, setCompanyDescription] = useState("");
  const [tone, setTone] = useState("Formal");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [senderName, setSenderName] = useState("");
  const [senderEmail, setSenderEmail] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const [gmailStatus, setGmailStatus] = useState("loading");
  const [gmailEmail, setGmailEmail] = useState("");
  const [gmailMessage, setGmailMessage] = useState("");
  const [gmailMessageType, setGmailMessageType] = useState("success");
  const [sendStatus, setSendStatus] = useState("idle");
  const [theme, setTheme] = useState(() =>
    window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light"
  );

  const editorRef = useRef(null);
  const accent = useMemo(() => (theme === "dark" ? "#7ab0ff" : "#2b5fd9"), [theme]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const refreshGmailStatus = async () => {
    const response = await fetch(`${API_BASE}/auth/gmail/status`, {
      credentials: "include"
    });
    if (!response.ok) {
      throw new Error("Could not check Gmail connection.");
    }
    const data = await response.json();
    setGmailStatus(data.connected ? "connected" : "disconnected");
    setGmailEmail(data.email || "");
    return data;
  };

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const gmailResult = query.get("gmail");
    const gmailError = query.get("gmail_error");

    if (gmailResult === "connected") {
      setGmailMessageType("success");
      setGmailMessage("Gmail connected successfully.");
    } else if (gmailError) {
      const messages = {
        authorization_cancelled: "Gmail connection was cancelled.",
        authorization_failed: "Gmail authorization failed. Please try again.",
        invalid_state: "Gmail authorization expired. Please connect again."
      };
      setGmailMessage(messages[gmailError] || "Could not connect Gmail. Please try again.");
      setGmailMessageType("error");
    }

    if (gmailResult || gmailError) {
      window.history.replaceState({}, "", window.location.pathname);
    }

    refreshGmailStatus().catch((error) => {
      setGmailStatus("error");
      setGmailMessageType("error");
      setGmailMessage(error.message || "Could not check Gmail connection.");
    });
  }, []);

  useEffect(() => {
    if (!editorRef.current) {
      return;
    }
    editorRef.current.innerText = body;
  }, [body]);

  const handleFileChange = (file) => {
    setResumeFile(file);
  };

  const buildCompanyText = () => {
    if (!companyDescription.trim()) {
      return "";
    }
    return `Tone: ${tone}\n${companyDescription.trim()}`;
  };

  const handleGenerate = async () => {
    setMessage("");

    if (!resumeFile) {
      setMessage("Upload your resume to generate the email.");
      setStatus("error");
      return;
    }

    if (!companyDescription.trim()) {
      setMessage("Add a company description or internship posting.");
      setStatus("error");
      return;
    }

    setStatus("loading");

    try {
      const form = new FormData();
      form.append("resume_file", resumeFile);
      form.append("company_description", buildCompanyText());
      if (senderName.trim()) {
        form.append("sender_name", senderName.trim());
      }
      if (senderEmail.trim()) {
        form.append("sender_email", senderEmail.trim());
      }

      const response = await fetch(`${API_BASE}/generate-email/from-file`, {
        method: "POST",
        body: form
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || "Generation failed.");
      }

      const data = await response.json();
      const nextSubject = data.subject || "";
      const nextBody = [data.greeting, "", data.body, "", data.signature]
        .filter(Boolean)
        .join("\n")
        .trim();

      setSubject(nextSubject);
      setBody(nextBody);
      setStatus("success");
    } catch (error) {
      setStatus("error");
      setMessage(error.message || "Something went wrong.");
    }
  };

  const handleConnectGmail = async () => {
    setGmailStatus("connecting");
    setGmailMessage("");
    setGmailMessageType("success");
    try {
      const response = await fetch(`${API_BASE}/auth/gmail/login`, {
        credentials: "include"
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Could not start Gmail authorization.");
      }
      window.location.assign(data.authorization_url);
    } catch (error) {
      setGmailStatus("error");
      setGmailMessageType("error");
      setGmailMessage(error.message || "Could not start Gmail authorization.");
    }
  };

  const handleDisconnectGmail = async () => {
    setGmailStatus("disconnecting");
    setGmailMessage("");
    try {
      const response = await fetch(`${API_BASE}/auth/gmail/disconnect`, {
        method: "DELETE",
        credentials: "include"
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Could not disconnect Gmail.");
      }
      setGmailStatus("disconnected");
      setGmailEmail("");
      setGmailMessageType(data.revoked ? "success" : "error");
      setGmailMessage(
        data.revoked
          ? "Gmail was disconnected and its authorization was revoked."
          : "Disconnected from this app, but Google could not revoke access. Remove this app in your Google Account security settings."
      );
    } catch (error) {
      setGmailStatus("error");
      setGmailMessageType("error");
      setGmailMessage(error.message || "Could not disconnect Gmail.");
    }
  };

  const handleSend = async () => {
    setGmailMessage("");
    if (gmailStatus !== "connected") {
      setSendStatus("error");
      setGmailMessageType("error");
      setGmailMessage("Connect Gmail before sending this draft.");
      return;
    }
    if (!recipientEmail.trim() || !subject.trim() || !body.trim()) {
      setSendStatus("error");
      setGmailMessageType("error");
      setGmailMessage("Enter a recipient, subject, and email body before sending.");
      return;
    }

    setSendStatus("sending");
    try {
      const response = await fetch(`${API_BASE}/auth/gmail/send`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recipient: recipientEmail.trim(),
          subject: subject.trim(),
          body: body.trim()
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Gmail could not send this message.");
      }
      setSendStatus("success");
      setGmailMessageType("success");
      setGmailMessage("Email sent successfully with Gmail.");
    } catch (error) {
      setSendStatus("error");
      setGmailMessageType("error");
      setGmailMessage(
        error instanceof TypeError
          ? "Could not confirm Gmail's response. Check Sent mail before retrying to avoid duplicates."
          : error.message || "Gmail could not send this message. Your draft is unchanged."
      );
    }
  };

  const toggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  const handleEditorInput = (event) => {
    setBody(event.currentTarget.innerText);
  };

  const noop = () => {};

  return (
    <div className="app" style={{ "--accent": accent }}>
      <Topbar theme={theme} onToggleTheme={toggleTheme} />

      <main className="grid">
        <InputPanel
          resumeFile={resumeFile}
          onFileChange={handleFileChange}
          companyDescription={companyDescription}
          onCompanyDescriptionChange={setCompanyDescription}
          tone={tone}
          onToneChange={setTone}
          toneOptions={toneOptions}
          senderName={senderName}
          onSenderNameChange={setSenderName}
          senderEmail={senderEmail}
          onSenderEmailChange={setSenderEmail}
          onGenerate={handleGenerate}
          status={status}
          message={message}
        />

        <EmailPanel
          subject={subject}
          onSubjectChange={setSubject}
          recipientEmail={recipientEmail}
          onRecipientEmailChange={setRecipientEmail}
          editorRef={editorRef}
          onEditorInput={handleEditorInput}
          onImproveWording={noop}
          onMakeConcise={noop}
          onAdaptTone={noop}
          onRegenerate={noop}
          onSend={handleSend}
          gmailStatus={gmailStatus}
          gmailEmail={gmailEmail}
          gmailMessage={gmailMessage}
          gmailMessageType={gmailMessageType}
          sendStatus={sendStatus}
          onConnectGmail={handleConnectGmail}
          onDisconnectGmail={handleDisconnectGmail}
        />
      </main>
      <BulkEmailPanel
        resumeFile={resumeFile}
        senderName={senderName}
        senderEmail={senderEmail}
        gmailStatus={gmailStatus}
      />
    </div>
  );
}
