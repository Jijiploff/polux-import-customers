import { ReactNode } from "react";

export function FormField({
  label, required, children, error,
}: { label: string; required?: boolean; children: ReactNode; error?: string }) {
  return (
    <label className="form-field" style={{ display: "block", marginBottom: "0.75rem" }}>
      <span style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: 4 }}>
        {label}{required && <span style={{ color: "crimson" }}> *</span>}
      </span>
      {children}
      {error && <span style={{ color: "crimson", fontSize: "0.8rem" }}>{error}</span>}
    </label>
  );
}