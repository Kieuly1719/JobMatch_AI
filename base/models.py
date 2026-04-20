from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
from .utils import clean_text
class CustomerUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email là bắt buộc")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser phải có is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser phải có is_superuser=True.')

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser phải có is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser phải có is_superuser=True.')

        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    username = None 
    email = models.EmailField(unique=True, verbose_name="Địa chỉ Email")

    ROLE_CHOICES = (
        ('candidate', 'Ứng viên'),
        ('recruiter', 'Nhà tuyên dụng'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='candidate')
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomerUserManager()
    def __str__(self):
        return self.email
    
class CompanyProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='company_profile')
    name = models.CharField(max_length=255, verbose_name="Tên công ty")
    website = models.URLField(blank=True, null=True)
    address = models.CharField(max_length=255, verbose_name="Địa chỉ công ty")
    logo = models.ImageField(upload_to='company_logos/', blank=True, null=True)
    description = models.TextField(verbose_name="Giới thiệu công ty")

    def __str__(self):
        return self.name
    
class CandidateProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='candidate_profile')
    full_name = models.CharField(max_length=255)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    phone_number = models.CharField(max_length=20)
    address = models.CharField(max_length=255, verbose_name="Địa chỉ")

    GENDER_CHOICES = (('Male', 'Nam'), ('Female', 'Nữ'), ('Other', 'Khác'))
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default='Male')

    LEVEL_CHOICES = ((1, 'Trung cấp'), (2, 'Cao đẳng'), (3, 'Đại học'), (4, 'Sau đại học'))
    level = models.IntegerField(choices=LEVEL_CHOICES, default=3, verbose_name="Trình độ học vấn")

    skills = models.TextField(verbose_name="Kỹ năng")
    cv_file = models.FileField(upload_to='cvs/')
    cv_extracted_text = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.full_name
    
class JobPost(models.Model):
    recruiter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='job_posts', null=True, blank=True)

    company_name = models.CharField(max_length=200)
    title = models.TextField(max_length=200, verbose_name="Tiêu đề công việc")
    description = models.TextField(verbose_name="Mô tả công việc")
    requirements = models.TextField(verbose_name="Yêu cầu công việc")
    salary_range = models.CharField(max_length=100, null=True, blank=True)
    location = models.CharField(max_length=255, verbose_name="Địa điểm làm việc")
    deadline = models.DateField(null = True, blank = True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    interview_count = models.IntegerField(default=0, verbose_name="Số lượng đã nộp hồ sơ")
    full_text_search = models.TextField(blank=True, null=True)
    cleaned_data = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):
        raw_text = f"{self.title} {self.description} {self.requirements}"
        self.cleaned_data = clean_text(raw_text) # Gọi hàm của bạn ở đây
        self.full_text_search = f"{self.title} {self.description} {self.requirements}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
    
class Application(models.Model):
    STATUS_CHOICES = (('pending', 'Đang chờ'), ('accepted', 'Mời phỏng vấn'), ('rejected', 'Từ chối'))
    job = models.ForeignKey(JobPost, on_delete=models.CASCADE, related_name='applications')
    candidate = models.ForeignKey(User, on_delete=models.CASCADE, related_name='my_applications')
    applied_at = models.DateTimeField(auto_now_add=True)
    cv_snapshot = models.FileField(upload_to='application_cvs/')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    class Meta:
        unique_together = ('job', 'candidate')

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    link = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return f"Notif for {self.user.username}: {self.message}"