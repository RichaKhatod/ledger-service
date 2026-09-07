from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from agents.models import Agent
from agents.utils import hash_key

class AgentAPIKeyAuth(BaseAuthentication):
    def authenticate(self, request):
        # get the header
        raw_key = request.headers.get("X-Agent-Key")

        # no header = skip this auth backend
        if not raw_key:
            return None

        # hash the key, look up the agent
        api_hash_key = hash_key(raw_key)
        try:
            agent = Agent.objects.get(api_key_hash=api_hash_key)
        except Agent.DoesNotExist:
            raise AuthenticationFailed("Invalid agent API key")
        
        # if agent not active, raise AuthenticationFailed("Agent is frozen")
        if agent.is_active == False:
            raise AuthenticationFailed("Agent is frozen")
        
        # set request.agent = agent
        request.agent = agent
        
        # return (None, agent)  — DRF expects a (user, auth) tuple
        return (None, agent)
        