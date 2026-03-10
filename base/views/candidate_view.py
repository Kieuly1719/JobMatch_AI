from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from base.models import JobPost, Application, CandidateProfile, Notification
from base.forms import CandidateProfileForm
from django.db.models import Q

@login_required(login_url='login')
def candidate_dashboard(request):
    toast = request.session.pop("toast", None)
    

    if request.user.role != 'candidate':
        return redirect('recruiter_dashboard')
    my_applications = Application.objects.filter(candidate=request.user).order_by('-applied_at')
    jobs = JobPost.objects.all().order_by('-created_at')
    query = request.GET.get('q')
    if query:
        jobs = jobs.filter(
            Q(title__icontains = query)|
            Q(location__icontains = query)
        )
    context = {
        'jobs': jobs,
        "toast": toast
    }
    return render(request, 'candidate/dashboard.html', context)

def job_detail(request, pk): 
    job = get_object_or_404(JobPost, id=pk)
    context = {
        'job': job
    }
    return render(request, 'recruiter/job_detail.html', context)

@login_required(login_url='login')
def my_application(request):
    if request.user.role != 'candidate':
        return redirect('home')
    apps = Application.objects.filter(candidate=request.user).order_by('-applied_at')
    return render(request, 'candidate/my_application.html', {'apps': apps})

@login_required(login_url='login')
def my_profile(request):
    if request.user.role != 'candidate':
        return redirect('home')
    profile, created = CandidateProfile.objects.get_or_create(user = request.user)
    
    if request.method == 'POST':
        form = CandidateProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.save()
            messages.success(request, "Cập nhật hồ sơ thành công!")
            return redirect('my_profile')
    else:
        form = CandidateProfileForm(instance=profile)
        
    return render(request, 'candidate/profile.html', {'form': form})

@login_required(login_url='login')
def apply_job(request, pk):
    if request.user.role != 'candidate':
        messages.error(request, 'Nhà tuyển dụng không thể ứng tuyển!')
        return redirect('home')
    job = get_object_or_404(JobPost, id=pk)
    try:
        profile = request.user.candidate_profile
        if not profile.cv_file:
            request.session["toast"] = {
                "type": "warning",
                "message": "Bạn cần upload CV trước khi ứng tuyển!"
            }
            messages.warning(request, 'Bạn cần upload CV trước khi ứng tuyển!')
            return redirect('my_profile')
        
    except CandidateProfile.DoesNotExist:
        request.session["toast"] = {
            "type": "warning",
            "message": "Bạn cần tạo hồ sơ ứng viên trước khi ứng tuyển!"
        }
        return redirect('my_profile')
    
    existing_application = Application.objects.filter(job = job, candidate = request.user).exists()
    if existing_application:
        request.session["toast"] = {
            "type": "error",
            "message": "Bạn đã ứng tuyển vào công việc này rồi!"
        }
        return redirect('job_detail', pk=pk)
    Application.objects.create(
        job=job,
        candidate=request.user,
        status='Pending' 
    )
    request.session["toast"] = {
    "type": "success",
    "message": "Nộp đơn ứng tuyển thành công! Chúc bạn may mắn."
}
    return redirect('candidate_dashboard')