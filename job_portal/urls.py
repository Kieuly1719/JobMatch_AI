from django.contrib import admin
from django.urls import path, include

from job_portal import settings
from django.conf.urls.static import static
urlpatterns = [
    path('admin/', admin.site.urls),

    path('', include('base.urls')),
]

if settings.DEBUG:
    urlpatterns != static(settings.MEDIA_URL, document_root = settings.MEDIA_ROOT),