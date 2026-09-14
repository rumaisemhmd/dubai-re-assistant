import hashlib
import json
from dataclasses import asdict

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.http import FileResponse, HttpResponseBadRequest, JsonResponse
from django.views import View
from django.views.generic import TemplateView
from google.genai import errors as genai_errors

from apps.agents.calculation import CalculationAgent
from apps.agents.compliance import ComplianceAgent
from apps.agents.report import ReportAgent
from apps.ingestion.models import Transaction

# Gemini's free tier caps at a small number of requests/day — cache a full
# scenario's result (area + property type + price + compliance question) for
# a day so repeatedly re-running the same scenario (e.g. while testing)
# doesn't burn quota re-calling Gemini.
SCENARIO_CACHE_TIMEOUT_SECONDS = 60 * 60 * 24

QUOTA_ERROR_MESSAGE = (
    "Oops — we've hit today's usage limit for AI analysis. Please try again "
    "in a few minutes, or come back tomorrow."
)


def _is_quota_error(exc):
    """True for Gemini 429 (rate limit) / 503 (overloaded) errors specifically —
    the only cases we mask with QUOTA_ERROR_MESSAGE instead of the real detail."""
    return isinstance(exc, genai_errors.APIError) and getattr(exc, "code", None) in (429, 503)


def _scenario_cache_key(data):
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()
    return f"scenario-analysis:v1:{digest}"


class LandingView(TemplateView):
    """Public marketing/landing page — explains the product before sign-in."""

    template_name = "web/landing.html"


class DashboardView(LoginRequiredMixin, TemplateView):
    """Scenario builder: form + async results view + PDF report download."""

    template_name = "web/dashboard.html"
    login_url = "/accounts/google/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["areas"] = (
            Transaction.objects.filter(group="Sales")
            .exclude(area="")
            .order_by("area")
            .values_list("area", flat=True)
            .distinct()
        )
        context["property_types"] = (
            Transaction.objects.filter(group="Sales")
            .exclude(property_type="")
            .order_by("property_type")
            .values_list("property_type", flat=True)
            .distinct()
        )
        return context


def _parse_scenario_payload(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return None, HttpResponseBadRequest("Invalid JSON body.")

    area = (payload.get("area") or "").strip()
    property_type = (payload.get("property_type") or "").strip()
    scenario = (payload.get("scenario") or "").strip()

    if not area or not property_type:
        return None, JsonResponse({"error": "Area and property type are required."}, status=400)

    try:
        purchase_price = float(payload.get("purchase_price"))
        if purchase_price <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return None, JsonResponse({"error": "Purchase price must be a positive number."}, status=400)

    return {
        "area": area,
        "property_type": property_type,
        "purchase_price": purchase_price,
        "scenario": scenario,
    }, None


class ScenarioAnalyzeView(LoginRequiredMixin, View):
    """Runs the calculation agent (and, if a scenario was given, the compliance agent)."""

    login_url = "/accounts/google/login/"

    def post(self, request):
        data, error_response = _parse_scenario_payload(request)
        if error_response is not None:
            return error_response

        cache_key = _scenario_cache_key(data)
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)

        try:
            analysis = CalculationAgent().analyze(
                area=data["area"], property_type=data["property_type"],
                purchase_price=data["purchase_price"],
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except Exception as exc:
            return JsonResponse({"error": f"Calculation failed: {exc}"}, status=502)

        result = {"analysis": asdict(analysis)}

        if data["scenario"]:
            try:
                assessment = ComplianceAgent().check(data["scenario"])
                result["compliance"] = asdict(assessment)
            except Exception as exc:
                result["compliance_error"] = (
                    QUOTA_ERROR_MESSAGE if _is_quota_error(exc) else f"Compliance check failed: {exc}"
                )

        # Only cache clean results — a quota/error result should be retried
        # fresh next time, not served back stale from cache.
        if "compliance_error" not in result:
            cache.set(cache_key, result, timeout=SCENARIO_CACHE_TIMEOUT_SECONDS)

        return JsonResponse(result)


class ScenarioReportView(LoginRequiredMixin, View):
    """Runs the report-generator agent and streams the resulting PDF back."""

    login_url = "/accounts/google/login/"

    def post(self, request):
        data, error_response = _parse_scenario_payload(request)
        if error_response is not None:
            return error_response

        try:
            output_path = ReportAgent().generate_for_property(
                area=data["area"], property_type=data["property_type"],
                purchase_price=data["purchase_price"], scenario=data["scenario"] or None,
            )
        except Exception as exc:
            if _is_quota_error(exc):
                return JsonResponse({"error": QUOTA_ERROR_MESSAGE}, status=429)
            return JsonResponse({"error": f"Report generation failed: {exc}"}, status=502)

        return FileResponse(open(output_path, "rb"), as_attachment=True, filename=output_path.name)
