from django.urls import path
from base.views import auth_view
from base.views import candidate_view
from base.views import recruiter_view

urlpatterns = [
    path('', auth_view.home, name='home'),
    path('register/', auth_view.register, name='register'),
    path('login/', auth_view.login_page, name='login'),
    path("logout/", auth_view.logout_page, name="logout"),
    path('recruiter_dashboard/',recruiter_view.recruiter_dashboard, name='recruiter_dashboard'),
    path('dashboard/', candidate_view.candidate_dashboard, name = 'candidate_dashboard'),
    path('create_job/', recruiter_view.create_job, name='create_job'),
    path('job/<str:pk>/', candidate_view.job_detail, name='job_detail'),
    path('update-job/<str:pk>/', recruiter_view.update_job, name='update_job'),
    path('delete-job/<str:pk>/', recruiter_view.delete_job, name='delete_job'),
    path('job/<str:pk>/applicants/', recruiter_view.job_applicants, name='job_applicants'),
    path('my-applications/', candidate_view.my_application, name='my_applications'),
    path('my-profile/', candidate_view.my_profile, name='my_profile'),
    path('apply-job/<str:pk>/', candidate_view.apply_job, name='apply_job'),
    path('update-application/<int:pk>/<str:status>/', recruiter_view.update_application_status, name='update_application_status'),
    path('application/<int:application_id>/view-cv/', recruiter_view.view_application_cv, name='view_application_cv'),
    path('notif/<int:pk>/read/', recruiter_view.mark_notification_read, name='mark_notif_read'),
    path('api/ask-ai/', candidate_view.ask_ai, name='ask_ai'),
]
