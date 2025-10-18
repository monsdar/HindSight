from django.urls import path

from . import views

app_name = 'predictions'

urlpatterns = [
    path('', views.home, name='home'),
]
