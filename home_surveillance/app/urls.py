from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from app import stream_camera

urlpatterns = [
    path('', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path("main", views.main, name="main"),
    path("history/<view>/", views.history, name="history"),
    path("about", views.about, name="about"),

    # Select camera
    path('camera/<camera_id>/', stream_camera.camera, name='camera'),
    path('view_camera/<camera_id>/', stream_camera.view_camera, name='view_camera'),
    path('manage_system/<task>/', stream_camera.manage_system, name="manage_system")
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)