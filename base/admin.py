from django.contrib import admin
from .models import User, CompanyProfile, CandidateProfile, JobPost, Application

admin.site.register(User)
admin.site.register(CompanyProfile)
admin.site.register(CandidateProfile)
admin.site.register(JobPost)
admin.site.register(Application)