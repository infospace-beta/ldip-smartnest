from django.contrib import admin
from .models import User, Property, Unit, Tenant, Payment, Notice, MaintenanceJob, Staff

admin.site.register(User)
admin.site.register(Property)
admin.site.register(Unit)
admin.site.register(Tenant)
admin.site.register(Payment)
admin.site.register(Notice)
admin.site.register(MaintenanceJob)
admin.site.register(Staff)
