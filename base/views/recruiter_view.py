from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from base.models import CompanyProfile, JobPost, Application, Notification
from base.forms import CompanyForm, JobPostForm
from django.shortcuts import render
from django.db.models import Q
from base.forms import CompanyForm
import mimetypes

@login_required(login_url='login')
def recruiter_dashboard(request):
    toast = request.session.pop("toast", None)
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
        'notifications': notifications,
        "active": "dashboard",
        "toast": toast
    }
    return render(request, 'recruiter/recruiter_dashboard.html',
                  context)
@login_required(login_url='login')
def company_profile(request):

    company, created = CompanyProfile.objects.get_or_create(
    user=request.user
)

    edit_mode = request.GET.get("edit")

    if request.method == "POST":

        form = CompanyForm(
            request.POST,
            request.FILES,
            instance=company
        )

        if form.is_valid():
            form.save()
            return redirect("company_profile")

    else:
        form = CompanyForm(instance=company)

    return render(
        request,
        "recruiter/company_profile.html",
        {
            "company": company,
            "form": form,
            "edit_mode": edit_mode
        }
    )
@login_required(login_url='login')
def recruiter_candidates(request):

    applications = Application.objects.filter(
        job__recruiter=request.user
    )

    # GET params
    search = request.GET.get("search")
    job_filter = request.GET.get("job")
    status_filter = request.GET.get("status")
    sort = request.GET.get("sort")

    # SEARCH
    if search:
        applications = applications.filter(
            Q(candidate__candidate_profile__full_name__icontains=search) |
            Q(candidate__email__icontains=search) |
            Q(job__title__icontains=search)
        )

    # FILTER JOB
    if job_filter:
        applications = applications.filter(job_id=job_filter)

    # FILTER STATUS
    if status_filter:
        applications = applications.filter(status=status_filter)

    # SORT
    if sort == "oldest":
        applications = applications.order_by("applied_at")
    else:
        applications = applications.order_by("-applied_at")

    jobs = JobPost.objects.filter(recruiter=request.user)

    stats = {
        "new": applications.filter(status="Pending").count(),
        "reviewing": applications.filter(status="Pending").count(),
        "accepted": applications.filter(status="Accepted").count(),
        "rejected": applications.filter(status="Rejected").count(),
    }

    return render(
        request,
        "recruiter/candidates.html",
        {
            "applications": applications,
            "jobs": jobs,
            "stats": stats,
        },
    )
@login_required
def job_management(request):

    status = request.GET.get("status")

    jobs = JobPost.objects.filter(recruiter=request.user)

    if status == "active":
        jobs = jobs.filter(is_active=True)

    elif status == "expired":
        jobs = jobs.filter(is_active=False)

    return render(request, "recruiter/job_management.html", {
        "jobs": jobs,
        "status": status
    })
@login_required(login_url='login')
def recruiter_job_detail(request, id):
    job = JobPost.objects.get(id=id)
    if request.user != job.recruiter:
        return HttpResponseForbidden("Bạn không có quyền xem chi tiết công việc này.")
    applications = job.applications.select_related(
        "candidate",
        "candidate__candidate_profile"
    )
    return render(request, 'recruiter/job_manage_detail.html', {'job': job, 'applications': applications})

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
            request.session["toast"] = {
                "type": "success",
                "message": "Đăng tin tuyển dụng thành công!"    
            }
            return redirect('recruiter_dashboard') 
        else:
            print(form.errors)
            status = "ERROR"
            request.session["toast"] = {
                "type": "error",
                "message": "Đăng tin tuyển dụng thất bại!"    
            }
            return render(request, 'recruiter/create_job.html', {'form': form, 'status': status})
    else:
        form = JobPostForm()
    return render(request, 'recruiter/create_job.html', {'form': form})

@login_required(login_url='login')
def update_job(request, pk):
    job = get_object_or_404(JobPost, id=pk)
    
    if request.user != job.recruiter:
        return HttpResponseForbidden("Bạn không có quyền chỉnh sửa công việc này.")
        
    form = JobPostForm(instance=job) 
    
    if request.method == 'POST':
        form = JobPostForm(request.POST, instance=job)
        if form.is_valid():
            form.save()
            request.session["toast"] = {
                "type": "success",
                "message": "Cập nhật tin tuyển dụng thành công!"
            }
            return redirect('recruiter_dashboard')
            
    return render(request, 'recruiter/create_job.html', {'form': form, 'title': 'Cập nhật tin tuyển dụng'})

@login_required(login_url='login')
def delete_job(request, pk):
    job = get_object_or_404(JobPost, id=pk)

    if request.user != job.recruiter:
        return HttpResponseForbidden("Bạn không có quyền xóa công việc này.")

    if request.method == 'POST':
        job.delete()
        request.session["toast"] = {
            "type": "success",
            "message": "Xóa công việc thành công!"
        }
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
        request.session["toast"] = {
            "type": "success",
            "message": f"Đã cập nhật trạng thái ứng viên thành: {status}"
        }

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

@login_required
def edit_company(request):
    company = CompanyProfile.objects.filter(user = request.user).first()
    if request.method == 'POST':
        form = CompanyForm(request.POST, instance=company)
        
        if form.is_valid():
            # Khoan lưu vội, lấy dữ liệu ra trước để gắn user vào (đề phòng trường hợp Tạo mới)
            new_company = form.save(commit=False)
            new_company.user = request.user 
            new_company.save()
            return redirect('recruiter_dashboard') # Lưu xong thì quay về Dashboard
    else:
        # Nếu là request GET (vào xem trang), thì hiển thị form với dữ liệu cũ (nếu có)
        form = CompanyForm(instance=company)

    return render(request, 'edit_company.html', {'form': form})