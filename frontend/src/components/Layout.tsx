import { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useLive } from "../lib/live";

export default function Layout({ children }: { children: ReactNode }) {
  const { role, username, signOut } = useAuth();
  const { connected, notice } = useLive();
  const navigate = useNavigate();

  const link = ({ isActive }: { isActive: boolean }) =>
    "navlink" + (isActive ? " active" : "");

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">NEPSE <span>Research</span></div>
        <nav>
          <NavLink to="/dashboard" className={link}>
            Companies
          </NavLink>
          <NavLink to="/compare" className={link}>
            Comparison
          </NavLink>
          {role === "admin" && (
            <NavLink to="/admin" className={link}>
              Admin
            </NavLink>
          )}
        </nav>
        <div className="topbar-right">
          <span className={"dot " + (connected ? "on" : "off")} title={connected ? "live" : "disconnected"} />
          <span className="muted">{connected ? "live" : "offline"}</span>
          <span className="pill">{role}</span>
          <span className="muted">@{username}</span>
          <button
            className="ghost"
            onClick={() => {
              signOut();
              navigate("/login");
            }}
          >
            Sign out
          </button>
        </div>
      </header>

      {notice && <div className="toast">{notice}</div>}

      <main className="content">{children}</main>

      <footer className="footer">
        NEPSE Research — demo build. Data from the bundled seed unless a live crawl has run.
      </footer>
    </div>
  );
}