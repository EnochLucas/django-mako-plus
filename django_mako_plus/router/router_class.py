from django.http import HttpResponseNotAllowed
from ..util import log
from .base import Router
from .router_function import ViewFunctionRouter





class ClassBasedRouter(Router):
    '''Router for class-based views.'''
    def __init__(self, module, instance, decorator_kwargs):
        self.instance = instance
        self.endpoints = {}
        for mthd_name in instance.http_method_names:  # get parameters from the first http-based method (get, post, etc.)
            func = getattr(instance, mthd_name, None)
            if func is not None:
                self.endpoints[mthd_name] = ViewFunctionRouter(module, func, decorator_kwargs)


    def get_response(self, request, *args, **kwargs):
        endpoint = self.endpoints.get(request.method.lower())
        if endpoint is not None:
            return endpoint.get_response(request, **kwargs)
        log.info('Method Not Allowed (%s): %s', request.method, request.path, extra={'status_code': 405, 'request': request})
        return HttpResponseNotAllowed([ e.upper() for e in self.endpoints.keys() ])


    @property
    def name(self):
        return self.instance.__class__.__qualname__


    def message(self, request, descriptive=True):
        if descriptive:
            return 'class-based view function {}.{}.{}'.format(request.dmp.module, self.name, request.dmp.function)
        return '{}.{}.{}'.format(request.dmp.module, self.name, request.dmp.function)