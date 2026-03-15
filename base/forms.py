from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CompanyProfile, User
from .models import JobPost, CandidateProfile

class UserRegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['email', 'role']

        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-primary focus:border-primary outline-none'
            }),
            'role': forms.Select(attrs={
                'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-primary focus:border-primary outline-none'
            }),
        }

    password1 = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-primary focus:border-primary outline-none'
    }))

    password2 = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-primary focus:border-primary outline-none'
    }))

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

        base_input = 'w-full pl-12 pr-4 py-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all text-slate-900 dark:text-white'

        widgets = {
            'company_name': forms.TextInput(attrs={
                'class': base_input,
                'placeholder': 'Nhập tên công ty'
            }),
            'title': forms.TextInput(attrs={
                'class': base_input,
                'placeholder': 'VD: Senior Frontend Developer'
            }),
            'location': forms.TextInput(attrs={
                'class': base_input,
                'placeholder': 'VD: Quận 1, TP.HCM hoặc Remote'
            }),
            'salary_range': forms.TextInput(attrs={
                'class': base_input,
                'placeholder': 'VD: 15 - 25 triệu',
                'min': '0',
                'step': '100000'
            }),
            'deadline': forms.DateInput(attrs={
                'type': 'date',
                'class': base_input
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all text-slate-900 dark:text-white resize-none',
                'rows': 5,
                'placeholder': 'Mô tả công việc...'
            }),
            'requirements': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all text-slate-900 dark:text-white resize-none',
                'rows': 5,
                'placeholder': 'Yêu cầu ứng viên...'
            }),
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

            'full_name': forms.TextInput(attrs={
                'class': 'w-full rounded-xl border border-slate-300 focus:border-primary focus:ring-primary px-4 py-3 bg-white dark:bg-slate-800',
                'placeholder': 'Nhập họ và tên'
            }),

            'phone_number': forms.TextInput(attrs={
                'class': 'w-full rounded-xl border border-slate-300 focus:border-primary focus:ring-primary px-4 py-3 bg-white dark:bg-slate-800',
                'placeholder': 'Nhập số điện thoại'
            }),

            'address': forms.TextInput(attrs={
                'class': 'w-full rounded-xl border border-slate-300 focus:border-primary focus:ring-primary px-4 py-3 bg-white dark:bg-slate-800',
                'placeholder': 'Nhập địa chỉ'
            }),

            'gender': forms.Select(attrs={
                'class': 'w-full rounded-xl border border-slate-300 focus:border-primary focus:ring-primary px-4 py-3 bg-white dark:bg-slate-800'
            }),

            'level': forms.Select(attrs={
                'class': 'w-full rounded-xl border border-slate-300 focus:border-primary focus:ring-primary px-4 py-3 bg-white dark:bg-slate-800'
            }),

            'skills': forms.Textarea(attrs={
                'class': 'w-full rounded-xl border border-slate-300 focus:border-primary focus:ring-primary px-4 py-3 bg-white dark:bg-slate-800 min-h-[120px]',
                'placeholder': 'Ví dụ: Python, Django, SQL...'
            }),

            'avatar': forms.ClearableFileInput(attrs={
                'class': 'block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200 dark:file:bg-slate-800 dark:file:text-slate-300'
            }),

            'cv_file': forms.ClearableFileInput(attrs={
                'class': 'block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200 dark:file:bg-slate-800 dark:file:text-slate-300'
            }),
        }
class CompanyForm(forms.ModelForm):
    class Meta:
        model = CompanyProfile
        fields = ['name', 'website', 'address', 'logo']

        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full bg-slate-50 border border-slate-200 text-slate-900 text-sm rounded-xl focus:ring-primary focus:border-primary block p-3 outline-none transition',
                'placeholder': 'Nhập tên công ty...'
            }),

            'website': forms.URLInput(attrs={
                'class': 'w-full bg-slate-50 border border-slate-200 text-slate-900 text-sm rounded-xl focus:ring-primary focus:border-primary block p-3 outline-none transition',
                'placeholder': 'https://...'
            }),

            'address': forms.TextInput(attrs={
                'class': 'w-full bg-slate-50 border border-slate-200 text-slate-900 text-sm rounded-xl focus:ring-primary focus:border-primary block p-3 outline-none transition',
                'placeholder': 'Số nhà, Tên đường, Quận, TP...'
            }),

            'logo': forms.FileInput(attrs={
                'class': 'hidden',
                'id': 'id_logo'
            })
        }