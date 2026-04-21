import type { ReactNode } from "react";

export interface OperatorShellProps {
  account: {
    label: string;
    detail?: string;
  };
  activeSection: string;
  sections: string[];
  children: ReactNode;
}

export function OperatorShell({ account, activeSection, sections, children }: OperatorShellProps) {
  return (
    <div className="operator-shell">
      <aside className="operator-shell__rail" aria-label="Primary navigation">
        <div className="operator-shell__brand">
          <span className="operator-shell__brand-mark">SM</span>
          <span>
            <strong>Slack Mirror</strong>
            <small>Operator console</small>
          </span>
        </div>
        <nav className="operator-shell__nav">
          {sections.map((section) => (
            <a
              aria-current={section === activeSection ? "page" : undefined}
              className="operator-shell__nav-link"
              href={`#${section.toLowerCase()}`}
              key={section}
            >
              {section}
            </a>
          ))}
        </nav>
      </aside>
      <main className="operator-shell__main">
        <header className="operator-shell__topbar">
          <div>
            <p className="eyebrow">User-scoped runtime</p>
            <h1>Selected Result Workbench</h1>
          </div>
          <div className="account-chip" aria-label="Signed-in account">
            <span className="account-chip__avatar">{account.label.slice(0, 1).toUpperCase()}</span>
            <span>
              <strong>{account.label}</strong>
              {account.detail ? <small>{account.detail}</small> : null}
            </span>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
