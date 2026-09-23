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


class WorkerSignals(QObject):
    """Señales que puede emitir un Worker.

    QRunnable no puede emitir señales directamente (no hereda de QObject),
    por eso las señales viven en un QObject aparte que el Worker sostiene.
    """
    finished = Signal(object)   # resultado de la función, ya en el hilo principal
    error = Signal(str)         # mensaje de error, ya en el hilo principal


class Worker(QRunnable):
    """Ejecuta `fn(*args, **kwargs)` en un hilo del pool y reporta el
    resultado (o el error) de vuelta al hilo principal vía señales."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            resultado = self.fn(*self.args, **self.kwargs)
        except Exception:
            self.signals.error.emit(traceback.format_exc())
        else:
            self.signals.finished.emit(resultado)