from django.urls import path

from .views import DashboardView, LandingView

app_name = "web"

urlpatterns = [
    path("", LandingView.as_view(), name="landing"),
    path("app/", DashboardView.as_view(), name="dashboard"),
]
