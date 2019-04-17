"""URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
"""
from django.urls import path
from django.http import HttpResponse

source = 'https://github.com/zeit/now-examples/tree/master/python-django'
css = '<link rel="stylesheet" href="/css/style.css" />'

def index(request):
    return HttpResponse("%s<h1>Django on Now 2.0</h1><p>You are viewing a Django application written in Python running on Now 2.0.</p><p>Visit the <a href='./about'>about</a> page or view the <a href='%s'>source code</a>.</p>" % (css, source), content_type='text/html')

urlpatterns = [
    path('', index)
]
