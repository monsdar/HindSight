from django.contrib import admin
from django.urls import include, path

from .views import health

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('hooptipp.predictions.urls', namespace='predictions')),
    path('health/', health, name='health'),
]
