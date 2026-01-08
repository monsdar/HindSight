from django.urls import path

from . import views

app_name = 'predictions'

urlpatterns = [
    path('', views.home, name='home'),
    path('api/save-prediction/', views.save_prediction, name='save_prediction'),
    path('api/toggle-lock/', views.toggle_lock, name='toggle_lock'),
    path('api/lock-summary/', views.get_lock_summary, name='lock_summary'),
    path('api/impressum/', views.get_impressum, name='impressum_api'),
    path('api/datenschutz/', views.get_datenschutz, name='datenschutz_api'),
    path('api/teilnahmebedingungen/', views.get_teilnahmebedingungen, name='teilnahmebedingungen_api'),
    path('api/give-kudos/', views.give_kudos_view, name='give_kudos'),
    path('api/enroll-in-season/', views.enroll_in_season, name='enroll_in_season'),
    path('disable-reminders/<str:uidb64>/<str:token>/', views.disable_reminder_emails, name='disable_reminders'),
    path('enroll-season/<str:uidb64>/<int:season_id>/<str:token>/', views.enroll_in_season_via_token, name='enroll_season_via_token'),
]
