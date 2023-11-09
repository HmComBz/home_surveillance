from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User

class DimCameras(models.Model):
    user_id = models.IntegerField()
    camera_name = models.CharField(max_length=30)
    camera_model = models.CharField(max_length=30)
    x_res = models.IntegerField()
    y_res = models.IntegerField()
    rtsp_main = models.CharField(max_length=100)
    domain = models.CharField(max_length=100)
    port = models.CharField(max_length=10)
    user_name = models.CharField(max_length=30)
    password = models.CharField(max_length=256)
    web_socket = models.IntegerField()
    description = models.CharField(max_length=100)
    detection_status = models.IntegerField() # If camera is included in analysis (1 or 0)
    selected_status = models.IntegerField() # If camera is selected to be shown in webpage (1 or 0)
    detection_classes = models.CharField(max_length=6)

    def __str__(self):
        return self.camera_name
    
class DimPerson(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    account_type = models.CharField(max_length=30)
    max_cameras = models.CharField(max_length=3)
    push_token = models.CharField(max_length=30)
    push_user = models.CharField(max_length=30)
    system_status = models.IntegerField()

    def __str__(self):
        return self.user
    
class FactAlarmLog(models.Model):
    user_id = models.IntegerField()
    camera_id = models.IntegerField(db_index=True)
    log_date = models.DateTimeField(default=timezone.now)
    log_class = models.IntegerField(db_index=True)
    log_score = models.DecimalField(max_digits=6, decimal_places=3)
    log_num_img = models.IntegerField()
    log_status = models.IntegerField()
    download_status = models.IntegerField()
    download_url = models.CharField(max_length=100)
    
class FactDetections(models.Model):
    log_id = models.IntegerField(db_index=True)
    created = models.DateTimeField(default=timezone.now)
    image = models.ImageField(upload_to='detections/')

    def __str__(self):
        return self.log_id
        
