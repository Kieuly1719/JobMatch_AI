from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from base.models import JobPost, Application, CandidateProfile, Notification
from base.forms import CandidateProfileForm
from django.db.models import Q

@login_required(login_url='login')
def candidate_dashboard(request):
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
        'jobs': jobs
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
            messages.warning(request, 'Bạn cần upload CV trước khi ứng tuyển!')
            return redirect('my_profile')
        
    except CandidateProfile.DoesNotExist:
        messages.warning(request, 'Vui lòng cập nhật hồ sơ cá nhân trước!')
        return redirect('my_profile')
    
    existing_application = Application.objects.filter(job = job, candidate = request.user).exists()
    if existing_application:
        messages.info(request, 'Bạn đã nộp đơn vào vị trí này rồi.')
        return redirect('job_detail', pk=pk)
    
    Application.objects.create(
        job=job,
        candidate=request.user,
        status='Pending' 
    )
    # Notification.objects.create(
    #     user = job.recruiter,
    #     message = f"Hồ sơ mới từ {request.user.candidate_profile.full_name} cho job {job.title}",
    #     link=f"/job/{job.id}/applicants/"
    # )
    messages.success(request, 'Nộp đơn ứng tuyển thành công! Chúc bạn may mắn.')
    return redirect('candidate_dashboard')