"""
Lógica de cálculo de costos.

Estrategia elegida: Costo Promedio Ponderado (CPP).

    nuevo_costo_promedio = (stock_actual * costo_promedio_actual + cantidad_comprada * costo_compra)
                            / (stock_actual + cantidad_comprada)

Este valor se guarda en productos.costo_promedio_actual y se usa como
"costo vigente" al momento de vender. Cada venta congela ese costo en
venta_detalle.costo_unitario_snapshot para que la utilidad histórica
nunca cambie retroactivamente.
"""


def calcular_costo_promedio_ponderado(
    stock_actual: float,
    costo_promedio_actual: float,
    cantidad_comprada: float,
    costo_compra_unitario: float,
) -> float:
    if cantidad_comprada <= 0:
        raise ValueError("La cantidad comprada debe ser mayor a cero.")

    nuevo_stock_total = stock_actual + cantidad_comprada
    if nuevo_stock_total <= 0:
        return costo_compra_unitario

    valor_inventario_actual = stock_actual * costo_promedio_actual
    valor_compra = cantidad_comprada * costo_compra_unitario

    nuevo_costo = (valor_inventario_actual + valor_compra) / nuevo_stock_total
    return round(nuevo_costo, 4)
