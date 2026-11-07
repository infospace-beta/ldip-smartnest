"""Minimal mutation audit metadata; never log tokens, queries or message bodies."""
import logging

logger = logging.getLogger('core.audit')


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith('/api/'):
            response['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                match = getattr(request, 'resolver_match', None)
                logger.info('mutation method=%s route=%s actor=%s status=%s', request.method,
                            getattr(match, 'route', 'unresolved'), getattr(request.user, 'pk', None), response.status_code)
        return response
