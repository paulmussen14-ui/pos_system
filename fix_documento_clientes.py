"""Arregla el campo Documento (DNI/RUC) de los clientes.

Problemas que corrige:
  1. Editar un cliente BORRABA su documento (el servicio guardaba siempre "").
  2. El formulario no tenia campo Documento, asi que la busqueda por
     documento nunca servia.

Que cambia:
  - services/cliente_service.py: crear() y actualizar() aceptan documento.
    Si actualizar() no recibe documento, CONSERVA el que ya tenia.
  - ui/clientes/clientes_page.py: el formulario suma "Documento (DNI/RUC)" y
    el buscador dice que tambien busca por telefono y documento.

Uso (desde la carpeta pos_system, app cerrada):
    python fix_documento_clientes.py

- Guarda copias .bak antes de tocar nada.
- Respeta los saltos de linea (Windows CRLF o Linux LF).
- Si algo no coincide con lo esperado, NO modifica nada y te avisa.
- Si ya esta aplicado, no hace nada.
"""
import shutil
import sys
from pathlib import Path

SERVICIO = Path("services/cliente_service.py")
PAGINA = Path("ui/clientes/clientes_page.py")

NUEVO_SERVICIO = '''    def crear(self, nombre: str, telefono: str, direccion: str, documento: str = "") -> int:
        nombre = nombre.strip()
        if not nombre:
            raise ClienteError("El nombre del cliente es obligatorio.")
        cliente = Cliente(id=None, nombre=nombre, documento=(documento or "").strip(),
                           telefono=telefono.strip(), direccion=direccion.strip())
        return self.cliente_repo.crear(cliente)

    def actualizar(self, cliente_id: int, nombre: str, telefono: str, direccion: str,
                    documento: str | None = None) -> None:
        """documento=None conserva el documento que el cliente ya tenia (asi
        una pantalla que no lo edita no lo borra por accidente). Para borrarlo
        a proposito, pasar documento="" ."""
        nombre = nombre.strip()
        if not nombre:
            raise ClienteError("El nombre del cliente es obligatorio.")
        if documento is None:
            existente = self.cliente_repo.obtener_por_id(cliente_id)
            documento = (existente.documento if existente else "") or ""
        cliente = Cliente(id=cliente_id, nombre=nombre, documento=documento.strip(),
                           telefono=telefono.strip(), direccion=direccion.strip())
        self.cliente_repo.actualizar(cliente)

'''

GUARDAR_VIEJO = '''                self.cliente_service.actualizar(
                    self.cliente.id, self.input_nombre.text(),
                    self.input_telefono.text(), self.input_direccion.text(),
                )
            else:
                self.cliente_service.crear(
                    self.input_nombre.text(),
                    self.input_telefono.text(), self.input_direccion.text(),
                )
'''
GUARDAR_NUEVO = '''                self.cliente_service.actualizar(
                    self.cliente.id, self.input_nombre.text(),
                    self.input_telefono.text(), self.input_direccion.text(),
                    self.input_documento.text(),
                )
            else:
                self.cliente_service.crear(
                    self.input_nombre.text(),
                    self.input_telefono.text(), self.input_direccion.text(),
                    self.input_documento.text(),
                )
'''

FORM_VIEJO = '''        self.input_direccion = QLineEdit()

        form.addRow("Nombre:", self.input_nombre)
        form.addRow("Teléfono:", self.input_telefono)
        form.addRow("Dirección:", self.input_direccion)
'''
FORM_NUEVO = '''        self.input_direccion = QLineEdit()
        self.input_documento = QLineEdit()
        self.input_documento.setPlaceholderText("DNI o RUC (opcional)")

        form.addRow("Nombre:", self.input_nombre)
        form.addRow("Documento (DNI/RUC):", self.input_documento)
        form.addRow("Teléfono:", self.input_telefono)
        form.addRow("Dirección:", self.input_direccion)
'''


def leer(ruta: Path):
    crudo = ruta.read_bytes().decode("utf-8")
    return crudo.replace("\r\n", "\n"), "\r\n" in crudo


def escribir(ruta: Path, texto: str, crlf: bool) -> None:
    if crlf:
        texto = texto.replace("\n", "\r\n")
    ruta.write_bytes(texto.encode("utf-8"))


def reemplazar_una_vez(texto: str, viejo: str, nuevo: str, nombre: str) -> str:
    if texto.count(viejo) != 1:
        raise ValueError(f"No encontre '{nombre}' (tu archivo es distinto al esperado).")
    return texto.replace(viejo, nuevo)


def main() -> int:
    print("== Arreglando documento de clientes ==")
    print(f"Carpeta actual: {Path.cwd()}")
    for r in (SERVICIO, PAGINA):
        if not r.exists():
            print(f"No encuentro {r}. Ejecuta este script desde la carpeta pos_system.")
            return 1

    serv, crlf_serv = leer(SERVICIO)
    pag, crlf_pag = leer(PAGINA)

    if "documento: str | None" in serv and "input_documento" in pag:
        print("El arreglo ya estaba aplicado. No se cambio nada.")
        return 0

    try:
        a = serv.find("    def crear(")
        b = serv.find("    def eliminar(")
        if a == -1 or b == -1 or b < a:
            raise ValueError("No encontre 'crear/actualizar' en cliente_service (archivo distinto al esperado).")
        serv_nuevo = serv[:a] + NUEVO_SERVICIO + serv[b:]

        pag_nuevo = reemplazar_una_vez(pag, GUARDAR_VIEJO, GUARDAR_NUEVO, "_guardar del formulario")
        pag_nuevo = reemplazar_una_vez(pag_nuevo, FORM_VIEJO, FORM_NUEVO, "campos del formulario")
        pag_nuevo = reemplazar_una_vez(
            pag_nuevo, "self.resize(360, 220)", "self.resize(380, 270)", "tamano del formulario")
        pag_nuevo = reemplazar_una_vez(
            pag_nuevo, '            self.input_direccion.setText(cliente.direccion or "")\n',
            '            self.input_direccion.setText(cliente.direccion or "")\n'
            '            self.input_documento.setText(cliente.documento or "")\n',
            "carga del cliente en el formulario")
        pag_nuevo = reemplazar_una_vez(
            pag_nuevo, 'self.input_busqueda.setPlaceholderText("Buscar cliente...")',
            'self.input_busqueda.setPlaceholderText("Buscar por nombre, teléfono o documento...")',
            "texto del buscador")
        pag_nuevo = reemplazar_una_vez(
            pag_nuevo, "self.input_busqueda.setFixedWidth(240)",
            "self.input_busqueda.setFixedWidth(340)", "ancho del buscador")

        compile(serv_nuevo, str(SERVICIO), "exec")
        compile(pag_nuevo, str(PAGINA), "exec")
    except (ValueError, SyntaxError) as e:
        print(f"ALTO: {e}\nNo se modifico nada. Mandame estos dos archivos y lo reviso.")
        return 2

    for r in (SERVICIO, PAGINA):
        shutil.copy2(r, str(r) + ".bak")
    escribir(SERVICIO, serv_nuevo, crlf_serv)
    escribir(PAGINA, pag_nuevo, crlf_pag)
    print("Listo. Arreglo aplicado en:")
    print(f"  - {SERVICIO}  (copia: {SERVICIO}.bak)")
    print(f"  - {PAGINA}  (copia: {PAGINA}.bak)")
    print("Para deshacer: borra los archivos y quita el '.bak' del nombre de las copias.")
    print("Siguiente paso: python test_documento_clientes.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())