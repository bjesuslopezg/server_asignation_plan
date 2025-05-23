#!/usr/bin/env python3
"""
Bin‑packing de servicios a servidores físicos (capacidades ya efectivas)

Uso:
    python bin_packing_script.py servicios.csv \
        --cores 10 --ram 21 --net 760 --disk-io 380 --storage 1520 \
        --seed 1

    python script.py services.csv \
        --cores 10.68 --ram 21.28 --net 760 --disk-io 380 --storage 1520
        
Argumentos:
    servicios.csv   CSV con las columnas:
        Servicios, Cantidad, USO CPU (%), E/S Red (Mbs), E/S disco (MB/s),
        Uso Disco (GB), Memoria (GB)

Salidas:
    1. Tabla resumen por servidor en stdout.
    2. Fichero JSON "plan_asignacion.json" con la estructura completa.
"""
import argparse, json, sys, random, pathlib
from typing import Dict, List

try:
    import pandas as pd
except ImportError:
    sys.exit("Este script requiere pandas. Instálalo con: pip install pandas")

# --------------------------------------------------
# Parsing de argumentos
# --------------------------------------------------
def get_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bin‑packing de servicios (capacidades efectivas)")
    p.add_argument("csv", help="Ruta al CSV de servicios")
    p.add_argument("--cores", type=float, required=True, help="Cores efectivos por servidor")
    p.add_argument("--ram", type=float, required=True, help="Memoria efectiva por servidor (GB)")
    p.add_argument("--net", type=float, required=True, help="Ancho de banda efectivo (Mbps)")
    p.add_argument("--disk-io", type=float, required=True, help="I/O disco efectivo (MB/s)")
    p.add_argument("--storage", type=float, required=True, help="Almacenamiento efectivo (GB)")
    p.add_argument("--seed", type=int, default=1, help="Semilla aleatoria para reproducibilidad")
    return p.parse_args()

RESOURCE_KEYS = ["CPU", "Memoria", "Red", "Disco_IO", "Almacenamiento"]

# --------------------------------------------------
# Bin‑packing First‑Fit Decreasing con anti‑afinidad
# -------------------------------------------------
def can_host(server: Dict, inst: Dict, caps: Dict[str, float]) -> bool:
    if inst["Servicio"] in server["services"]:
        return False  # anti-afinidad
    for k in RESOURCE_KEYS:
        if server[k] + inst[k] > caps[k]:
            return False
    return True


def first_fit_decreasing(instances: List[Dict], caps: Dict[str, float]):
    instances_sorted = sorted(instances, key=lambda x: (x["CPU"], x["Red"],  x["Memoria"]), reverse=True)
    servers = []
    for inst in instances_sorted:
        placed = False
        for s in servers:
            if can_host(s, inst, caps):
                for k in RESOURCE_KEYS:
                    s[k] += inst[k]
                s["services"].add(inst["Servicio"])
                s["instances"].append(inst)
                placed = True
                break
        if not placed:
            servers.append({
                "name": f"S{len(servers)+1}",
                **{k: inst[k] for k in RESOURCE_KEYS},
                "services": set([inst["Servicio"]]),
                "instances": [inst]
            })
    return servers

# --------------------------------------------------
# Carga CSV y expansión de instancias
# --------------------------------------------------
def load_instances(path: pathlib.Path) -> List[Dict]:
    df = pd.read_csv(path, sep=',')

    df["Cantidad"] = df["Cantidad"].astype(int)
    df["E/S disco (MB/s)"] = pd.to_numeric(df["E/S disco (MB/s)"], errors="raise")

    instances = []
    for _, row in df.iterrows():
        for _ in range(row["Cantidad"]):
            instances.append({
                "Servicio": row["Servicios"],
                "CPU": row["USO CPU (%)"] / 100.0,           # núcleos-equivalentes
                "Memoria": row["Memoria (GB)"],
                "Red": row["E/S Red (Mbs)"],
                "Disco_IO": row["E/S disco (MB/s)"],
                "Almacenamiento": row["Uso Disco (GB)"]
            })
    return instances

# --------------------------------------------------
# Pretty print y main
# --------------------------------------------------
def print_summary(servers: List[Dict], caps: Dict[str, float]):
    print("\n=== Plan de asignación ===\n")
    for s in servers:
        print(f"{s['name']}: {', '.join(sorted(s['services']))}")
        for k in RESOURCE_KEYS:
            pct = (s[k] / caps[k]) * 100
            print(f"  {k:13}: {s[k]:8.2f} / {caps[k]:.2f}  ({pct:5.1f}% usado)")
        print()
    print(f"Total servidores: {len(servers)}")


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
    servers = first_fit_decreasing(instances, caps)

    print_summary(servers, caps)

    plan = [{**{k: s[k] for k in RESOURCE_KEYS}, "name": s["name"], "services": sorted(s["services"])} for s in servers]
    with open("plan_asignacion.json", "w", encoding="utf-8") as f:
        json.dump({"capacity": caps, "servers": plan}, f, indent=2)
    print("\nSe creó el fichero plan_asignacion.json con el detalle completo.")


if __name__ == "__main__":
    main()