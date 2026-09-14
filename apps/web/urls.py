from django.urls import path

from .views import DashboardView, LandingView, ScenarioAnalyzeView, ScenarioReportView

app_name = "web"

urlpatterns = [
    path("", LandingView.as_view(), name="landing"),
    path("app/", DashboardView.as_view(), name="dashboard"),
    path("app/analyze/", ScenarioAnalyzeView.as_view(), name="analyze"),
    path("app/report/", ScenarioReportView.as_view(), name="report"),
]
