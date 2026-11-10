"""Catálogos administrables: hitos, SLA, plantillas y definiciones KPI."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models import DimKpi, HitoCatalogo, PlantillaMensaje, SlaHito
from app.schemas.admin import (
    DimKpiRead,
    DimKpiUpdate,
    HitoCatalogoCreate,
    HitoCatalogoRead,
    HitoCatalogoUpdate,
    PlantillaCreate,
    PlantillaRead,
    PlantillaUpdate,
    SlaHitoCreate,
    SlaHitoRead,
    SlaHitoUpdate,
)

router = APIRouter(dependencies=[Depends(get_current_user)])


# =========================== Hitos ===========================
@router.get("/hitos", response_model=list[HitoCatalogoRead])
def listar_hitos(db: Session = Depends(get_db)):
    return db.scalars(
        select(HitoCatalogo).order_by(HitoCatalogo.origen, HitoCatalogo.orden)
    ).all()


@router.post(
    "/hitos",
    response_model=HitoCatalogoRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def crear_hito(payload: HitoCatalogoCreate, db: Session = Depends(get_db)):
    if db.scalar(select(HitoCatalogo).where(HitoCatalogo.codigo == payload.codigo)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Código de hito ya existe")
    obj = HitoCatalogo(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/hitos/{hito_id}",
    response_model=HitoCatalogoRead,
    dependencies=[Depends(require_admin)],
)
def actualizar_hito(
    hito_id: int, payload: HitoCatalogoUpdate, db: Session = Depends(get_db)
):
    obj = db.get(HitoCatalogo, hito_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hito no encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


# =========================== SLA ===========================
@router.get("/sla", response_model=list[SlaHitoRead])
def listar_sla(db: Session = Depends(get_db)):
    return db.scalars(select(SlaHito).order_by(SlaHito.hito_id)).all()


@router.post(
    "/sla",
    response_model=SlaHitoRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def crear_sla(payload: SlaHitoCreate, db: Session = Depends(get_db)):
    if db.get(HitoCatalogo, payload.hito_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "hito_id inválido")
    existente = db.scalar(
        select(SlaHito).where(
            SlaHito.hito_id == payload.hito_id, SlaHito.origen == payload.origen
        )
    )
    if existente:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ya existe un SLA para este hito y origen",
        )
    obj = SlaHito(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/sla/{sla_id}",
    response_model=SlaHitoRead,
    dependencies=[Depends(require_admin)],
)
def actualizar_sla(
    sla_id: int, payload: SlaHitoUpdate, db: Session = Depends(get_db)
):
    obj = db.get(SlaHito, sla_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SLA no encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


# =========================== Plantillas ===========================
@router.get("/plantillas", response_model=list[PlantillaRead])
def listar_plantillas(db: Session = Depends(get_db)):
    return db.scalars(
        select(PlantillaMensaje).order_by(PlantillaMensaje.codigo)
    ).all()


@router.post(
    "/plantillas",
    response_model=PlantillaRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def crear_plantilla(payload: PlantillaCreate, db: Session = Depends(get_db)):
    if db.scalar(
        select(PlantillaMensaje).where(PlantillaMensaje.codigo == payload.codigo)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Código de plantilla ya existe")
    obj = PlantillaMensaje(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch(
    "/plantillas/{plantilla_id}",
    response_model=PlantillaRead,
    dependencies=[Depends(require_admin)],
)
def actualizar_plantilla(
    plantilla_id: int,
    payload: PlantillaUpdate,
    db: Session = Depends(get_db),
):
    obj = db.get(PlantillaMensaje, plantilla_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plantilla no encontrada")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


# =========================== KPIs ===========================
@router.get("/kpis", response_model=list[DimKpiRead])
def listar_kpis(db: Session = Depends(get_db)):
    return db.scalars(select(DimKpi).order_by(DimKpi.id)).all()


@router.patch(
    "/kpis/{kpi_id}",
    response_model=DimKpiRead,
    dependencies=[Depends(require_admin)],
)
def actualizar_kpi(kpi_id: int, payload: DimKpiUpdate, db: Session = Depends(get_db)):
    kpi = db.get(DimKpi, kpi_id)
    if kpi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "KPI no encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(kpi, field, value)
    db.commit()
    db.refresh(kpi)
    return kpi