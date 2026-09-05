"""Ajoute les en-têtes CORS sur /media/ (souvent servi hors API)."""
from __future__ import annotations

from django.http import HttpResponse


class MediaCorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ''
        if path.startswith('/media/') and request.method == 'OPTIONS':
            response = HttpResponse(status=204)
            self._apply_cors(response)
            return response

        response = self.get_response(request)
        if path.startswith('/media/'):
            self._apply_cors(response)
        return response

    @staticmethod
    def _apply_cors(response) -> None:
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type'
        response['Cross-Origin-Resource-Policy'] = 'cross-origin'
        response['Access-Control-Max-Age'] = '86400'
