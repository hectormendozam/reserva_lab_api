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
        # Filtros de query params
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        lab_id = request.query_params.get("lab")
        status = request.query_params.get("status")
        
        reservaciones = models.Reservacion.objects.filter(
            status=models.Reservacion.ReservacionStatus.APROBADO
        )
        
        if date_from:
            reservaciones = reservaciones.filter(fecha__gte=date_from)
        if date_to:
            reservaciones = reservaciones.filter(fecha__lte=date_to)
        if lab_id:
            reservaciones = reservaciones.filter(lab_id=lab_id)
        if status:
            reservaciones = reservaciones.filter(status=status)
        
        data = []
        for reserva in reservaciones:
            hora_inicio = datetime.combine(datetime.min, reserva.horaInicio)
            hora_fin = datetime.combine(datetime.min, reserva.horaFin)
            delta = hora_fin - hora_inicio
            horas_reservadas = delta.total_seconds() / 3600
            
            data.append({
                "labId": reserva.lab.id,
                "nombreLab": reserva.lab.nombre,  
                "fecha": reserva.fecha.strftime("%Y-%m-%d"),
                "horasReservadas": round(horas_reservadas, 2),
                "estadoReserva": reserva.status
            })
        
        return Response(data)


class EquipmentUsageReportView(BaseReportView):
    def get(self, request, *args, **kwargs):
        start_date, end_date = _parse_date_range(request)
        loans = models.Prestamo.objects.filter(
            status__in=[
                models.Prestamo.PrestamoStatus.APROBADO,
                models.Prestamo.PrestamoStatus.DEVUELTO,
                models.Prestamo.PrestamoStatus.DANADO,
            ],
            fechaPrestamo__range=(start_date, end_date),
        )
        aggregated = loans.values("equipo_id", "equipo__nombre").annotate(prestamos_totales=Count("id"))
        data = [
            {
                "equipo_id": item["equipo_id"],
                "equipo_name": item["equipo__nombre"],
                "prestamos_totales": item["prestamos_totales"],
            }
            for item in aggregated
        ]
        return Response(data)


class IncidentReportView(BaseReportView):
    def get(self, request, *args, **kwargs):
        fechaInicio, fechaFin = _parse_date_range(request)
        incidentes = models.Prestamo.objects.filter(
            status=models.Prestamo.PrestamoStatus.DANADO,
            fechaEntrega__range=(fechaInicio, fechaFin),
        ).select_related("equipo")
        data = [
            {
                "loan_id": loan.id,
                "nombre": loan.equipo.nombre,
                "tipo_dano": "DANADO" if loan.danado else "DEVUELTO",
                "reported_at": loan.updated_at.isoformat(),
            }
            for loan in incidentes
        ]
        return Response(data)


def _parse_period(period: str | None):
    hoy = timezone.localdate()
    if not period:
        año, mes = hoy.año, hoy.mes
        period_label = hoy.strftime("%Y-%m")
    else:
        try:
            parsed = datetime.strptime(period, "%Y-%m")
        except ValueError as exc:
            raise ValidationError({"period": "Formato inválido. Use YYYY-MM."}) from exc
        año, mes = parsed.year, parsed.month
        period_label = parsed.strftime("%Y-%m")
    start_day = 1
    ultimo_dia = calendar.monthrange(año, mes)[1]
    fechaInicio = datetime(año, mes, start_day).date()
    fechaFin = datetime(año, mes, ultimo_dia).date()
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