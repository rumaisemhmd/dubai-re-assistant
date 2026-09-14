from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class LandingView(TemplateView):
    """Public marketing/landing page — explains the product before sign-in."""

    template_name = "web/landing.html"


class DashboardView(LoginRequiredMixin, TemplateView):
    """Post-login app screen. Placeholder — built out in the next pass."""

    template_name = "web/dashboard.html"
    login_url = "/accounts/google/login/"
