from audit.models import AnomalyAlert


def get_anomaly_alerts_util(agent_id=None):
    anomaly_alerts = AnomalyAlert.objects.all()
    if agent_id:
        anomaly_alerts = anomaly_alerts.filter(agent_id=agent_id)
        
    data = list(anomaly_alerts.values("id", "agent_id", "alert_type", "details", "resolved", "created_at")[:50])
    
    return ("anomalies fetched successfully", data, 200)