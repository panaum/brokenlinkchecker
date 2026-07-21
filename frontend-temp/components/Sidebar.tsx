import { Link2 } from "lucide-react";
import { Logo } from "./Logo";

// Left sidebar — mirrors the Deliverables Dashboard shell (light surface, dark
// text, indigo active pill, small workspace header at top). LinkSpy is a
// single-tool app, so the menu carries one honest destination.
const NAV = [{ label: "Link Checker", icon: Link2, active: true }];

export default function Sidebar() {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border-soft bg-[#fbfbfd] px-3 py-5">
      {/* Workspace header */}
      <div className="mb-7 flex items-center gap-2.5 px-2">
        <div className="flex size-9 items-center justify-center rounded-xl border border-border-soft bg-card shadow-sm">
          <Logo className="size-6" />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold text-text-primary">LinkSpy</span>
          <span className="text-[11px] text-text-muted">Apexure workspace</span>
        </div>
      </div>

      <span className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">
        Menu
      </span>
      <nav className="flex flex-1 flex-col gap-0.5">
        {NAV.map((item) => {
          const Icon = item.icon;
          return (
            <span
              key={item.label}
              aria-current={item.active ? "page" : undefined}
              className={
                item.active
                  ? "relative flex items-center gap-3 rounded-lg bg-accent/10 px-3 py-2 text-sm font-medium text-accent ring-1 ring-inset ring-accent/15"
                  : "relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-text-secondary"
              }
            >
              <Icon className="size-[18px]" strokeWidth={item.active ? 2 : 1.5} />
              {item.label}
            </span>
          );
        })}
      </nav>

      <p className="mt-3 px-3 text-[10px] tracking-wide text-text-muted/50">
        LinkSpy · Broken Link Checker
      </p>
    </aside>
  );
}
