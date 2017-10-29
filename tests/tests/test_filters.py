from django.apps import apps
from django.http import HttpResponse
from django.template import TemplateDoesNotExist
from django.test import TestCase

from django_mako_plus.util import log
from django_mako_plus.filters import django_syntax
from django_mako_plus import render_template

import logging, os, os.path



class Tester(TestCase):

    def test_filters(self):
        html = render_template(None, 'tests', 'filters.html', {
            'django_var': '::django::',
            'jinja2_var': '~~jinja2~~',
        })
        self.assertTrue('::django::' in html)
        self.assertTrue('~~jinja2~~' in html)