from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import Sum
from django.contrib.auth.decorators import login_required
from .models import DimCameras, DimPerson


@login_required
def main(request):
    # Current user
    current_user = request.user.id

    # Import camera list
    selected_camera = 0
    data = []
    system_status = DimPerson.objects.get(user_id=current_user).system_status
    cameras = DimCameras.objects.filter(user_id=current_user)
    for camera in cameras:
        temp_dict = {"id":camera.id, "user_id":camera.user_id, "camera_name":camera.camera_name,
                     "detection_status":camera.detection_status, "selected_status":camera.selected_status}
        data.append(temp_dict)
        if camera.selected_status == 1:
            selected_camera = str(camera.id)
    return render(request, "home.html", {"selected_camera":selected_camera, "system_status":system_status, "data":data})

@login_required
def history(request, view):
    return render(request, "history.html", {"view":view})

def about(request):
    return render(request, "about.html")
