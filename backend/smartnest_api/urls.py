from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('api/', include('core.urls')),
]

# The separate password-only admin must not bypass production API MFA.
if not settings.PRODUCTION:
    urlpatterns.insert(0, path('admin/', admin.site.urls))

if not settings.SUPABASE_AUTH_ENABLED:
    urlpatterns.append(path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'))
