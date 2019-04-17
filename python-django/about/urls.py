"""URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
"""
from django.urls import path
from django.http import HttpResponse

source = 'https://github.com/zeit/now-examples/tree/master/python-django'
css = '<link rel="stylesheet" href="/css/style.css" />'

def index(request):
    return HttpResponse("%s<h1>About</h1><p>You are viewing a Django.</p><p>Visit the <a href='./'>home</a> page.</p>" % (css), content_type='text/html')

urlpatterns = [
    path('about', index)
]
