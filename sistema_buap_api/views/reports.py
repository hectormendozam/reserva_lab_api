import calendar
from datetime import datetime

from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from sistema_buap_api import models, permissions as custom_permissions


class BaseReportView(APIView):
    permission_classes = [custom_permissions.IsAdminOrTech]


class OccupancyReportView(BaseReportView):
    def get(self, request, *args, **kwargs):
        period = request.query_params.get("period")
        fechaInicio, fechaFin, period_label = _parse_period(period)
        reservations = models.Reservation.objects.filter(
            status=models.Reservation.ReservationStatus.APPROVED,
            date__range=(fechaInicio, fechaFin),
        )
        data = []
        total_days = (fechaFin - fechaInicio).days + 1
        capacidad_total_horas = max(total_days * 12, 1)
        for lab in models.Lab.objects.all():
            lab_reservations = reservations.filter(lab=lab).values(
                "fechaInicio", "fechaFin"
            )
            horas_reservadas = 0
            for item in lab_reservations:
                delta = datetime.combine(datetime.min, item["fechaFin"]) - datetime.combine(
                    datetime.min, item["fechaInicio"]
                )
                horas_reservadas += delta.total_seconds() / 3600
            tasa_ocupacion = min(horas_reservadas / capacidad_total_horas, 1)
            data.append(
                {
                    "lab_id": lab.id,
                    "lab_name": lab.name,
                    "period": period_label,
                    "tasa_ocupacion": round(tasa_ocupacion, 4),
                }
            )
        return Response(data)


class EquipmentUsageReportView(BaseReportView):
    def get(self, request, *args, **kwargs):
        start_date, end_date = _parse_date_range(request)
        loans = models.Loan.objects.filter(
            status__in=[
                models.Loan.LoanStatus.APROBADO,
                models.Loan.LoanStatus.DEVUELTO,
                models.Loan.LoanStatus.DANADO,
            ],
            loan_date__range=(start_date, end_date),
        )
        aggregated = loans.values("equipo_id", "equipo__name").annotate(prestamos_totales=Count("id"))
        data = [
            {
                "equipo_id": item["equipo_id"],
                "equipo_name": item["equipo__name"],
                "prestamos_totales": item["prestamos_totales"],
            }
            for item in aggregated
        ]
        return Response(data)


class IncidentReportView(BaseReportView):
    def get(self, request, *args, **kwargs):
        fechaInicio, fechaFin = _parse_date_range(request)
        incidents = models.Loan.objects.filter(
            status=models.Loan.LoanStatus.DANADO,
            fechaEntrega__range=(fechaInicio, fechaFin),
        ).select_related("equipo")
        data = [
            {
                "loan_id": loan.id,
                "nombre": loan.equipo.name,
                "tipo_dano": "DANADO" if loan.danado else "DEVUELTO",
                "reported_at": loan.updated_at.isoformat(),
            }
            for loan in incidents
        ]
        return Response(data)


def _parse_period(period: str | None):
    today = timezone.localdate()
    if not period:
        year, month = today.year, today.month
        period_label = today.strftime("%Y-%m")
    else:
        try:
            parsed = datetime.strptime(period, "%Y-%m")
        except ValueError as exc:
            raise ValidationError({"period": "Formato inválido. Use YYYY-MM."}) from exc
        year, month = parsed.year, parsed.month
        period_label = parsed.strftime("%Y-%m")
    start_day = 1
    ultimo_dia = calendar.monthrange(year, month)[1]
    fechaInicio = datetime(year, month, start_day).date()
    fechaFin = datetime(year, month, ultimo_dia).date()
    return fechaInicio, fechaFin, period_label


def _parse_date_range(request):
    start_param = request.query_params.get("from")
    end_param = request.query_params.get("to")
    today = timezone.localdate()
    try:
        fechaInicio = datetime.strptime(start_param, "%Y-%m-%d").date() if start_param else today.replace(day=1)
        fechaFin = datetime.strptime(end_param, "%Y-%m-%d").date() if end_param else today
    except ValueError as exc:
        raise ValidationError({"detail": "Fechas inválidas. Use YYYY-MM-DD."}) from exc
    if fechaInicio > fechaFin:
        raise ValidationError({"detail": "El rango de fechas es inválido."})
    return fechaInicio, fechaFin