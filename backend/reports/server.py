import psutil
from backend.agent import worker_pool

def get_server_status():
    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.1)
    swap = psutil.swap_memory()
    disk = psutil.disk_usage('/')
    return {
        "ram_percent": mem.percent,
        "ram_used_gb": round(mem.used / (1024**3), 2),
        "ram_total_gb": round(mem.total / (1024**3), 2),
        "cpu_percent": cpu,
        "swap_percent": swap.percent,
        "disk_percent": disk.percent,
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "worker_slots_active": sum(1 for s in worker_pool.slots if s is not None),
        "worker_slots_max": worker_pool.max_slots,
        "agent_running": worker_pool.running
    }
