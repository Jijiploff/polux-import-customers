from datetime import datetime, timedelta

from app.services.delivery_conversation import _receptor, _ubicacion


def test_receptor_accepts_comma_separated_natural_format():
    fecha = (datetime.utcnow() + timedelta(days=4)).strftime("%d/%m/%Y")
    result = _receptor(
        f"María Rodriguez, 70000001, 923027824, {fecha}, "
        "entre la 1 y 3 de la tarde."
    )

    assert result == {
        "receptor_nombre": "María Rodriguez",
        "receptor_dni": "70000001",
        "receptor_telefono": "923027824",
        "fecha": (datetime.utcnow() + timedelta(days=4)).strftime("%Y-%m-%d"),
        "franja_horaria": "13:00-15:00",
    }


def test_receptor_accepts_multiline_format():
    fecha = (datetime.utcnow() + timedelta(days=4)).strftime("%d/%m/%Y")
    result = _receptor(
        f"María Rodriguez\n70000001\n923027824\n{fecha}\n"
        "Franja entre la 1 y 3 de la tarde."
    )

    assert result is not None
    assert result["receptor_nombre"] == "María Rodriguez"
    assert result["franja_horaria"] == "13:00-15:00"


def test_receptor_rejects_past_date():
    assert _receptor(
        "María Rodriguez, 70000001, 923027824, 01/01/2020, 13:00-15:00"
    ) is None


def test_ubicacion_separates_district_and_reference():
    result = _ubicacion(
        "La direccion es Calle san Carlos 501, El Porvenir.\n"
        "A 2 cuadras del mercado Miguel Grau.",
        "DOMICILIO",
    )

    assert result == {
        "direccion": "Calle san Carlos 501",
        "distrito": "El Porvenir",
        "referencia": "A 2 cuadras del mercado Miguel Grau",
    }
