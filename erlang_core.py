import math
from scipy.optimize import root_scalar

def erlang_c_probability(a, m):
    """
    Calcula la probabilidad de que una llamada espere (Erlang C).
    a: Carga de tráfico (Erlangs)
    m: Número de agentes
    """
    if m <= a:
        return 1.0
    
    # Sumatoria para el denominador
    sum_terms = sum((a ** k) / math.factorial(k) for k in range(int(m)))
    last_term = (a ** m) / (math.factorial(int(m)) * (1 - (a / m)))
    
    intensity = last_term / (sum_terms + last_term)
    return max(0.0, min(1.0, intensity))

def calculate_service_level(a, m, aht, target_time):
    """Calcula el Nivel de Servicio (SLA) esperado."""
    if m <= a:
        return 0.0
    pw = erlang_c_probability(a, m)
    sla = 1.0 - (pw * math.exp(-(m - a) * (target_time / aht)))
    return max(0.0, min(1.0, sla))

def calculate_required_agents(calls, interval_minutes, aht, target_sla, target_time, max_occupancy=0.85):
    """
    Calcula los agentes netos requeridos para una franja.
    """
    if calls <= 0 or aht <= 0:
        return 0, 0.0, 0.0
    
    interval_seconds = interval_minutes * 60
    # Carga de tráfico en Erlangs (A = λ * AHT / T)
    a = (calls * aht) / interval_seconds
    
    # Agentes mínimos necesarios por tráfico
    m = math.ceil(a) + 1
    
    # Incrementar agentes hasta cumplir SLA y límite de ocupación
    while True:
        occupancy = a / m
        sla = calculate_service_level(a, m, aht, target_time)
        
        if sla >= target_sla and occupancy <= max_occupancy:
            break
        m += 1
        
    return m, sla, occupancy
