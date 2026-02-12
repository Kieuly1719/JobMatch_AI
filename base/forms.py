from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User
from .models import JobPost, CandidateProfile

class UserRegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['email', 'role']

class JobPostForm(forms.ModelForm):
    class Meta:
        model = JobPost
        fields = [
            'company_name',
            'title',
            'location',
            'description',
            'salary_range',
            'requirements',
            'deadline'
        ]

        widgets = {
            'deadline': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 4}),
            'requirements': forms.Textarea(attrs={'rows': 4}),
        }

class CandidateProfileForm(forms.ModelForm):
    class Meta:
        model = CandidateProfile
        fields = [
            'full_name', 
            'avatar', 
            'phone_number', 
            'address', 
            'gender', 
            'level', 
            'skills', 
            'cv_file' 
        ]
        
        widgets = {
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'skills': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ví dụ: Python, Django, SQL...'}),
            'phone_number': forms.TextInput(attrs={'placeholder': 'Nhập số điện thoại'}),
        }