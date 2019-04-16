import os

from django.core.wsgi import get_wsgi_application
#from django.conf import settings
#import settings as myapp_defaults
#settings.configure(myapp_defaults)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')

app = get_wsgi_application()
