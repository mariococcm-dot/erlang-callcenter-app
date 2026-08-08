import math

def calculate_shift_requirements(max_fte_peak, total_fte_hours_day, shrinkage_pct=0.20):
    """
    Calcula el requerimiento de agentes reales (Headcount) según el tipo de jornada y días de descanso.
    
    Parámetros:
    - max_fte_peak: Pico máximo de FTEs simultáneos en el día.
    - total_fte_hours_day: Total de horas-hombre requeridas en todo el día (suma de FTEs por intervalo * duración en horas).
    - shrinkage_pct: Porcentaje de merma / ausentismo / pausas.
    """
    
    # Horas productivas totales ajustadas por shrinkage
    gross_fte_hours = total_fte_hours_day / (1 - shrinkage_pct) if shrinkage_pct < 1 else total_fte_hours_day

    # Definición de Esquemas de Trabajo
    shifts_info = {
        "6.5h (1 día descanso)": {
            "work_hours_per_day": 6.5,
            "days_worked_week": 6,
            "net_daily_productive_hours": 6.0,  # Considerando 30 min de pausas/comida
        },
        "8.0h (1 día descanso)": {
            "work_hours_per_day": 8.0,
            "days_worked_week": 6,
            "net_daily_productive_hours": 7.0,  # Considerando 1h de comida/pausas
        },
        "9.0h (2 días descanso)": {
            "work_hours_per_day": 9.0,
            "days_worked_week": 5,
            "net_daily_productive_hours": 8.0,  # Considerando 1h de comida/pausas
        }
    }
    
    shift_results = {}
    
    for shift_name, config in shifts_info.items():
        # 1. Agentes requeridos para cubrir el pico del día (Cobertura de Capacidad)
        headcount_peak = math.ceil((max_fte_peak / (1 - shrinkage_pct)))
        
        # 2. Agentes requeridos por volumen de horas totales
        daily_agents_needed = gross_fte_hours / config["net_daily_productive_hours"]
        
        # 3. Factor por días de descanso (Rotación semanal)
        # 7 días de operación / días trabajados
        rest_factor = 7.0 / config["days_worked_week"]
        total_headcount_weekly = math.ceil(daily_agents_needed * rest_factor)
        
        # El headcount final debe cumplir tanto el volumen total semanal como la capacidad en hora pico
        final_headcount = max(headcount_peak, total_headcount_weekly)
        
        shift_results[shift_name] = {
            "Jornada Diaria": f"{config['work_hours_per_day']} hrs",
            "Días Laborales / Sem": config["days_worked_week"],
            "Agentes en Turno (Pico)": headcount_peak,
            "Plantilla Total Necesaria (Headcount)": final_headcount
        }
        
    return shift_results
