from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from base.models import JobPost, Application, Notification
from base.forms import JobPostForm
import mimetypes

@login_required(login_url='login')
def recruiter_dashboard(request):
    if request.user.role != 'recruiter':
        return redirect('login')
    try:
        company = request.user.company_profile
    except:
        company = None
    my_jobs = JobPost.objects.filter(recruiter=request.user)
    notifications = Notification.objects.filter(user = request.user, is_read = False).order_by('-created_at')
    context = {
        'company': company,
        'my_jobs': my_jobs,
        'notifications': notifications
    }
    return render(request, 'recruiter/recruiter_dashboard.html', context)

@login_required(login_url='login')
def create_job(request):
    if request.user.role != 'recruiter':
        return HttpResponseForbidden("Chỉ nhà tuyển dụng mới được đăng bài.")

    if request.method == 'POST':
        form = JobPostForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.recruiter = request.user
            job.save()
            messages.success(request, 'Đăng tin tuyển dụng thành công!')
            return redirect('recruiter_dashboard') 
        else:
            print(form.errors)
            messages.error(request, 'Có lỗi xảy ra, vui lòng kiểm tra lại.')
    else:
        form = JobPostForm()
    return render(request, 'recruiter/create_job.html', {'form': form})

@login_required(login_url='login')
def update_job(request, pk):
    job = get_object_or_404(JobPost, id=pk)
    
    if request.user != job.recruiter:
        return HttpResponseForbidden("Bạn không có quyền chỉnh sửa công việc này.")
        
    form = JobPostForm(instance=job) # Khởi tạo mặc định
    
    if request.method == 'POST':
        form = JobPostForm(request.POST, instance=job)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cập nhật công việc thành công!')
            return redirect('recruiter_dashboard')
            
    return render(request, 'recruiter/create_job.html', {'form': form, 'title': 'Cập nhật tin tuyển dụng'})

@login_required(login_url='login')
def delete_job(request, pk):
    job = get_object_or_404(JobPost, id=pk)

    if request.user != job.recruiter:
        return HttpResponseForbidden("Bạn không có quyền xóa công việc này.")

    if request.method == 'POST':
        job.delete()
        messages.success(request, 'Xóa công việc thành công!')
        return redirect('recruiter_dashboard')

    return render(request, 'recruiter/delete_confirm.html', {'object': job, 'type': 'công việc'})

@login_required(login_url='login')
def job_applicants(request, pk):
    job = get_object_or_404(JobPost, id=pk)

    if request.user != job.recruiter:
        return HttpResponseForbidden("Bạn không có quyền xem ứng viên cho công việc này.")

    applications = Application.objects.filter(job=job).order_by('-id')

    context = {
        'job': job,
        'applications': applications
    }
    return render(request, 'recruiter/job_applicants.html', context)

@login_required(login_url='login')
def update_application_status(request, pk, status):
    application = get_object_or_404(Application, id=pk)

    if(request.user != application.job.recruiter):
        return HttpResponseForbidden("Bạn không có quyền thực hiện thao tác này.")

    if status in ['Accepted', 'Rejected']:
        application.status = status
        application.save()
        messages.success(request, f"Đã cập nhật trạng thái ứng viên thành: {status}")

    return redirect('job_applicants', pk=application.job.id)

@login_required(login_url='login')
def view_application_cv(request, application_id):
    application = get_object_or_404(Application, id=application_id)
    if request.user != application.job.recruiter:
        return HttpResponseForbidden("Bạn không có quyền xem CV này.")
    
    cv_url = None
    is_pdf = False

    try:
        profile = application.candidate.candidate_profile
        if profile.cv_file:
            cv_url = profile.cv_file.url
            filename = profile.cv_file.name
            if filename.lower().endswith('.pdf'):
                is_pdf = True

    except:
        profile = None
    
    context = {
        'application': application,
        'cv_url': cv_url,
        'is_pdf': is_pdf,
        'profile': profile
    }
    return render(request, 'recruiter/view_cv.html', context)

@login_required(login_url='login')
def mark_notification_read(request, pk):
    notif = get_object_or_404(Notification, id=pk)
    if request.user == notif.user:
        notif.is_read = True 
        notif.save()
        return redirect(notif.link) if notif.link else redirect('recruiter_dashboard')
    return redirect('recruiter_dashboard')