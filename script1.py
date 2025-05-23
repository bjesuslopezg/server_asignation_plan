#!/usr/bin/env python3
"""
Bin‑packing de servicios a servidores físicos ─ versión optimizada
=================================================================

Objetivo: **minimizar el número de servidores** usando al máximo cada
capacidad efectiva, sin violar anti‑afinidad (una réplica por host).

Cambios vs versión anterior
---------------------------
1. **Ordenamiento dinámico** de instancias:
   * Se calcula la *criticidad* de cada recurso = demanda total / capacidad
     por servidor.
   * Los recursos se ordenan de mayor a menor criticidad; esa lista se usa
     como clave primaria para *First‑Fit Decreasing*.
2. **Empate inteligente**: si dos planes usan el mismo nº de hosts, se elige
   el que deja **menos capacidad libre total**.
3. Todas las métricas se manejan como *float* para soportar fracciones de
   core o GB.

Uso
---
```bash
python bin_packing_script.py servicios.csv \
       --cores 10.68 --ram 21.28 --net 760 --disk-io 380 --storage 1520 \
       --seed 42
```

CSV requerido
-------------
```
Servicios,Cantidad,USO CPU (%),E/S Red (Mbs),E/S disco (MB/s),Uso Disco (GB),Memoria (GB)
```

Salidas
-------
* Tabla en stdout.
* `plan_asignacion.json` con el desglose completo.
"""
import argparse, json, sys, random, pathlib
from typing import Dict, List
import itertools, math
import pandas as pd

RESOURCE_KEYS = ["CPU", "Memoria", "Red", "Disco_IO", "Almacenamiento"]

# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def get_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bin‑packing con orden dinámico")
    p.add_argument("csv", help="Ruta al CSV de servicios")
    p.add_argument("--cores", type=float, required=True)
    p.add_argument("--ram", type=float, required=True)
    p.add_argument("--net", type=float, required=True)
    p.add_argument("--disk-io", type=float, required=True)
    p.add_argument("--storage", type=float, required=True)
    p.add_argument("--seed", type=int, default=1)
    return p.parse_args()

# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------

def can_host(server: Dict, inst: Dict, caps: Dict[str, float]) -> bool:
    if inst["Servicio"] in server["services"]:
        return False
    return all(server[k] + inst[k] <= caps[k] for k in RESOURCE_KEYS)


def ffd(instances: List[Dict], caps: Dict[str, float], crit_order: List[str]):
    """First‑Fit Decreasing usando el orden de criticidad dado."""
    instances_sorted = sorted(
        instances,
        key=lambda x: tuple(x[r] / caps[r] for r in crit_order),
        reverse=True,
    )
    servers: List[Dict] = []
    for inst in instances_sorted:
        for s in servers:
            if can_host(s, inst, caps):
                for k in RESOURCE_KEYS:
                    s[k] += inst[k]
                s["services"].add(inst["Servicio"])
                s["instances"].append(inst)
                break
        else:  # no ha cabido → crear servidor nuevo
            servers.append({
                "name": f"S{len(servers)+1}",
                **{k: inst[k] for k in RESOURCE_KEYS},
                "services": {inst["Servicio"]},
                "instances": [inst],
            })
    return servers

# ---------------------------------------------------------------------
# Carga CSV
# ---------------------------------------------------------------------
def load_instances(path: pathlib.Path) -> List[Dict]:
    df = pd.read_csv(path)
    numeric_cols = [
        "USO CPU (%)", "Memoria (GB)", "E/S Red (Mbs)", "E/S disco (MB/s)", "Uso Disco (GB)", "Cantidad",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="raise")
    instances: List[Dict] = []
    for _, row in df.iterrows():
        for _ in range(int(row["Cantidad"])):
            instances.append({
                "Servicio": row["Servicios"],
                "CPU": float(row["USO CPU (%)"]) / 100.0,
                "Memoria": float(row["Memoria (GB)"]),
                "Red": float(row["E/S Red (Mbs)"]),
                "Disco_IO": float(row["E/S disco (MB/s)"]),
                "Almacenamiento": float(row["Uso Disco (GB)"]),
            })
    return instances

# ---------------------------------------------------------------------
# Planificador global: prueba varios órdenes y elige el mejor
# ---------------------------------------------------------------------

def best_plan(instances: List[Dict], caps: Dict[str, float]):
    # 1. Calcular demanda total por recurso
    demand = {k: sum(inst[k] for inst in instances) for k in RESOURCE_KEYS}
    criticity = {k: demand[k] / caps[k] for k in RESOURCE_KEYS}
    crit_order = sorted(criticity, key=criticity.get, reverse=True)

    # 2. Probar con (a) orden crítico y (b) permutaciones aleatorias cortas
    best = None
    for order in [crit_order] + random.sample(list(itertools.permutations(RESOURCE_KEYS)), k=min(100, math.factorial(len(RESOURCE_KEYS)))):
        plan = ffd(instances, caps, list(order))
        if best is None or len(plan) < len(best):
            best = plan
        elif len(plan) == len(best):
            # desempate: menor capacidad sobrante total
            spare_best = sum(caps[k] - sum(s[k] for s in best) for k in RESOURCE_KEYS)
            spare_now = sum(caps[k] - sum(s[k] for s in plan) for k in RESOURCE_KEYS)
            if spare_now < spare_best:
                best = plan
    return best

# ---------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------

def print_summary(servers: List[Dict], caps: Dict[str, float]):
    print("\n=== PLAN DE ASIGNACIÓN ===\n")
    for s in servers:
        print(f"{s['name']}: {', '.join(sorted(s['services']))}")
        for k in RESOURCE_KEYS:
            pct = 100 * s[k] / caps[k]
            print(f"  {k:13}: {s[k]:8.2f} / {caps[k]:.2f}  ({pct:5.1f}% usado)")
        print()
    print(f"Total servidores: {len(servers)}")

# ---------------------------------------------------------------------
# main
# ---------------------------------------------------------------------

def main():
    args = get_cli()
    random.seed(args.seed)
    caps = {
        "CPU": args.cores,
        "Memoria": args.ram,
        "Red": args.net,
        "Disco_IO": args.disk_io,
        "Almacenamiento": args.storage,
    }
    instances = load_instances(args.csv)
    plan = best_plan(instances, caps)
    print_summary(plan, caps)

    # JSON de salida
    out = [{"name": s["name"], "services": sorted(s["services"]), **{k: s[k] for k in RESOURCE_KEYS}} for s in plan]
    with open("plan_asignacion.json", "w", encoding="utf-8") as f:
        json.dump({"capacity": caps, "servers": out}, f, indent=2)
    print("\nSe creó plan_asignacion.json con el detalle completo.")

if __name__ == "__main__":
    main()
