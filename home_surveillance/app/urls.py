from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views


urlpatterns = [
    path('', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path("main", views.main, name="main"),
    path("history/<view>/", views.history, name="history"),
    path("about", views.about, name="about"),

    # Select camera
    path('camera/<camera_id>/', views.camera, name='camera'),
    path('include_camera/<camera_id>/', views.include_camera, name='include_camera'),
    path('exclude_camera/<camera_id>/', views.exclude_camera, name='exclude_camera'),
    path('view_camera/<camera_id>/', views.view_camera, name='view_camera'),
    path('manage_system/<task>/', views.manage_system, name="manage_system")
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
