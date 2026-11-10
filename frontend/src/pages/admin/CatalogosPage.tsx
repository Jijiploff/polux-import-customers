import { useEffect, useState } from "react";
import { adminApi } from "../../api/admin";
import { DataTable } from "../../components/DataTable";
import { Loading } from "../../components/Loading";
import { Modal } from "../../components/Modal";
import { FormField } from "../../components/FormField";
import type {
  Canal, DimKpi, HitoCatalogo, Origen, Plantilla, SlaHito,
} from "../../types/domain";

type Tab = "hitos" | "sla" | "plantillas" | "kpis";

export function CatalogosPage() {
  const [tab, setTab] = useState<Tab>("hitos");
  const [hitos, setHitos] = useState<HitoCatalogo[] | null>(null);
  const [slas, setSlas] = useState<SlaHito[] | null>(null);
  const [plantillas, setPlantillas] = useState<Plantilla[] | null>(null);
  const [kpis, setKpis] = useState<DimKpi[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadAll() {
    try {
      const [h, s, p, k] = await Promise.all([
        adminApi.catalogos.hitos(),
        adminApi.catalogos.sla(),
        adminApi.catalogos.plantillas(),
        adminApi.catalogos.kpis(),
      ]);
      setHitos(h); setSlas(s); setPlantillas(p); setKpis(k);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  useEffect(() => { loadAll(); }, []);

  // ============ Hitos ============
  const [hitoModal, setHitoModal] = useState<"crear" | "editar" | null>(null);
  const [hitoForm, setHitoForm] = useState<Partial<HitoCatalogo> & { origen?: Origen }>({});

  async function guardarHito() {
    try {
      if (hitoModal === "crear") {
        await adminApi.catalogos.crearHito({
          codigo: hitoForm.codigo!, nombre: hitoForm.nombre!,
          origen: hitoForm.origen!, orden: hitoForm.orden ?? 1,
          activo: hitoForm.activo ?? true,
        });
      } else if (hitoForm.id) {
        await adminApi.catalogos.actualizarHito(hitoForm.id, {
          nombre: hitoForm.nombre, orden: hitoForm.orden, activo: hitoForm.activo,
        });
      }
      setHitoModal(null); setHitoForm({});
      await loadAll();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  // ============ SLA ============
  const [slaModal, setSlaModal] = useState<"crear" | "editar" | null>(null);
  const [slaForm, setSlaForm] = useState<Partial<SlaHito>>({});

  async function guardarSla() {
    try {
      if (slaModal === "crear") {
        await adminApi.catalogos.crearSla({
          hito_id: slaForm.hito_id!, origen: slaForm.origen!,
          dias_maximos: slaForm.dias_maximos ?? 0,
          horas_maximas: slaForm.horas_maximas ?? undefined,
          activo: slaForm.activo ?? true,
        });
      } else if (slaForm.id) {
        await adminApi.catalogos.actualizarSla(slaForm.id, {
          dias_maximos: slaForm.dias_maximos,
          horas_maximas: slaForm.horas_maximas ?? undefined,
          activo: slaForm.activo,
        });
      }
      setSlaModal(null); setSlaForm({});
      await loadAll();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  // ============ Plantillas ============
  const [plModal, setPlModal] = useState<"crear" | "editar" | null>(null);
  const [plForm, setPlForm] = useState<Partial<Plantilla> & { canal?: Canal }>({});

  async function guardarPlantilla() {
    try {
      if (plModal === "crear") {
        await adminApi.catalogos.crearPlantilla({
          codigo: plForm.codigo!, nombre: plForm.nombre!,
          canal: (plForm.canal ?? "WHATSAPP") as any,
          evento: plForm.evento!, cuerpo: plForm.cuerpo!,
          whatsapp_template_id: plForm.whatsapp_template_id ?? null,
          idioma: plForm.idioma ?? "es_PE",
          activo: plForm.activo ?? true,
        });
      } else if (plForm.id) {
        await adminApi.catalogos.actualizarPlantilla(plForm.id, {
          nombre: plForm.nombre, cuerpo: plForm.cuerpo,
          whatsapp_template_id: plForm.whatsapp_template_id ?? null,
          activo: plForm.activo,
        });
      }
      setPlModal(null); setPlForm({});
      await loadAll();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  // ============ KPI ============
  const [editKpi, setEditKpi] = useState<{ id: number; o: string; a: string; c: string } | null>(null);
  async function guardarKpi() {
    if (!editKpi) return;
    try {
      await adminApi.catalogos.actualizarKpi(editKpi.id, {
        umbral_optimo: Number(editKpi.o),
        umbral_alerta: Number(editKpi.a),
        umbral_critico: Number(editKpi.c),
      });
      setEditKpi(null); await loadAll();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Catálogos</h1>
      <div style={{ display: "flex", gap: 4, marginBottom: "1rem" }}>
        {(["hitos", "sla", "plantillas", "kpis"] as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            style={{ background: tab === t ? "#0b57d0" : "white",
                     color: tab === t ? "white" : "#0f172a" }}>
            {t.toUpperCase()}
          </button>
        ))}
      </div>
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {tab === "hitos" && (!hitos ? <Loading /> : (
        <>
          <button style={{ marginBottom: "0.75rem" }}
            onClick={() => { setHitoForm({ activo: true, orden: 1 }); setHitoModal("crear"); }}>
            + Nuevo hito
          </button>
          <DataTable
            rows={hitos}
            columns={[
              { key: "cod", header: "Código", render: (h) => h.codigo },
              { key: "nom", header: "Nombre", render: (h) => h.nombre },
              { key: "ori", header: "Origen", render: (h) => h.origen },
              { key: "ord", header: "Orden", render: (h) => h.orden },
              { key: "act", header: "Activo", render: (h) => h.activo ? "Sí" : "No" },
              { key: "acc", header: "",
                render: (h) => <button onClick={() => { setHitoForm(h); setHitoModal("editar"); }}>
                  Editar
                </button> },
            ]}
          />
        </>
      ))}

      {tab === "sla" && (!slas ? <Loading /> : (
        <>
          <button style={{ marginBottom: "0.75rem" }}
            onClick={() => { setSlaForm({ dias_maximos: 1, activo: true }); setSlaModal("crear"); }}>
            + Nuevo SLA
          </button>
          <DataTable
            rows={slas}
            columns={[
              { key: "hito", header: "Hito ID", render: (s) => s.hito_id },
              { key: "ori", header: "Origen", render: (s) => s.origen },
              { key: "dias", header: "Días máx", render: (s) => s.dias_maximos },
              { key: "horas", header: "Horas máx", render: (s) => s.horas_maximas ?? "—" },
              { key: "act", header: "Activo", render: (s) => s.activo ? "Sí" : "No" },
              { key: "acc", header: "",
                render: (s) => <button onClick={() => { setSlaForm(s); setSlaModal("editar"); }}>
                  Editar
                </button> },
            ]}
          />
        </>
      ))}

      {tab === "plantillas" && (!plantillas ? <Loading /> : (
        <>
          <button style={{ marginBottom: "0.75rem" }}
            onClick={() => { setPlForm({ canal: "WHATSAPP", idioma: "es_PE", activo: true }); setPlModal("crear"); }}>
            + Nueva plantilla
          </button>
          <DataTable
            rows={plantillas}
            columns={[
              { key: "cod", header: "Código", render: (p) => p.codigo },
              { key: "nom", header: "Nombre", render: (p) => p.nombre },
              { key: "can", header: "Canal", render: (p) => p.canal },
              { key: "wa", header: "WhatsApp template", render: (p) => p.whatsapp_template_id ?? "—" },
              { key: "act", header: "Activo", render: (p) => p.activo ? "Sí" : "No" },
              { key: "acc", header: "",
                render: (p) => <button onClick={() => { setPlForm(p); setPlModal("editar"); }}>
                  Editar
                </button> },
            ]}
          />
        </>
      ))}

      {tab === "kpis" && (!kpis ? <Loading /> : (
        <DataTable
          rows={kpis}
          columns={[
            { key: "cod", header: "Código", render: (k) => k.codigo },
            { key: "nom", header: "Nombre", render: (k) => k.nombre },
            { key: "uni", header: "Unidad", render: (k) => k.unidad },
            { key: "o", header: "Óptimo",
              render: (k) => editKpi?.id === k.id ? (
                <input style={{ width: 70 }} value={editKpi.o}
                  onChange={(e) => setEditKpi({ ...editKpi, o: e.target.value })} />
              ) : k.umbral_optimo },
            { key: "a", header: "Alerta",
              render: (k) => editKpi?.id === k.id ? (
                <input style={{ width: 70 }} value={editKpi.a}
                  onChange={(e) => setEditKpi({ ...editKpi, a: e.target.value })} />
              ) : k.umbral_alerta },
            { key: "c", header: "Crítico",
              render: (k) => editKpi?.id === k.id ? (
                <input style={{ width: 70 }} value={editKpi.c}
                  onChange={(e) => setEditKpi({ ...editKpi, c: e.target.value })} />
              ) : k.umbral_critico },
            { key: "acc", header: "",
              render: (k) => editKpi?.id === k.id ? (
                <span>
                  <button onClick={guardarKpi}>OK</button>
                  <button onClick={() => setEditKpi(null)}>×</button>
                </span>
              ) : (
                <button onClick={() => setEditKpi({
                  id: k.id, o: String(k.umbral_optimo),
                  a: String(k.umbral_alerta), c: String(k.umbral_critico),
                })}>Editar</button>
              ) },
          ]}
        />
      ))}

      {/* Modales */}
      <Modal open={hitoModal !== null} title={`Hito · ${hitoModal}`}
             onClose={() => setHitoModal(null)}>
        <FormField label="Código" required>
          <input value={hitoForm.codigo ?? ""}
            disabled={hitoModal === "editar"}
            onChange={(e) => setHitoForm({ ...hitoForm, codigo: e.target.value })}
            style={{ width: "100%" }} />
        </FormField>
        <FormField label="Nombre" required>
          <input value={hitoForm.nombre ?? ""}
            onChange={(e) => setHitoForm({ ...hitoForm, nombre: e.target.value })}
            style={{ width: "100%" }} />
        </FormField>
        <FormField label="Origen" required>
          <select value={hitoForm.origen ?? "STOCK_TRUJILLO"}
            disabled={hitoModal === "editar"}
            onChange={(e) => setHitoForm({ ...hitoForm, origen: e.target.value as Origen })}>
            <option value="STOCK_TRUJILLO">Stock Trujillo</option>
            <option value="IMPORTACION">Importación</option>
          </select>
        </FormField>
        <FormField label="Orden" required>
          <input type="number" value={hitoForm.orden ?? 1}
            onChange={(e) => setHitoForm({ ...hitoForm, orden: Number(e.target.value) })} />
        </FormField>
        <label><input type="checkbox" checked={hitoForm.activo ?? true}
          onChange={(e) => setHitoForm({ ...hitoForm, activo: e.target.checked })} /> Activo</label>
        <div style={{ marginTop: "1rem" }}><button onClick={guardarHito}>Guardar</button></div>
      </Modal>

      <Modal open={slaModal !== null} title={`SLA · ${slaModal}`}
             onClose={() => setSlaModal(null)}>
        <FormField label="Hito ID" required>
          <input type="number" value={slaForm.hito_id ?? ""}
            disabled={slaModal === "editar"}
            onChange={(e) => setSlaForm({ ...slaForm, hito_id: Number(e.target.value) })} />
        </FormField>
        <FormField label="Origen" required>
          <select value={slaForm.origen ?? "STOCK_TRUJILLO"}
            disabled={slaModal === "editar"}
            onChange={(e) => setSlaForm({ ...slaForm, origen: e.target.value as Origen })}>
            <option value="STOCK_TRUJILLO">Stock Trujillo</option>
            <option value="IMPORTACION">Importación</option>
          </select>
        </FormField>
        <FormField label="Días máximos" required>
          <input type="number" value={slaForm.dias_maximos ?? 0}
            onChange={(e) => setSlaForm({ ...slaForm, dias_maximos: Number(e.target.value) })} />
        </FormField>
        <FormField label="Horas máximas (opcional)">
          <input type="number" value={slaForm.horas_maximas ?? ""}
            onChange={(e) => setSlaForm({ ...slaForm, horas_maximas: e.target.value ? Number(e.target.value) : undefined })} />
        </FormField>
        <div style={{ marginTop: "1rem" }}><button onClick={guardarSla}>Guardar</button></div>
      </Modal>

      <Modal open={plModal !== null} title={`Plantilla · ${plModal}`}
             onClose={() => setPlModal(null)}>
        <FormField label="Código" required>
          <input value={plForm.codigo ?? ""}
            disabled={plModal === "editar"}
            onChange={(e) => setPlForm({ ...plForm, codigo: e.target.value })}
            style={{ width: "100%" }} />
        </FormField>
        <FormField label="Nombre" required>
          <input value={plForm.nombre ?? ""}
            onChange={(e) => setPlForm({ ...plForm, nombre: e.target.value })}
            style={{ width: "100%" }} />
        </FormField>
        <FormField label="Canal" required>
          <select value={plForm.canal ?? "WHATSAPP"}
            disabled={plModal === "editar"}
            onChange={(e) => setPlForm({ ...plForm, canal: e.target.value as Canal })}>
            <option value="WHATSAPP">WhatsApp</option>
            <option value="EMAIL">Email</option>
            <option value="WEB">Web</option>
          </select>
        </FormField>
        <FormField label="Evento" required>
          <input value={plForm.evento ?? ""}
            disabled={plModal === "editar"}
            onChange={(e) => setPlForm({ ...plForm, evento: e.target.value })}
            style={{ width: "100%" }} />
        </FormField>
        <FormField label="Cuerpo" required>
          <textarea value={plForm.cuerpo ?? ""}
            onChange={(e) => setPlForm({ ...plForm, cuerpo: e.target.value })}
            style={{ width: "100%", minHeight: 100 }} />
        </FormField>
        <FormField label="WhatsApp template ID (opcional)">
          <input value={plForm.whatsapp_template_id ?? ""}
            onChange={(e) => setPlForm({ ...plForm, whatsapp_template_id: e.target.value })}
            style={{ width: "100%" }} />
        </FormField>
        <label><input type="checkbox" checked={plForm.activo ?? true}
          onChange={(e) => setPlForm({ ...plForm, activo: e.target.checked })} /> Activa</label>
        <div style={{ marginTop: "1rem" }}><button onClick={guardarPlantilla}>Guardar</button></div>
      </Modal>
    </div>
  );
}