from django.conf import settings
from django.conf.urls import url
from django.core.exceptions import ImproperlyConfigured, ViewDoesNotExist
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.http import Http404, HttpResponseNotAllowed
from django.template import TemplateDoesNotExist
from django.views.generic import View

from .converter import ConversionTask
from .decorators import view_function, view_parameter, NotDecoratedError
from .exceptions import InternalRedirectException, RedirectException
from .signals import dmp_signal_pre_process_request, dmp_signal_post_process_request, dmp_signal_internal_redirect_exception, dmp_signal_redirect_exception
from .util import get_dmp_instance, get_dmp_app_configs, log, DMP_OPTIONS

import sys, logging, inspect
from importlib import import_module
from importlib.util import find_spec
from collections import namedtuple


##############################################################
###   The front controller of all views on the site.
###   urls.py routes everything through this method.

def route_request(request, **kwargs):
    '''
    The main router for all calls coming in to the system.  Patterns in urls.py should call this function.
    '''
    # check to ensure DMP's middleware ran
    # wrap to enable the InternalRedirectExceptions to loop around
    response = None
    while True:
        # an outer try that catches the redirect exceptions
        try:
            # ensure we have a dmp_router_callback variable on request
            if getattr(request, 'dmp_router_callback', None) is None:
                raise ImproperlyConfigured("Variable request.dmp_router_callback does not exist (check MIDDLEWARE for `django_mako_plus.RequestInitMiddleware`).")

            # output the variables so the programmer can debug where this is routing
            if log.isEnabledFor(logging.INFO):
                log.info('processing: app={}, page={}, module={}, func={}, urlparams={}'.format(request.dmp_router_app, request.dmp_router_page, request.dmp_router_module, request.dmp_router_function, request.urlparams))

            # if we had a view not found, raise a 404
            if isinstance(request.dmp_router_callback, ViewDoesNotExist) or isinstance(request.dmp_router_callback, RegistryExceptionRouter):
                log.error(request.dmp_router_callback.message(request))
                raise Http404

            # send the pre-signal
            if DMP_OPTIONS.get('SIGNALS', False):
                for receiver, ret_response in dmp_signal_pre_process_request.send(sender=sys.modules[__name__], request=request):
                    if isinstance(ret_response, (HttpResponse, StreamingHttpResponse)):
                        return ret_response

            # log the view
            if log.isEnabledFor(logging.INFO):
                log.info('calling {}'.format(request.dmp_router_callback.message(request)))

            # call view function with any args and any remaining kwargs
            response = request.dmp_router_callback.get_response(request, **kwargs)

            # send the post-signal
            if DMP_OPTIONS.get('SIGNALS', False):
                for receiver, ret_response in dmp_signal_post_process_request.send(sender=sys.modules[__name__], request=request, response=response):
                    if ret_response != None:
                        response = ret_response # sets it to the last non-None in the signal receiver chain

            # if we didn't get a correct response back, send a 404
            if not isinstance(response, (HttpResponse, StreamingHttpResponse)):
                log.error('{} failed to return an HttpResponse (or the post-signal overwrote it).  Returning Http404.'.format(request.dmp_router_callback.message(request)))
                raise Http404

            # return the response
            return response

        except InternalRedirectException as ivr:
            # send the signal
            if DMP_OPTIONS.get('SIGNALS', False):
                dmp_signal_internal_redirect_exception.send(sender=sys.modules[__name__], request=request, exc=ivr)
            # resolve to a function
            request.dmp_router_module = ivr.redirect_module
            request.dmp_router_function = ivr.redirect_function
            try:
                module = import_module(request.dmp_router_module)
                request.dmp_router_callback = getattr(module, request.dmp_router_function, None)
                if request.dmp_router_callback == None:
                    request.dmp_router_callback = ViewDoesNotExist('module {} found successfully during internal redirect, but view function {} is not defined in the module.'.format(request.dmp_router_module, request.dmp_router_function))
            except ImportError:
                request.dmp_router_callback = ViewDoesNotExist('view {}.{} not found during internal redirect.'.format(request.dmp_router_module, request.dmp_router_function))
            # do the internal redirect
            log.info('received an InternalViewRedirect to {} -> {}'.format(request.dmp_router_module, request.dmp_router_function))

        except RedirectException as e: # redirect to another page
            if request.dmp_router_class == None:
                log.error('{} redirected processing to {}.'.format(request.dmp_router_callback.message(request), e.redirect_to))
            # send the signal
            if DMP_OPTIONS.get('SIGNALS', False):
                dmp_signal_redirect_exception.send(sender=sys.modules[__name__], request=request, exc=e)
            # send the browser the redirect command
            return e.get_response(request)

    # the code should never get here
    raise Exception("Django-Mako-Plus error: The route_request() function should not have been able to get to this point.  Please notify the owner of the DMP project.  Thanks.")





########################################################################################
###   Router classes for the different types of views.  When a view is first accessed,
###   one of the "mini" routers is created for that view and cached in the registry
###   for future calls.

def router_factory(app_name, module_name, function_name, fallback_template):
    '''Factory method to create a view-specific router in the system. In production mode, these are cached in the registry.'''
    try:
        # I'm first calling find_spec first here beacuse I don't want import_module in
        # a try/except -- there are lots of reasons that importing can fail, and I just want to
        # know whether the file actually exists.  find_spec raises AttributeError if not found.
        try:
            spec = find_spec(module_name)
        except ValueError:
            spec = None
        if spec is None:
            # no view module, can we call the template directly?
            try:
                return TemplateViewRouter(app_name, fallback_template)
            except TemplateDoesNotExist as e:
                raise ViewDoesNotExist('View module {} not found, and fallback template {} could not be loaded ({})'.format(module_name, fallback_template, e))

        # get the function from the module
        module = import_module(module_name)
        try:
            func = getattr(module, function_name)
        except AttributeError:
            raise ViewDoesNotExist('Module {} found successfully, but view {} is not defined in the module.'.format(module_name, function_name))

        # class-based view?
        try:
            decorator_args, decorator_kwargs = view_function.get_args(func)[0]
        except NotDecoratedError:
            decorator_args, decorator_kwargs = None, None
        if inspect.isclass(func) and issubclass(func, View):
            return ClassBasedRouter(module, func(), decorator_kwargs)  # func() because func is class (not instance)

        # it's a view function
        # ensure it was  @view_function, it will have kwargs cached on it.
        if not view_function.is_decorated(func):
            raise ViewDoesNotExist("View {}.{} was found successfully, but it must be decorated with @view_function or be a subclass of django.views.generic.View.".format(module_name, function_name))
        return ViewFunctionRouter(module, func, decorator_kwargs)

    except ViewDoesNotExist as vdne:
        return RegistryExceptionRouter(vdne)


class ViewFunctionRouter(object):
    '''Router for view functions and class-based methods'''
    def __init__(self, mod, func, decorator_kwargs):
        self.module = mod
        self.function = func
        self.decorator_kwargs = decorator_kwargs
        param_types = getattr(func, '__annotations__', {}) # not using typing.get_type_hints because it adds Optional() to None defaults, and we don't need to follow mro here
        params = []
        for i, p in enumerate(inspect.signature(func).parameters.values()):
            if i > 0:  # skip the request object
                vp = ViewParameter(
                    name=p.name,
                    type=param_types.get(p.name, inspect.Parameter.empty),
                    default=p.default,
                )
                view_parameter.update(func, vp)  # update from @view_parameter args, if there is one
                params.append(vp)
        self.parameters = tuple(params)

    def get_response(self, request, **kwargs):
        # build the args list from request.urlparams (kwargs are any extra named groups in the matched url pattern)
        request.urlparams.check_length(len(self.parameters))
        ctask = ConversionTask(request, self.decorator_kwargs, self.module, self.function)
        args = [ request ]
        for i, parameter in enumerate(self.parameters):
            value = kwargs.pop(parameter.name, request.urlparams[i]) # popping kwargs so we don't have the same param in args and kwargs
            # converter function should catch conversion errors and raise someting more useful like Http404 or RedirectException
            if parameter.converter is not None:
                value = parameter.converter(value, parameter, ctask)  # specified converter for this parameter
            else:
                value = ctask.converter(value, parameter, ctask)      # converter for view function (specified or defaulted)
            args.append(value)
        # here we go! finally, call the view function!
        return self.function(*args, **kwargs)

    def message(self, request):
        return 'view function {}.{}'.format(request.dmp_router_module, request.dmp_router_function)


class ClassBasedRouter(object):
    '''Router for class-based views.'''
    def __init__(self, module, instance, decorator_kwargs):
        self.endpoints = {}
        for mthd_name in instance.http_method_names:  # get parameters from the first http-based method (get, post, etc.)
            func = getattr(instance, mthd_name, None)
            if func is not None:
                self.endpoints[mthd_name] = ViewFunctionRouter(module, func, decorator_kwargs)

    def get_response(self, request, **kwargs):
        endpoint = self.endpoints.get(request.method.lower())
        if endpoint is not None:
            return endpoint.get_response(request, **kwargs)
        log.warning('Method Not Allowed (%s): %s', request.method, request.path, extra={'status_code': 405, 'request': request})
        return HttpResponseNotAllowed([ e.upper() for e in self.endpoints.keys() ])

    def message(self, request):
        return 'class-based view function {}.{}.{}'.format(request.dmp_router_module, request.dmp_router_class, request.dmp_router_function)


class TemplateViewRouter(object):
    '''Router for direct templates (used whe a view.py file doesn't exist but the .html does)'''
    def __init__(self, app_name, template_name):
        # not keeping the actual template objects because we need to get from the loader each time (Mako has its own cache)
        self.app_name = app_name
        self.template_name = template_name
        # check the template by loading it
        get_dmp_instance().get_template_loader(self.app_name).get_template(self.template_name)

    def get_response(self, request, **kwargs):
        template = get_dmp_instance().get_template_loader(self.app_name).get_template(self.template_name)
        return template.render_to_response(request=request, context=kwargs)

    def message(self, request):
        return 'template {} (view function {}.{} not found)'.format(self.template_name, request.dmp_router_module, request.dmp_router_function)


class RegistryExceptionRouter(object):
    '''Router for a registry exception (i.e. view not found).'''
    def __init__(self, exc):
        self.exc = exc

    def get_response(self, request, **kwargs):
        return HttpResponseNotFound(str(self.exc))

    def message(self, request):
        return str(self.exc)



###########################
###  ConversionTask

class ViewParameter(object):
    '''
    A data class that represents a view parameter on a view function.
    An instance of this class is created for each parameter in a view function
    (except the initial request object argument).
    '''
    def __init__(self, name, type=None, default=None, converter=None):
        '''
        name:      The name of the parameter.
        type:      The expected type of this parameter.  Converters use this type to
                   convert urlparam strings to the right type.
        default:   Any default value, specified in function type hints.  If no default is
                   specified in the function, this is `inspect.Parameter.empty`.
        converter: A callable to convert this parameter.  If set, this overrides the
                   normal coverter for this type.
        '''
        self.name = name
        self.type = type
        self.default = default
        self.converter = converter

    def __str__(self):
        return 'ViewParameter: name={}, type={}, default={}, converter={}'.format(
            self.name,
            self.type.__qualname__ if self.type is not None else '<not specified>',
            self.default,
            self.converter,
        )


