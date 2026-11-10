"""Esquemas de administración: usuarios, reglas y catálogos."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Canal, OrigenItem, RolCodigo


class _OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- Usuarios ----
class UsuarioCreate(BaseModel):
    email: EmailStr
    nombre_completo: str
    password: str = Field(min_length=8)
    roles: list[RolCodigo] = [RolCodigo.OPERADOR]


class UsuarioUpdate(BaseModel):
    nombre_completo: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8)
    activo: Optional[bool] = None
    roles: Optional[list[RolCodigo]] = None


class UsuarioRead(_OrmModel):
    id: int
    email: EmailStr
    nombre_completo: str
    activo: bool
    ultimo_login: Optional[datetime]
    roles: list[RolCodigo] = Field(default_factory=list)


# ---- Reglas ----
class ReglaRead(_OrmModel):
    id: int
    codigo: str
    nombre: str
    categoria: str
    valor: str
    tipo_valor: str
    activo: bool


class ReglaUpdate(BaseModel):
    valor: Optional[str] = None
    activo: Optional[bool] = None


# ---- Hitos ----
class HitoCatalogoRead(_OrmModel):
    id: int
    codigo: str
    nombre: str
    origen: OrigenItem
    orden: int
    activo: bool


class HitoCatalogoCreate(BaseModel):
    codigo: str = Field(min_length=2, max_length=60)
    nombre: str = Field(min_length=2, max_length=160)
    origen: OrigenItem
    orden: int = Field(ge=1)
    activo: bool = True


class HitoCatalogoUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=2, max_length=160)
    orden: Optional[int] = Field(default=None, ge=1)
    activo: Optional[bool] = None


# ---- SLA ----
class SlaHitoRead(_OrmModel):
    id: int
    hito_id: int
    origen: OrigenItem
    dias_maximos: int
    horas_maximas: Optional[int]
    activo: bool


class SlaHitoCreate(BaseModel):
    hito_id: int
    origen: OrigenItem
    dias_maximos: int = Field(ge=0)
    horas_maximas: Optional[int] = Field(default=None, ge=0)
    activo: bool = True


class SlaHitoUpdate(BaseModel):
    dias_maximos: Optional[int] = Field(default=None, ge=0)
    horas_maximas: Optional[int] = Field(default=None, ge=0)
    activo: Optional[bool] = None


# ---- Plantillas ----
class PlantillaRead(_OrmModel):
    id: int
    codigo: str
    nombre: str
    canal: Canal
    evento: str
    cuerpo: str
    whatsapp_template_id: Optional[str] = None
    idioma: str
    activo: bool


class PlantillaCreate(BaseModel):
    codigo: str = Field(min_length=2, max_length=60)
    nombre: str = Field(min_length=2, max_length=160)
    canal: Canal
    evento: str = Field(min_length=2, max_length=80)
    cuerpo: str = Field(min_length=2)
    whatsapp_template_id: Optional[str] = Field(default=None, max_length=80)
    idioma: str = "es_PE"
    activo: bool = True


class PlantillaUpdate(BaseModel):
    nombre: Optional[str] = None
    cuerpo: Optional[str] = None
    whatsapp_template_id: Optional[str] = None
    activo: Optional[bool] = None


# ---- KPIs ----
class DimKpiRead(_OrmModel):
    id: int
    codigo: str
    nombre: str
    definicion: str
    unidad: str
    umbral_optimo: float
    umbral_alerta: float
    umbral_critico: float
    sentido: str
    es_complementario: bool


class DimKpiUpdate(BaseModel):
    umbral_optimo: Optional[float] = None
    umbral_alerta: Optional[float] = None
    umbral_critico: Optional[float] = None