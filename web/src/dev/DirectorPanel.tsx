import { useEffect, useState, type ReactNode } from "react";

/* THE DIRECTOR PANEL.
 *
 * The states are the real work in this product: searching, low confidence,
 * needing a clarifying question, unknown, stale, offline, connecting, camera
 * denied, submitted but not published. Reaching "camera denied + offline +
 * stale coverage" by playing naturally is painful, and a reviewer who cannot
 * reach a state cannot judge it.
 *
 * So both routes exist. Every state is reachable by ordinary use, and this
 * panel is the shortcut. It renders only when import.meta.env.DEV is true.
 *
 * It is also absent from a production build, which it did not used to be. It
 * was imported statically by App.tsx, and while both panels returned null in
 * production their props – every state label in this product – were built
 * either way, so the copy shipped to every user. It is reached through
 * dev/DevTools.tsx now, behind a dynamic import on a DEV branch that a build
 * folds away, and scripts/check-bundle.mjs fails if any of it reappears in
 * dist. Add controls here freely: none of it can reach a user.
 *
 * Rebuilt from the Claude Design prototype's tweaks panel, minus the host
 * protocol that talked to the design canvas – there is no canvas here.
 * Deliberately styled outside the design system: it is scaffolding standing
 * next to the building, and it should not be mistaken for part of it.
 */

const PANEL_CSS = `
.dp{position:fixed;inset-inline-end:16px;inset-block-end:16px;z-index:2147483646;inline-size:264px;
  max-block-size:calc(100vh - 32px);display:flex;flex-direction:column;
  background:rgba(250,249,247,.88);color:#29261b;
  -webkit-backdrop-filter:blur(24px) saturate(160%);backdrop-filter:blur(24px) saturate(160%);
  border:.5px solid rgba(255,255,255,.6);border-radius:14px;
  box-shadow:0 1px 0 rgba(255,255,255,.5) inset,0 12px 40px rgba(0,0,0,.18);
  font:11.5px/1.4 ui-sans-serif,system-ui,-apple-system,sans-serif;overflow:hidden}
.dp-hd{display:flex;align-items:center;justify-content:space-between;
  padding:10px 8px 10px 14px;user-select:none;border-block-end:.5px solid rgba(0,0,0,.08)}
.dp-hd b{font-size:12px;font-weight:600;letter-spacing:.01em}
.dp-x{appearance:none;border:0;background:transparent;color:rgba(41,38,27,.55);
  inline-size:22px;block-size:22px;border-radius:6px;cursor:pointer;font-size:13px;line-height:1}
.dp-x:hover{background:rgba(0,0,0,.06);color:#29261b}
.dp-body{padding:2px 14px 14px;display:flex;flex-direction:column;gap:10px;
  overflow-y:auto;min-block-size:0;scrollbar-width:thin}
.dp-row{display:flex;flex-direction:column;gap:5px}
.dp-lbl{color:rgba(41,38,27,.72);font-weight:500}
.dp-sect{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
  color:rgba(41,38,27,.45);padding-block-start:10px}
.dp-sect:first-child{padding-block-start:0}
.dp-field{appearance:none;box-sizing:border-box;inline-size:100%;block-size:26px;padding:0 8px;
  border:.5px solid rgba(0,0,0,.1);border-radius:7px;
  background:rgba(255,255,255,.7);color:inherit;font:inherit;outline:none;cursor:pointer}
.dp-field:focus{border-color:rgba(0,0,0,.25);background:#fff}
.dp-seg{display:flex;padding:2px;border-radius:8px;background:rgba(0,0,0,.06);gap:2px}
.dp-seg button{appearance:none;flex:1;border:0;background:transparent;color:inherit;font:inherit;
  font-weight:500;min-block-size:22px;border-radius:6px;cursor:pointer;padding:4px 6px;line-height:1.2}
.dp-seg button[aria-pressed=true]{background:rgba(255,255,255,.95);box-shadow:0 1px 2px rgba(0,0,0,.12)}
.dp-btn{appearance:none;inline-size:100%;block-size:26px;border:.5px solid rgba(0,0,0,.12);
  border-radius:7px;background:rgba(255,255,255,.7);color:inherit;font:inherit;cursor:pointer}
.dp-btn:hover{background:#fff}
.dp-open{position:fixed;inset-inline-end:16px;inset-block-end:16px;z-index:2147483646;
  appearance:none;border:.5px solid rgba(0,0,0,.12);border-radius:999px;cursor:pointer;
  background:rgba(250,249,247,.9);-webkit-backdrop-filter:blur(20px);backdrop-filter:blur(20px);
  box-shadow:0 8px 24px rgba(0,0,0,.16);padding:8px 14px;
  font:11.5px/1 ui-sans-serif,system-ui,sans-serif;font-weight:600;color:#29261b}
@media (prefers-reduced-motion:no-preference){.dp{transition:opacity .12s ease}}
`;

export function DirectorPanel({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(true);

  useEffect(() => {
    const id = "sbr-director-css";
    if (document.getElementById(id)) return;
    const el = document.createElement("style");
    el.id = id;
    el.textContent = PANEL_CSS;
    document.head.appendChild(el);
  }, []);

  if (!import.meta.env.DEV) return null;

  if (!open) {
    return (
      <button type="button" className="dp-open" onClick={() => setOpen(true)}>
        States
      </button>
    );
  }

  return (
    <aside className="dp" dir="ltr" lang="en" aria-label="State director">
      <div className="dp-hd">
        <b>States</b>
        <button type="button" className="dp-x" onClick={() => setOpen(false)} aria-label="Hide">
          ×
        </button>
      </div>
      <div className="dp-body">{children}</div>
    </aside>
  );
}

export function Section({ label }: { label: string }) {
  return <div className="dp-sect">{label}</div>;
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly T[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="dp-row">
      <span className="dp-lbl">{label}</span>
      <div className="dp-seg">
        {options.map((o) => (
          <button key={o} type="button" aria-pressed={o === value} onClick={() => onChange(o)}>
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Select<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="dp-row">
      <span className="dp-lbl">{label}</span>
      <select className="dp-field" value={value} onChange={(e) => onChange(e.target.value as T)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function Toggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="dp-row">
      <span className="dp-lbl">{label}</span>
      <div className="dp-seg">
        <button type="button" aria-pressed={!value} onClick={() => onChange(false)}>
          off
        </button>
        <button type="button" aria-pressed={value} onClick={() => onChange(true)}>
          on
        </button>
      </div>
    </div>
  );
}

export function Action({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" className="dp-btn" onClick={onClick}>
      {label}
    </button>
  );
}
