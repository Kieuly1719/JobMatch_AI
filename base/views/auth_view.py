from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from base.forms import UserRegisterForm
from base.models import JobPost

def home(request):
    jobs = JobPost.objects.all().order_by('-created_at')

    return render(request, 'home.html', {
        'jobs': jobs
    })

def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            email = form.cleaned_data.get('email')
            messages.success(request, f'Tài khoản {email} đã được tạo thành công!')
            return redirect('login')
    else:
        form = UserRegisterForm()
    return render(request, 'accounts/register.html', {'form': form})

def login_page(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)

            if user is not None:
                login(request, user)
                messages.info(request, f"Chào mừng {username} quay trở lại!")
                if user.role == 'recruiter':
                    return redirect('recruiter_dashboard')  
                else:
                    return redirect('candidate_dashboard')
            else:
                messages.error(request, "Sai email hoặc mật khẩu")
        else:
            messages.error(request, "Sai email hoặc mật khẩu")
        
    form = AuthenticationForm()
    return render(request, 'accounts/login.html', {'form': form})
def logout_page(request):
    logout(request)
    messages.info(request, "Bạn đã đăng xuất thành công!")
    return redirect('home')