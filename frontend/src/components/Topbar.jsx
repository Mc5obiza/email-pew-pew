export default function Topbar({ theme, onToggleTheme }) {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark" />
        <div>
          <p className="brand-title">Internship Email Studio</p>
          <p className="brand-sub">Calm, focused writing with real context.</p>
        </div>
      </div>
      <button className="ghost" onClick={onToggleTheme} type="button">
        {theme === "dark" ? "Light mode" : "Dark mode"}
      </button>
    </header>
  );
}
