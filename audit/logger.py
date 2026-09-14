from audit.models import *

def log_event(event_type, agent=None, spend_request=None, payload=None):
    return AuditEvent.objects.create(
        event_type=event_type,
        agent=agent,
        spend_request=spend_request,
        payload=payload or {}
    )