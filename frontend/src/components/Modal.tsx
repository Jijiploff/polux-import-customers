import { ReactNode } from "react";

export function Modal({
  open, title, onClose, children,
}: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" style={{
      position: "fixed", inset: 0, background: "rgba(15,23,42,0.55)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100,
      padding: "1rem",
    }} onClick={onClose}>
      <div className="modal-panel" style={{
        background: "white", borderRadius: 8, padding: "1.5rem",
        maxWidth: 640, width: "100%", maxHeight: "85vh", overflow: "auto",
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "1rem" }}>
          <h3 style={{ margin: 0 }}>{title}</h3>
          <button onClick={onClose}>×</button>
        </div>
        {children}
      </div>
    </div>
  );
}