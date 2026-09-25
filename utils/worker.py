"""
Worker genérico para sacar tareas pesadas (consultas SQL, reportes, etc.)
del hilo principal de la interfaz.

Uso típico en una página:

    from utils.worker import Worker

    def _buscar_productos(self) -> None:
        texto = self.input_busqueda_producto.text()
        worker = Worker(self.producto_service.listar, texto)
        worker.signals.finished.connect(self._on_productos_listos)
        worker.signals.error.connect(self._on_error_busqueda)
        QThreadPool.globalInstance().start(worker)

    def _on_productos_listos(self, productos) -> None:
        # Esto SIEMPRE corre en el hilo principal (la señal lo garantiza),
        # así que aquí sí se puede tocar la UI sin problema.
        ...

No hay que crear un QThread por pantalla: basta con QThreadPool.globalInstance(),
que ya viene con Qt y reutiliza un pool de hilos para toda la app.

Importante: la función que se le pasa al Worker (ej. producto_service.listar)
NO debe tocar ningún widget de Qt, solo hacer la consulta y devolver datos.
Toda actualización de la UI se hace en el slot conectado a `finished`,
porque Qt no es thread-safe para widgets.
"""

import traceback

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

# QThreadPool.start() transfiere la propiedad del Worker a C++, que lo
# destruye automáticamente al terminar run() (autoDelete=True). Si nada en
# Python retiene una referencia al Worker (o a su `signals`), el recolector
# de basura puede destruir el WorkerSignals ANTES de que la señal
# finished/error -emitida desde el hilo en segundo plano- llegue a
# procesarse en el hilo principal, perdiendo el resultado en silencio.
# Por eso se guarda aquí una referencia fuerte a cada worker activo.
_workers_activos: set["Worker"] = set()


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)


class Worker(QRunnable):

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        _workers_activos.add(self)
        self.signals.finished.connect(lambda *_: _workers_activos.discard(self))
        self.signals.error.connect(lambda *_: _workers_activos.discard(self))

    @Slot()
    def run(self) -> None:
        try:
            resultado = self.fn(*self.args, **self.kwargs)
        except Exception:
            self.signals.error.emit(traceback.format_exc())
        else:
            self.signals.finished.emit(resultado)