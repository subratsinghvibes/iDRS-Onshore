"""
Schedule Execution Module (SEM) Views
Independent module to execute approved schedules, capture actuals,
lock completed work, and enable controlled re-optimization.
"""

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, Max, Min, Count, Q, F, Avg
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from decimal import Decimal
from datetime import datetime, date, timedelta
import json
import logging

from .models import (
    Schedule, Assignment, ScheduleRig, ScheduleWell,
    Rig, Well, CompanyCode,
    ExecutionSchedule, ExecutionRig, ExecutionWell, ExecutionLog,
    ExecutionScenario,
    parse_financial_year,
)
from .optimization import DrillingScheduler
from .well_rejection_analyzer import WellRejectionAnalyzer
from .views import get_user_location, get_user_accessible_locations

logger = logging.getLogger(__name__)


# =============================================================================
# TEMPLATE VIEWS
# =============================================================================

@login_required
def sem_dashboard(request):
    """Main SEM dashboard - lists all execution schedules"""
    return render(request, 'scheduler/sem_dashboard.html')


@login_required
def sem_detail(request, execution_id):
    """Detail view for a single execution schedule"""
    execution = get_object_or_404(ExecutionSchedule, id=execution_id)
    return render(request, 'scheduler/sem_detail.html', {'execution_id': str(execution_id)})


# =============================================================================
# API: LIST & ACTIVATE
# =============================================================================

@api_view(['GET'])
def sem_list_executions(request):
    """List all execution schedules with summary stats"""
    location = get_user_location(request.user)
    qs = ExecutionSchedule.objects.all()
    if location:
        qs = qs.filter(location=location)

    data = []
    for ex in qs:
        wells = ex.execution_wells.all()
        total = wells.count()
        locked = wells.filter(is_locked=True).count()
        completed = wells.filter(status='COMPLETED').count()
        in_progress = wells.filter(status='IN_PROGRESS').count()

        data.append({
            'id': str(ex.id),
            'name': ex.name,
            'source_schedule_id': str(ex.source_schedule_id),
            'source_schedule_name': ex.source_schedule.name,
            'financial_year': ex.financial_year,
            'status': ex.status,
            'cutoff_date': ex.cutoff_date.isoformat() if ex.cutoff_date else None,
            'total_wells': total,
            'locked_wells': locked,
            'completed_wells': completed,
            'in_progress_wells': in_progress,
            'progress_pct': round((completed / total) * 100, 1) if total else 0,
            'total_planned_cost': float(ex.total_planned_cost),
            'total_actual_cost': float(ex.total_actual_cost),
            'planned_end_date': ex.planned_end_date.isoformat() if ex.planned_end_date else None,
            'projected_end_date': ex.projected_end_date.isoformat() if ex.projected_end_date else None,
            'optimization_runs': ex.optimization_runs,
            'created_at': ex.created_at.isoformat(),
            'created_by': ex.created_by.username if ex.created_by else None,
        })
    return Response(data)


@api_view(['GET'])
def sem_available_schedules(request):
    """List completed schedules available for activation"""
    location = get_user_location(request.user)
    qs = Schedule.objects.filter(status='COMPLETED')
    if location:
        qs = qs.filter(location=location)

    data = []
    for s in qs.order_by('-created_at')[:50]:
        assignment_count = s.assignments.count()
        data.append({
            'id': str(s.id),
            'name': s.name,
            'financial_year': s.financial_year,
            'total_cost': float(s.total_cost),
            'assignment_count': assignment_count,
            'project_end_date': s.project_end_date.isoformat() if s.project_end_date else None,
            'created_at': s.created_at.isoformat(),
            'location_name': s.location.name if s.location else None,
        })
    return Response(data)


@api_view(['POST'])
def sem_activate_schedule(request):
    """Activate/move a completed schedule into execution"""
    schedule_id = request.data.get('schedule_id')
    if not schedule_id:
        return Response({'error': 'schedule_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    schedule = get_object_or_404(Schedule, id=schedule_id, status='COMPLETED')
    assignments = Assignment.objects.filter(schedule=schedule).select_related('rig', 'well')

    if not assignments.exists():
        return Response({'error': 'Schedule has no assignments'}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        # Create ExecutionSchedule
        exec_schedule = ExecutionSchedule.objects.create(
            name=f"Execution: {schedule.name}",
            source_schedule=schedule,
            location=schedule.location,
            financial_year=schedule.financial_year,
            status='ACTIVE',
            total_planned_cost=(schedule.total_drilling_cost or 0) + (schedule.total_ilm_cost or 0),
            planned_end_date=schedule.project_end_date,
            projected_end_date=schedule.project_end_date,
            created_by=request.user,
        )

        # Create ExecutionRigs
        rig_ids_seen = set()
        for a in assignments:
            if a.rig_id not in rig_ids_seen:
                rig_ids_seen.add(a.rig_id)
                ExecutionRig.objects.create(
                    execution_schedule=exec_schedule,
                    rig=a.rig,
                    is_active=True,
                )

        # Create ExecutionWells
        for a in assignments:
            ExecutionWell.objects.create(
                execution_schedule=exec_schedule,
                well=a.well,
                rig=a.rig,
                source_assignment=a,
                planned_start_date=a.well_start_date,
                planned_end_date=a.well_end_date,
                actual_start_date=a.actual_start_date,
                actual_end_date=a.actual_end_date,
                status='COMPLETED' if a.actual_end_date else ('IN_PROGRESS' if a.actual_start_date else 'PLANNED'),
                is_locked=bool(a.actual_start_date or a.actual_end_date),
                locked_at=timezone.now() if (a.actual_start_date or a.actual_end_date) else None,
                sequence_order=a.sequence_order,
                planned_drilling_cost=a.drilling_cost,
                actual_drilling_cost=a.drilling_cost if a.actual_end_date else Decimal('0'),
                planned_ilm_cost=a.ilm_cost,
            )

        # Log activation
        ExecutionLog.objects.create(
            execution_schedule=exec_schedule,
            action='ACTIVATED',
            description=f'Schedule "{schedule.name}" activated for execution',
            details={'source_schedule_id': str(schedule.id), 'well_count': assignments.count()},
            performed_by=request.user,
        )

    return Response({
        'id': str(exec_schedule.id),
        'name': exec_schedule.name,
        'status': exec_schedule.status,
        'total_wells': exec_schedule.execution_wells.count(),
    }, status=status.HTTP_201_CREATED)


# =============================================================================
# API: EXECUTION DETAIL & WELLS
# =============================================================================

@api_view(['GET'])
def sem_execution_detail(request, execution_id):
    """Full detail of an execution schedule with all wells"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    wells = ex.execution_wells.select_related('well', 'rig', 'well__location').all()
    rigs = ex.execution_rigs.select_related('rig').all()

    # Summary stats
    total = wells.count()
    locked = wells.filter(is_locked=True).count()
    completed = wells.filter(status='COMPLETED').count()
    in_progress = wells.filter(status='IN_PROGRESS').count()
    planned = wells.filter(status='PLANNED').count()
    deferred = wells.filter(status='DEFERRED').count()
    removed = wells.filter(status='REMOVED').count()

    # Delay stats
    completed_wells = wells.filter(actual_end_date__isnull=False, planned_end_date__isnull=False)
    total_delay = 0
    max_delay = 0
    delay_count = 0
    for w in completed_wells:
        delay = (w.actual_end_date - w.planned_end_date).days
        total_delay += delay
        if delay > max_delay:
            max_delay = delay
        if delay > 0:
            delay_count += 1

    # Rig utilization
    rig_data = []
    for er in rigs:
        rig_wells = wells.filter(rig=er.rig)
        assigned_days = sum(
            (w.planned_end_date - w.planned_start_date).days for w in rig_wells
            if w.status not in ['REMOVED', 'DEFERRED']
        )
        rig_data.append({
            'id': str(er.id),
            'rig_id': str(er.rig.id),
            'rig_name': er.rig.name,
            'rig_type': er.rig.rig_type,
            'is_active': er.is_active,
            'well_count': rig_wells.exclude(status__in=['REMOVED', 'DEFERRED']).count(),
            'assigned_days': assigned_days,
        })

    # Well data
    wells_data = []
    for w in wells:
        wells_data.append({
            'id': str(w.id),
            'well_id': str(w.well.id),
            'well_name': w.well.name,
            'well_sn': w.well.sn,
            'well_type': w.well.well_type,
            'well_depth': w.well.depth,
            'well_priority': w.well.priority,
            'well_asset_id': w.well.asset_id,
            'rig_id': str(w.rig.id),
            'rig_name': w.rig.name,
            'planned_start': w.planned_start_date.isoformat(),
            'planned_end': w.planned_end_date.isoformat(),
            'actual_start': w.actual_start_date.isoformat() if w.actual_start_date else None,
            'actual_end': w.actual_end_date.isoformat() if w.actual_end_date else None,
            'status': w.status,
            'is_locked': w.is_locked,
            'locked_at': w.locked_at.isoformat() if w.locked_at else None,
            'sequence_order': w.sequence_order,
            'planned_drilling_cost': float(w.planned_drilling_cost),
            'actual_drilling_cost': float(w.actual_drilling_cost),
            'planned_ilm_cost': float(w.planned_ilm_cost),
            'actual_ilm_cost': float(w.actual_ilm_cost),
            'delay_days': w.delay_days,
            'planned_duration': w.planned_duration_days,
            'actual_duration': w.actual_duration_days,
            'cost_variance': w.cost_variance,
            'notes': w.notes,
            'remarks': w.notes,  # Alias for frontend compatibility
        })

    return Response({
        'id': str(ex.id),
        'name': ex.name,
        'source_schedule_id': str(ex.source_schedule_id),
        'source_schedule_name': ex.source_schedule.name,
        'financial_year': ex.financial_year,
        'status': ex.status,
        'cutoff_date': ex.cutoff_date.isoformat() if ex.cutoff_date else None,
        'total_planned_cost': float(ex.total_planned_cost),
        'total_actual_cost': float(ex.total_actual_cost),
        'planned_end_date': ex.planned_end_date.isoformat() if ex.planned_end_date else None,
        'projected_end_date': ex.projected_end_date.isoformat() if ex.projected_end_date else None,
        'optimization_runs': ex.optimization_runs,
        'last_optimized_at': ex.last_optimized_at.isoformat() if ex.last_optimized_at else None,
        'created_by': ex.created_by.username if ex.created_by else None,
        'created_at': ex.created_at.isoformat(),
        'summary': {
            'total': total,
            'locked': locked,
            'completed': completed,
            'in_progress': in_progress,
            'planned': planned,
            'deferred': deferred,
            'removed': removed,
            'progress_pct': round((completed / total) * 100, 1) if total else 0,
            'total_delay_days': total_delay,
            'max_delay_days': max_delay,
            'wells_with_delay': delay_count,
            'avg_delay_days': round(total_delay / delay_count, 1) if delay_count else 0,
        },
        'rigs': rig_data,
        'wells': wells_data,
    })


@api_view(['GET'])
def sem_gantt_data(request, execution_id):
    """Gantt chart data for execution schedule — planned + actual bars"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    wells = ex.execution_wells.select_related('well', 'rig').exclude(
        status='REMOVED'
    ).order_by('rig__name', 'sequence_order')

    tasks = []
    rig_names = set()
    for w in wells:
        rig_names.add(w.rig.name)
        # Planned bar
        tasks.append({
            'id': f"{w.id}_planned",
            'exec_well_id': str(w.id),
            'type': 'planned',
            'name': w.well.name,
            'rig': w.rig.name,
            'start': w.planned_start_date.isoformat(),
            'end': w.planned_end_date.isoformat(),
            'status': w.status,
            'is_locked': w.is_locked,
            'priority': w.well.priority,
            'well_type': w.well.well_type,
            'depth': w.well.depth,
            'sequence_order': w.sequence_order,
        })
        # Actual bar (only if there are actual dates)
        if w.actual_start_date:
            actual_end = w.actual_end_date or date.today()
            tasks.append({
                'id': f"{w.id}_actual",
                'exec_well_id': str(w.id),
                'type': 'actual',
                'name': w.well.name,
                'rig': w.rig.name,
                'start': w.actual_start_date.isoformat(),
                'end': actual_end.isoformat(),
                'status': w.status,
                'is_locked': w.is_locked,
                'priority': w.well.priority,
                'well_type': w.well.well_type,
                'depth': w.well.depth,
                'sequence_order': w.sequence_order,
            })

    # Date range
    all_starts = [w.planned_start_date for w in wells]
    all_ends = [w.planned_end_date for w in wells]
    actual_ends = [w.actual_end_date for w in wells if w.actual_end_date]
    all_ends.extend(actual_ends)

    return Response({
        'tasks': tasks,
        'rigs': sorted(rig_names),
        'date_range': {
            'start': min(all_starts).isoformat() if all_starts else None,
            'end': max(all_ends).isoformat() if all_ends else None,
        },
        'cutoff_date': ex.cutoff_date.isoformat() if ex.cutoff_date else None,
    })


# =============================================================================
# API: ACTUAL DATE CAPTURE & LOCKING
# =============================================================================

@api_view(['POST'])
def sem_update_actuals(request, execution_id):
    """
    Bulk update actual dates for execution wells.
    Payload: { "updates": [{ "exec_well_id": "...", "actual_start": "YYYY-MM-DD", "actual_end": "YYYY-MM-DD" }, ...] }
    """
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    if ex.status != 'ACTIVE':
        return Response({'error': 'Execution schedule is not active'}, status=status.HTTP_400_BAD_REQUEST)

    updates = request.data.get('updates', [])
    if not updates:
        return Response({'error': 'No updates provided'}, status=status.HTTP_400_BAD_REQUEST)

    updated_wells = []
    errors = []

    with transaction.atomic():
        for upd in updates:
            exec_well_id = upd.get('exec_well_id')
            if not exec_well_id:
                errors.append({'error': 'Missing exec_well_id', 'data': upd})
                continue

            try:
                ew = ExecutionWell.objects.get(id=exec_well_id, execution_schedule=ex)
            except ExecutionWell.DoesNotExist:
                errors.append({'error': f'Well {exec_well_id} not found', 'data': upd})
                continue

            actual_start = upd.get('actual_start')
            actual_end = upd.get('actual_end')

            if actual_start:
                try:
                    actual_start = datetime.strptime(actual_start, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    errors.append({'error': f'Invalid actual_start date for well {ew.well.name}'})
                    continue

            if actual_end:
                try:
                    actual_end = datetime.strptime(actual_end, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    errors.append({'error': f'Invalid actual_end date for well {ew.well.name}'})
                    continue

            # Get remarks from update data
            remarks = upd.get('remarks', '')
            
            ew.set_actual_dates(actual_start=actual_start, actual_end=actual_end, user=request.user)
            
            # Update notes/remarks if provided
            if remarks:
                ew.notes = remarks
                ew.save(update_fields=['notes'])

            # Calculate actual cost if completed
            if ew.actual_start_date and ew.actual_end_date:
                actual_days = (ew.actual_end_date - ew.actual_start_date).days
                ew.actual_drilling_cost = Decimal(str(actual_days)) * ew.rig.daily_cost_inr
                ew.save(update_fields=['actual_drilling_cost'])

            updated_wells.append(ew.well.name)

            # Log
            ExecutionLog.objects.create(
                execution_schedule=ex,
                action='ACTUAL_SET',
                description=f'Actual dates set for {ew.well.name}: start={actual_start}, end={actual_end}{f", remarks: {remarks}" if remarks else ""}',
                details={
                    'exec_well_id': str(ew.id),
                    'well_name': ew.well.name,
                    'actual_start': str(actual_start) if actual_start else None,
                    'actual_end': str(actual_end) if actual_end else None,
                    'remarks': remarks if remarks else None,
                },
                performed_by=request.user,
            )

        # Recalculate metrics
        ex.recalculate_metrics()

    return Response({
        'updated': updated_wells,
        'errors': errors,
        'total_updated': len(updated_wells),
    })


@api_view(['POST'])
def sem_lock_well(request, execution_id):
    """Lock a specific well"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    exec_well_id = request.data.get('exec_well_id')
    ew = get_object_or_404(ExecutionWell, id=exec_well_id, execution_schedule=ex)

    if ew.is_locked:
        return Response({'message': f'{ew.well.name} is already locked'})

    ew.lock(user=request.user)

    ExecutionLog.objects.create(
        execution_schedule=ex,
        action='LOCKED',
        description=f'Well {ew.well.name} manually locked',
        details={'exec_well_id': str(ew.id), 'well_name': ew.well.name},
        performed_by=request.user,
    )

    return Response({'message': f'{ew.well.name} locked successfully', 'is_locked': True})


@api_view(['POST'])
def sem_unlock_well(request, execution_id):
    """Unlock a specific well"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    if ex.status != 'ACTIVE':
        return Response({'error': 'Execution is not active'}, status=status.HTTP_400_BAD_REQUEST)

    exec_well_id = request.data.get('exec_well_id')
    ew = get_object_or_404(ExecutionWell, id=exec_well_id, execution_schedule=ex)

    if not ew.is_locked:
        return Response({'message': f'{ew.well.name} is already unlocked'})

    ew.is_locked = False
    ew.locked_at = None
    ew.locked_by = None
    if ew.status == 'LOCKED':
        ew.status = 'PLANNED'
    ew.save(update_fields=['is_locked', 'locked_at', 'locked_by', 'status'])

    ExecutionLog.objects.create(
        execution_schedule=ex,
        action='STATUS_CHANGE',
        description=f'Well {ew.well.name} manually unlocked',
        details={'exec_well_id': str(ew.id), 'well_name': ew.well.name, 'action': 'unlocked'},
        performed_by=request.user,
    )

    return Response({'message': f'{ew.well.name} unlocked successfully', 'is_locked': False})


@api_view(['POST'])
def sem_apply_cutoff(request, execution_id):
    """Apply cutoff lock — lock all wells up to selected date"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    cutoff_str = request.data.get('cutoff_date')
    if not cutoff_str:
        return Response({'error': 'cutoff_date is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        cutoff = datetime.strptime(cutoff_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

    count = ex.apply_cutoff_lock(cutoff)

    ExecutionLog.objects.create(
        execution_schedule=ex,
        action='CUTOFF_APPLIED',
        description=f'Cutoff lock applied: all wells before {cutoff_str} locked ({count} wells)',
        details={'cutoff_date': cutoff_str, 'wells_locked': count},
        performed_by=request.user,
    )

    return Response({'message': f'{count} wells locked up to {cutoff_str}', 'wells_locked': count})


# =============================================================================
# API: RIG & WELL MODIFICATIONS
# =============================================================================

@api_view(['POST'])
def sem_add_well(request, execution_id):
    """Add a well from Manage Wells to this execution (for future optimization only)"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    if ex.status != 'ACTIVE':
        return Response({'error': 'Execution is not active'}, status=status.HTTP_400_BAD_REQUEST)

    well_id = request.data.get('well_id')
    rig_id = request.data.get('rig_id')

    well = get_object_or_404(Well, id=well_id)
    rig = get_object_or_404(Rig, id=rig_id)

    # Check if well already exists
    if ex.execution_wells.filter(well=well).exclude(status='REMOVED').exists():
        return Response({'error': f'Well {well.name} already in this execution'}, status=status.HTTP_400_BAD_REQUEST)

    # Find max sequence order for this rig
    max_seq = ex.execution_wells.filter(rig=rig).aggregate(m=Max('sequence_order'))['m'] or 0

    # Estimate planned dates — place at end of rig's current work
    last_well = ex.execution_wells.filter(rig=rig).exclude(status='REMOVED').order_by('-planned_end_date').first()
    if last_well:
        planned_start = last_well.planned_end_date + timedelta(days=1)
    else:
        planned_start = date.today()
    planned_end = planned_start + timedelta(days=well.duration)

    ew = ExecutionWell.objects.create(
        execution_schedule=ex,
        well=well,
        rig=rig,
        planned_start_date=planned_start,
        planned_end_date=planned_end,
        status='PLANNED',
        sequence_order=max_seq + 1,
        planned_drilling_cost=well.duration * rig.daily_cost_inr,
    )

    # Ensure rig is in execution
    ExecutionRig.objects.get_or_create(
        execution_schedule=ex, rig=rig,
        defaults={'is_active': True}
    )

    ExecutionLog.objects.create(
        execution_schedule=ex,
        action='WELL_ADDED',
        description=f'Well {well.name} added to rig {rig.name}',
        details={'well_id': str(well.id), 'well_name': well.name, 'rig_name': rig.name},
        performed_by=request.user,
    )

    ex.recalculate_metrics()
    return Response({
        'message': f'Well {well.name} added successfully',
        'exec_well_id': str(ew.id),
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def sem_remove_well(request, execution_id):
    """Remove a well from execution (only if not locked)"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    exec_well_id = request.data.get('exec_well_id')
    ew = get_object_or_404(ExecutionWell, id=exec_well_id, execution_schedule=ex)

    if ew.is_locked:
        return Response(
            {'error': f'Cannot remove locked well {ew.well.name}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    ew.status = 'REMOVED'
    ew.save(update_fields=['status', 'updated_at'])

    ExecutionLog.objects.create(
        execution_schedule=ex,
        action='WELL_REMOVED',
        description=f'Well {ew.well.name} removed from execution',
        details={'exec_well_id': str(ew.id), 'well_name': ew.well.name, 'rig_name': ew.rig.name},
        performed_by=request.user,
    )

    ex.recalculate_metrics()
    return Response({'message': f'Well {ew.well.name} removed'})


@api_view(['POST'])
def sem_defer_well(request, execution_id):
    """Defer a well (only if not locked)"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    exec_well_id = request.data.get('exec_well_id')
    ew = get_object_or_404(ExecutionWell, id=exec_well_id, execution_schedule=ex)

    if ew.is_locked:
        return Response(
            {'error': f'Cannot defer locked well {ew.well.name}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    ew.status = 'DEFERRED'
    ew.save(update_fields=['status', 'updated_at'])

    ExecutionLog.objects.create(
        execution_schedule=ex,
        action='DEFERRED',
        description=f'Well {ew.well.name} deferred',
        details={'exec_well_id': str(ew.id), 'well_name': ew.well.name},
        performed_by=request.user,
    )

    return Response({'message': f'Well {ew.well.name} deferred'})


@api_view(['POST'])
def sem_update_remarks(request, execution_id):
    """Update remarks for a specific well"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    exec_well_id = request.data.get('exec_well_id')
    remarks = request.data.get('remarks', '').strip()
    
    ew = get_object_or_404(ExecutionWell, id=exec_well_id, execution_schedule=ex)
    
    if ew.is_locked:
        return Response(
            {'error': f'Cannot update remarks for locked well {ew.well.name}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    old_remarks = ew.notes
    ew.notes = remarks
    ew.save(update_fields=['notes', 'updated_at'])
    
    ExecutionLog.objects.create(
        execution_schedule=ex,
        action='REMARKS_UPDATED',
        description=f'Remarks updated for well {ew.well.name}',
        details={
            'exec_well_id': str(ew.id), 
            'well_name': ew.well.name,
            'old_remarks': old_remarks or '',
            'new_remarks': remarks,
        },
        performed_by=request.user,
    )
    
    return Response({
        'message': f'Remarks updated for {ew.well.name}',
        'remarks': remarks,
    })


@api_view(['POST'])
def sem_add_rig(request, execution_id):
    """Add a rig to execution schedule"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    rig_id = request.data.get('rig_id')
    rig = get_object_or_404(Rig, id=rig_id)

    er, created = ExecutionRig.objects.get_or_create(
        execution_schedule=ex, rig=rig,
        defaults={'is_active': True}
    )
    if not created and not er.is_active:
        er.is_active = True
        er.removed_at = None
        er.save(update_fields=['is_active', 'removed_at'])

    ExecutionLog.objects.create(
        execution_schedule=ex,
        action='RIG_ADDED',
        description=f'Rig {rig.name} added to execution',
        details={'rig_id': str(rig.id), 'rig_name': rig.name},
        performed_by=request.user,
    )

    return Response({'message': f'Rig {rig.name} added', 'is_new': created})


@api_view(['POST'])
def sem_remove_rig(request, execution_id):
    """Remove a rig — removes all future (unlocked) assignments, keeps locked wells"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    rig_id = request.data.get('rig_id')
    rig = get_object_or_404(Rig, id=rig_id)

    try:
        er = ExecutionRig.objects.get(execution_schedule=ex, rig=rig)
    except ExecutionRig.DoesNotExist:
        return Response({'error': 'Rig not in this execution'}, status=status.HTTP_400_BAD_REQUEST)

    # Check for locked wells on this rig
    locked_on_rig = ex.execution_wells.filter(rig=rig, is_locked=True).count()

    # Remove unlocked wells on this rig
    unlocked_wells = ex.execution_wells.filter(rig=rig, is_locked=False).exclude(status='REMOVED')
    removed_count = unlocked_wells.update(status='REMOVED')

    # Mark rig as inactive
    er.is_active = False
    er.removed_at = timezone.now()
    er.save(update_fields=['is_active', 'removed_at'])

    ExecutionLog.objects.create(
        execution_schedule=ex,
        action='RIG_REMOVED',
        description=f'Rig {rig.name} removed. {removed_count} unlocked wells removed. {locked_on_rig} locked wells preserved.',
        details={
            'rig_id': str(rig.id),
            'rig_name': rig.name,
            'wells_removed': removed_count,
            'locked_preserved': locked_on_rig,
        },
        performed_by=request.user,
    )

    ex.recalculate_metrics()
    return Response({
        'message': f'Rig {rig.name} removed',
        'wells_removed': removed_count,
        'locked_preserved': locked_on_rig,
    })


@api_view(['POST'])
def sem_replace_rig(request, execution_id):
    """
    Replace one rig with another in execution.
    All unlocked wells on the old rig are reassigned to the new rig.
    Locked wells remain on the old rig (it stays as inactive with those wells).
    """
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    if ex.status != 'ACTIVE':
        return Response({'error': 'Execution is not active'}, status=status.HTTP_400_BAD_REQUEST)

    old_rig_id = request.data.get('old_rig_id')
    new_rig_id = request.data.get('new_rig_id')
    if not old_rig_id or not new_rig_id:
        return Response({'error': 'Both old_rig_id and new_rig_id are required'}, status=status.HTTP_400_BAD_REQUEST)

    old_rig = get_object_or_404(Rig, id=old_rig_id)
    new_rig = get_object_or_404(Rig, id=new_rig_id)

    try:
        old_er = ExecutionRig.objects.get(execution_schedule=ex, rig=old_rig)
    except ExecutionRig.DoesNotExist:
        return Response({'error': f'Rig {old_rig.name} is not in this execution'}, status=status.HTTP_400_BAD_REQUEST)

    if old_rig_id == new_rig_id:
        return Response({'error': 'Old and new rig cannot be the same'}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        # Add the new rig to execution (or reactivate if previously removed)
        new_er, created = ExecutionRig.objects.get_or_create(
            execution_schedule=ex, rig=new_rig,
            defaults={'is_active': True}
        )
        if not created and not new_er.is_active:
            new_er.is_active = True
            new_er.removed_at = None
            new_er.save(update_fields=['is_active', 'removed_at'])

        # Reassign all unlocked, active wells from old rig to new rig
        wells_to_move = ex.execution_wells.filter(
            rig=old_rig, is_locked=False
        ).exclude(status__in=['REMOVED', 'DEFERRED'])
        moved_count = 0
        for ew in wells_to_move:
            ew.rig = new_rig
            ew.save(update_fields=['rig', 'updated_at'])
            moved_count += 1

        # Check for locked wells remaining on old rig
        locked_on_old = ex.execution_wells.filter(rig=old_rig, is_locked=True).exclude(status='REMOVED').count()

        # If no locked wells left on old rig, deactivate it
        if locked_on_old == 0:
            old_er.is_active = False
            old_er.removed_at = timezone.now()
            old_er.save(update_fields=['is_active', 'removed_at'])

        # Resequence wells on the new rig
        new_rig_wells = ex.execution_wells.filter(
            rig=new_rig
        ).exclude(status__in=['REMOVED', 'DEFERRED']).order_by('planned_start_date')
        for idx, ew in enumerate(new_rig_wells, 1):
            if ew.sequence_order != idx:
                ew.sequence_order = idx
                ew.save(update_fields=['sequence_order'])

        ExecutionLog.objects.create(
            execution_schedule=ex,
            action='RIG_REPLACED',
            description=f'Rig {old_rig.name} replaced by {new_rig.name}. {moved_count} wells reassigned. {locked_on_old} locked wells preserved on old rig.',
            details={
                'old_rig_id': str(old_rig.id), 'old_rig_name': old_rig.name,
                'new_rig_id': str(new_rig.id), 'new_rig_name': new_rig.name,
                'wells_moved': moved_count, 'locked_preserved': locked_on_old,
            },
            performed_by=request.user,
        )

        ex.recalculate_metrics()

    return Response({
        'message': f'Rig {old_rig.name} replaced by {new_rig.name}',
        'wells_moved': moved_count,
        'locked_preserved': locked_on_old,
        'old_rig_deactivated': locked_on_old == 0,
    })


@api_view(['POST'])
def sem_replace_well(request, execution_id):
    """
    Replace one well with another in execution.
    The old well is marked REMOVED and the new well takes its place
    (same rig, same sequence position, estimated dates).
    """
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    if ex.status != 'ACTIVE':
        return Response({'error': 'Execution is not active'}, status=status.HTTP_400_BAD_REQUEST)

    old_exec_well_id = request.data.get('old_exec_well_id')
    new_well_id = request.data.get('new_well_id')
    if not old_exec_well_id or not new_well_id:
        return Response({'error': 'Both old_exec_well_id and new_well_id are required'}, status=status.HTTP_400_BAD_REQUEST)

    old_ew = get_object_or_404(ExecutionWell, id=old_exec_well_id, execution_schedule=ex)

    if old_ew.is_locked:
        return Response({'error': f'Cannot replace locked well {old_ew.well.name}'}, status=status.HTTP_400_BAD_REQUEST)

    new_well = get_object_or_404(Well, id=new_well_id)

    # Check the new well isn't already in this execution (active)
    if ex.execution_wells.filter(well=new_well).exclude(status='REMOVED').exists():
        return Response({'error': f'Well {new_well.name} is already in this execution'}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        # Capture the old position
        rig = old_ew.rig
        seq = old_ew.sequence_order
        planned_start = old_ew.planned_start_date
        # Estimate new planned end based on new well duration
        planned_end = planned_start + timedelta(days=new_well.duration)
        planned_cost = new_well.duration * rig.daily_cost_inr

        # Remove old well
        old_well_name = old_ew.well.name
        old_ew.status = 'REMOVED'
        old_ew.save(update_fields=['status', 'updated_at'])

        # Create new execution well in the same slot
        new_ew = ExecutionWell.objects.create(
            execution_schedule=ex,
            well=new_well,
            rig=rig,
            planned_start_date=planned_start,
            planned_end_date=planned_end,
            status='PLANNED',
            sequence_order=seq,
            planned_drilling_cost=planned_cost,
        )

        ExecutionLog.objects.create(
            execution_schedule=ex,
            action='WELL_REPLACED',
            description=f'Well {old_well_name} replaced by {new_well.name} on rig {rig.name}',
            details={
                'old_well_name': old_well_name,
                'new_well_id': str(new_well.id), 'new_well_name': new_well.name,
                'rig_name': rig.name,
                'planned_start': str(planned_start), 'planned_end': str(planned_end),
            },
            performed_by=request.user,
        )

        ex.recalculate_metrics()

    return Response({
        'message': f'Well {old_well_name} replaced by {new_well.name}',
        'new_exec_well_id': str(new_ew.id),
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def sem_shift_dates(request, execution_id):
    """
    Smart date shifting — close gaps in the schedule without full re-optimization.
    For each active rig, orders wells by sequence, and cascades dates forward
    so that each well starts after the previous one ends (+ mobilization gap).
    Only affects unlocked wells; locked wells act as hard anchors.
    """
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    if ex.status != 'ACTIVE':
        return Response({'error': 'Execution is not active'}, status=status.HTTP_400_BAD_REQUEST)

    gap_days = int(request.data.get('gap_days', 1))  # days between wells (mobilization)
    total_shifted = 0

    with transaction.atomic():
        for er in ex.execution_rigs.filter(is_active=True).select_related('rig'):
            rig = er.rig
            wells = list(
                ex.execution_wells.filter(rig=rig)
                .exclude(status__in=['REMOVED', 'DEFERRED'])
                .order_by('sequence_order', 'planned_start_date')
                .select_related('well')
            )
            if not wells:
                continue

            # First pass: determine the anchor (earliest locked well or rig start)
            # We cascade forward from each anchor point
            cursor_date = None
            for ew in wells:
                if ew.is_locked:
                    # Locked well — use its actual/planned end as the new cursor
                    end = ew.actual_end_date or ew.planned_end_date
                    cursor_date = end + timedelta(days=gap_days)
                else:
                    if cursor_date is None:
                        # No prior anchor — use rig start date or current planned start
                        cursor_date = rig.start_date if rig.start_date else ew.planned_start_date

                    duration = ew.well.duration
                    new_start = cursor_date
                    new_end = new_start + timedelta(days=duration)

                    if ew.planned_start_date != new_start or ew.planned_end_date != new_end:
                        ew.planned_start_date = new_start
                        ew.planned_end_date = new_end
                        ew.planned_drilling_cost = duration * rig.daily_cost_inr
                        ew.save(update_fields=[
                            'planned_start_date', 'planned_end_date',
                            'planned_drilling_cost', 'updated_at'
                        ])
                        total_shifted += 1

                    cursor_date = new_end + timedelta(days=gap_days)

        # Re-sequence per rig
        for er in ex.execution_rigs.filter(is_active=True):
            rig_wells = ex.execution_wells.filter(
                rig=er.rig
            ).exclude(status__in=['REMOVED', 'DEFERRED']).order_by('planned_start_date')
            for idx, ew in enumerate(rig_wells, 1):
                if ew.sequence_order != idx:
                    ew.sequence_order = idx
                    ew.save(update_fields=['sequence_order'])

        ExecutionLog.objects.create(
            execution_schedule=ex,
            action='DATES_SHIFTED',
            description=f'Smart date shift: {total_shifted} wells adjusted, gap={gap_days}d',
            details={'wells_shifted': total_shifted, 'gap_days': gap_days},
            performed_by=request.user,
        )

        ex.recalculate_metrics()

    return Response({
        'message': f'{total_shifted} wells shifted to close gaps',
        'wells_shifted': total_shifted,
        'gap_days': gap_days,
    })


# =============================================================================
# API: CONTROLLED RE-OPTIMIZATION
# =============================================================================

@api_view(['POST'])
def sem_reoptimize(request, execution_id):
    """
    Re-optimize the execution schedule.
    Locked wells stay fixed. Only unlocked/future wells are re-optimized.
    """
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    if ex.status != 'ACTIVE':
        return Response({'error': 'Execution is not active'}, status=status.HTTP_400_BAD_REQUEST)

    time_limit = int(request.data.get('time_limit_seconds', 60))

    # Gather data
    locked_wells = list(ex.execution_wells.filter(is_locked=True).exclude(status='REMOVED').select_related('well', 'rig'))
    unlocked_wells = list(ex.execution_wells.filter(is_locked=False).exclude(status__in=['REMOVED', 'DEFERRED']).select_related('well', 'rig'))

    active_rigs = list(ex.execution_rigs.filter(is_active=True).select_related('rig'))

    if not unlocked_wells:
        return Response({'error': 'No unlocked wells to optimize'}, status=status.HTTP_400_BAD_REQUEST)

    # Build rigs data for optimizer
    rigs_data = []
    for er in active_rigs:
        r = er.rig
        rigs_data.append({
            'name': r.name,
            'rig_type': r.rig_type,
            'start_date': r.start_date,
            'end_date': r.end_date,
            'rig_capacity_hp': r.rig_capacity_hp,
            'daily_cost_inr': float(r.daily_cost_inr),
            'drilling_capacity_m': r.drilling_capacity_m,
            'mobilization_time_days': r.mobilization_time_days,
            'maintenance_schedule': r.maintenance_schedule,
            'crew_availability': r.crew_availability,
            'hpht_suitability': r.hpht_suitability,
            'ilm_cost_fixed': float(r.ilm_cost_fixed),
            'ilm_cost_per_km': float(r.ilm_cost_per_km),
            'ilm_cost_cluster': float(r.ilm_cost_cluster),
            'bop_stack': r.bop_stack,
            'tds_availability': r.tds_availability,
        })

    # Build wells data (both locked + unlocked for the optimizer)
    all_active_wells = locked_wells + unlocked_wells
    wells_data = []
    for ew in all_active_wells:
        w = ew.well
        wells_data.append({
            'name': w.name,
            'sn': w.sn,
            'asset_id': w.asset_id,
            'well_type': w.well_type,
            'well_profile': w.well_profile,
            'depth': w.depth,
            'rig_capacity_required_hp': w.rig_capacity_required_hp,
            'drl_days': w.drl_days,
            'pt_days': w.pt_days,
            'duration': w.duration,
            'latitude': float(w.latitude),
            'longitude': float(w.longitude),
            'rtd': w.rtd,
            'bop_stack': w.bop_stack,
            'tds_requirement': w.tds_requirement,
            'footprint': w.footprint,
            'preferred_rig': w.preferred_rig,
            'expected_potential': getattr(w, 'expected_potential', None),
            'priority': w.priority,
        })

    # Build fixed actuals from locked wells
    fixed_actuals = []
    for ew in locked_wells:
        actual_start = ew.actual_start_date or ew.planned_start_date
        actual_end = ew.actual_end_date or ew.planned_end_date
        fixed_actuals.append({
            'well': ew.well.name,
            'rig': ew.rig.name,
            'actual_start_date': actual_start,
            'actual_end_date': actual_end,
        })

    # Parse financial year
    fy_start_date = None
    fy_end_date = None
    if ex.financial_year:
        try:
            fy_start_date, fy_end_date = parse_financial_year(ex.financial_year)
        except ValueError:
            pass

    # Run optimizer
    try:
        scheduler = DrillingScheduler(rigs_data, wells_data, fy_start_date=fy_start_date, fy_end_date=fy_end_date)
        if fixed_actuals:
            results = scheduler.solve_with_actuals(fixed_actuals, time_limit_seconds=time_limit)
        else:
            results = scheduler.solve(time_limit_seconds=time_limit)
    except Exception as e:
        logger.error(f"SEM re-optimization failed: {e}")
        return Response({'error': f'Optimization failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if not results or results.get('status') not in ['OPTIMAL', 'FEASIBLE']:
        return Response({
            'error': f"No feasible solution: {results.get('status') if results else 'NO_RESULT'}",
        }, status=status.HTTP_400_BAD_REQUEST)

    # Apply results — update ONLY unlocked wells
    with transaction.atomic():
        # Build lookup of new assignments
        new_assignments = {}
        for ad in results.get('assignments', []):
            new_assignments[ad['well']] = ad

        rigs_by_name = {r.name: r for r in Rig.objects.filter(name__in=[er.rig.name for er in active_rigs])}

        # Update unlocked wells with new optimization results
        for ew in unlocked_wells:
            well_name = ew.well.name
            if well_name in new_assignments:
                ad = new_assignments[well_name]
                new_rig = rigs_by_name.get(ad['rig'])
                if new_rig:
                    ew.rig = new_rig
                ew.planned_start_date = ad['well_start_date']
                ew.planned_end_date = ad['well_end_date']
                ew.planned_drilling_cost = Decimal(str(ad.get('drilling_cost_inr', ad.get('drilling_cost', 0))))
                ew.planned_ilm_cost = Decimal(str(ad.get('ilm_cost', 0)))
                ew.sequence_order = ad.get('calculated_sequence_order', ew.sequence_order)
                ew.save()

        # Update execution schedule metrics
        ex.optimization_runs += 1
        ex.last_optimized_at = timezone.now()
        ex.save(update_fields=['optimization_runs', 'last_optimized_at', 'updated_at'])
        ex.recalculate_metrics()

        # Recompute sequence orders per rig
        for er in active_rigs:
            rig_wells = ex.execution_wells.filter(
                rig=er.rig
            ).exclude(status__in=['REMOVED', 'DEFERRED']).order_by('planned_start_date')
            for idx, ew in enumerate(rig_wells, 1):
                if ew.sequence_order != idx:
                    ew.sequence_order = idx
                    ew.save(update_fields=['sequence_order'])

        ExecutionLog.objects.create(
            execution_schedule=ex,
            action='REOPTIMIZED',
            description=f'Re-optimization run #{ex.optimization_runs}: {len(locked_wells)} locked, {len(unlocked_wells)} re-optimized',
            details={
                'locked_count': len(locked_wells),
                'unlocked_count': len(unlocked_wells),
                'solver_status': results.get('status'),
                'solve_time': results.get('solve_time_seconds'),
            },
            performed_by=request.user,
        )

    return Response({
        'message': f'Re-optimization complete. {len(unlocked_wells)} wells updated.',
        'solver_status': results.get('status'),
        'solve_time_seconds': results.get('solve_time_seconds'),
        'locked_count': len(locked_wells),
        'optimized_count': len(unlocked_wells),
        'optimization_run': ex.optimization_runs,
    })


# =============================================================================
# API: EXECUTION LOG
# =============================================================================

@api_view(['GET'])
def sem_execution_logs(request, execution_id):
    """Get audit logs for an execution schedule"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    logs = ex.logs.select_related('performed_by').all()[:100]

    data = [{
        'id': str(log.id),
        'action': log.action,
        'description': log.description,
        'details': log.details,
        'performed_by': log.performed_by.username if log.performed_by else None,
        'created_at': log.created_at.isoformat(),
    } for log in logs]

    return Response(data)


# =============================================================================
# API: STATUS UPDATE
# =============================================================================

@api_view(['POST'])
def sem_update_status(request, execution_id):
    """Update execution schedule status (ACTIVE/PAUSED/COMPLETED/CANCELLED)"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    new_status = request.data.get('status')

    valid_statuses = ['ACTIVE', 'PAUSED', 'COMPLETED', 'CANCELLED']
    if new_status not in valid_statuses:
        return Response({'error': f'Invalid status. Valid: {valid_statuses}'}, status=status.HTTP_400_BAD_REQUEST)

    old_status = ex.status
    ex.status = new_status
    ex.save(update_fields=['status', 'updated_at'])

    ExecutionLog.objects.create(
        execution_schedule=ex,
        action='STATUS_CHANGE',
        description=f'Status changed: {old_status} → {new_status}',
        details={'old_status': old_status, 'new_status': new_status},
        performed_by=request.user,
    )

    return Response({'message': f'Status updated to {new_status}', 'status': new_status})


# =============================================================================
# API: DELAY & COST ANALYTICS
# =============================================================================

@api_view(['GET'])
def sem_analytics(request, execution_id):
    """Comprehensive delay, cost, and variance analytics"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    wells = ex.execution_wells.select_related('well', 'rig').exclude(status='REMOVED')

    # Per-well delay analysis
    well_delays = []
    total_delay = 0
    total_planned_cost = Decimal('0')
    total_actual_cost = Decimal('0')
    total_planned_days = 0
    total_actual_days = 0

    for w in wells:
        planned_days = w.planned_duration_days
        actual_days = w.actual_duration_days
        delay = w.delay_days
        cost_var = w.cost_variance
        total_planned_cost += w.planned_drilling_cost
        total_actual_cost += w.actual_drilling_cost
        total_planned_days += planned_days
        if actual_days is not None:
            total_actual_days += actual_days
        total_delay += delay

        well_delays.append({
            'well_name': w.well.name,
            'rig_name': w.rig.name,
            'status': w.status,
            'planned_start': w.planned_start_date.isoformat(),
            'planned_end': w.planned_end_date.isoformat(),
            'actual_start': w.actual_start_date.isoformat() if w.actual_start_date else None,
            'actual_end': w.actual_end_date.isoformat() if w.actual_end_date else None,
            'planned_days': planned_days,
            'actual_days': actual_days,
            'delay_days': delay,
            'planned_cost': float(w.planned_drilling_cost),
            'actual_cost': float(w.actual_drilling_cost),
            'cost_variance': cost_var,
        })

    # Rig idle time analysis
    rig_idle = []
    for er in ex.execution_rigs.filter(is_active=True).select_related('rig'):
        rig_wells = wells.filter(rig=er.rig).order_by('planned_start_date')
        idle_days = 0
        prev_end = None
        for w in rig_wells:
            well_start = w.actual_start_date or w.planned_start_date
            if prev_end and well_start > prev_end:
                idle_days += (well_start - prev_end).days
            prev_end = w.actual_end_date or w.planned_end_date

        rig_idle.append({
            'rig_name': er.rig.name,
            'idle_days': idle_days,
            'well_count': rig_wells.count(),
            'idle_cost': float(idle_days * er.rig.daily_cost_inr),
        })

    return Response({
        'well_delays': well_delays,
        'rig_idle_time': rig_idle,
        'summary': {
            'total_delay_days': total_delay,
            'total_planned_cost': float(total_planned_cost),
            'total_actual_cost': float(total_actual_cost),
            'cost_variance': float(total_actual_cost - total_planned_cost),
            'total_planned_days': total_planned_days,
            'total_actual_days': total_actual_days,
            'schedule_variance_pct': round(
                (total_delay / total_planned_days * 100) if total_planned_days else 0, 1
            ),
            'cost_variance_pct': round(
                (float(total_actual_cost - total_planned_cost) / float(total_planned_cost) * 100)
                if total_planned_cost else 0, 1
            ),
            'total_rig_idle_days': sum(r['idle_days'] for r in rig_idle),
            'total_idle_cost': sum(r['idle_cost'] for r in rig_idle),
        },
    })


# =============================================================================
# API: SCENARIO MANAGEMENT (WHAT-IF ANALYSIS)
# =============================================================================

def _snapshot_execution(ex):
    """Create a JSON-serializable snapshot of the current execution state."""
    wells = []
    for ew in ex.execution_wells.select_related('well', 'rig').exclude(status='REMOVED'):
        wells.append({
            'exec_well_id': str(ew.id),
            'well_id': str(ew.well.id),
            'well_name': ew.well.name,
            'rig_id': str(ew.rig.id),
            'rig_name': ew.rig.name,
            'status': ew.status,
            'is_locked': ew.is_locked,
            'sequence_order': ew.sequence_order,
            'planned_start': str(ew.planned_start_date),
            'planned_end': str(ew.planned_end_date),
            'actual_start': str(ew.actual_start_date) if ew.actual_start_date else None,
            'actual_end': str(ew.actual_end_date) if ew.actual_end_date else None,
            'planned_drilling_cost': float(ew.planned_drilling_cost),
            'planned_ilm_cost': float(ew.planned_ilm_cost),
            'notes': ew.notes,
        })

    rigs = []
    for er in ex.execution_rigs.select_related('rig'):
        rigs.append({
            'exec_rig_id': str(er.id),
            'rig_id': str(er.rig.id),
            'rig_name': er.rig.name,
            'is_active': er.is_active,
            'rig_type': er.rig.rig_type,
            'daily_cost': float(er.rig.daily_cost_inr),
        })

    # Summary metrics
    from django.db.models import Max, Sum
    agg = ex.execution_wells.exclude(status='REMOVED').aggregate(
        total_cost=Sum('planned_drilling_cost'),
        max_end=Max('planned_end_date'),
    )
    total_cost = float(agg['total_cost'] or 0)
    end_date = str(agg['max_end']) if agg['max_end'] else None
    active_well_count = ex.execution_wells.exclude(status__in=['REMOVED', 'DEFERRED']).count()

    return {
        'rigs': rigs,
        'wells': wells,
        'metrics': {
            'total_cost': total_cost,
            'end_date': end_date,
            'active_well_count': active_well_count,
            'active_rig_count': ex.execution_rigs.filter(is_active=True).count(),
            'locked_count': ex.execution_wells.filter(is_locked=True).exclude(status='REMOVED').count(),
        },
    }


@api_view(['POST'])
def sem_create_scenario(request, execution_id):
    """
    Create a what-if scenario snapshot of the current execution state.
    The user can then make changes and compare scenarios.
    """
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    name = request.data.get('name', '').strip()
    description = request.data.get('description', '').strip()

    if not name:
        name = f'Scenario {ex.scenarios.count() + 1} — {timezone.now().strftime("%d %b %Y %H:%M")}'

    snapshot = _snapshot_execution(ex)

    scenario = ExecutionScenario.objects.create(
        execution_schedule=ex,
        name=name,
        description=description,
        snapshot=snapshot,
        total_cost=Decimal(str(snapshot['metrics']['total_cost'])),
        total_duration_days=(
            (date.fromisoformat(snapshot['metrics']['end_date']) - date.today()).days
            if snapshot['metrics']['end_date'] else 0
        ),
        end_date=snapshot['metrics']['end_date'],
        created_by=request.user,
    )

    ExecutionLog.objects.create(
        execution_schedule=ex,
        action='SCENARIO_CREATED',
        description=f'Scenario "{name}" created',
        details={'scenario_id': str(scenario.id), 'name': name},
        performed_by=request.user,
    )

    return Response({
        'message': f'Scenario "{name}" created',
        'scenario_id': str(scenario.id),
        'name': name,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def sem_list_scenarios(request, execution_id):
    """List all scenarios for this execution schedule."""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    scenarios = ex.scenarios.select_related('created_by').all()

    data = [{
        'id': str(s.id),
        'name': s.name,
        'description': s.description,
        'is_optimized': s.is_optimized,
        'solver_status': s.solver_status,
        'total_cost': float(s.total_cost),
        'total_duration_days': s.total_duration_days,
        'end_date': str(s.end_date) if s.end_date else None,
        'well_count': len(s.snapshot.get('wells', [])),
        'rig_count': len([r for r in s.snapshot.get('rigs', []) if r.get('is_active')]),
        'created_by': s.created_by.username if s.created_by else None,
        'created_at': s.created_at.isoformat(),
    } for s in scenarios]

    return Response(data)


@api_view(['GET'])
def sem_scenario_detail(request, execution_id, scenario_id):
    """Get full detail of a scenario including its snapshot."""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    scenario = get_object_or_404(ExecutionScenario, id=scenario_id, execution_schedule=ex)

    return Response({
        'id': str(scenario.id),
        'name': scenario.name,
        'description': scenario.description,
        'is_optimized': scenario.is_optimized,
        'solver_status': scenario.solver_status,
        'total_cost': float(scenario.total_cost),
        'end_date': str(scenario.end_date) if scenario.end_date else None,
        'snapshot': scenario.snapshot,
        'created_by': scenario.created_by.username if scenario.created_by else None,
        'created_at': scenario.created_at.isoformat(),
    })


@api_view(['GET'])
def sem_compare_scenarios(request, execution_id):
    """
    Compare two scenarios side-by-side, or compare a scenario with current state.
    Query params: scenario_a, scenario_b (UUIDs). If scenario_b is 'current', compare with live execution.
    """
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    scenario_a_id = request.query_params.get('scenario_a')
    scenario_b_id = request.query_params.get('scenario_b', 'current')

    if not scenario_a_id:
        return Response({'error': 'scenario_a is required'}, status=status.HTTP_400_BAD_REQUEST)

    scenario_a = get_object_or_404(ExecutionScenario, id=scenario_a_id, execution_schedule=ex)
    snap_a = scenario_a.snapshot

    if scenario_b_id == 'current':
        snap_b = _snapshot_execution(ex)
        name_b = 'Current State'
    else:
        scenario_b = get_object_or_404(ExecutionScenario, id=scenario_b_id, execution_schedule=ex)
        snap_b = scenario_b.snapshot
        name_b = scenario_b.name

    # Build comparison
    def _well_map(snap):
        return {w['well_name']: w for w in snap.get('wells', [])}

    wells_a = _well_map(snap_a)
    wells_b = _well_map(snap_b)
    all_wells = sorted(set(list(wells_a.keys()) + list(wells_b.keys())))

    comparison = []
    for wn in all_wells:
        wa = wells_a.get(wn)
        wb = wells_b.get(wn)
        entry = {'well_name': wn}
        if wa and wb:
            entry['in_a'] = True
            entry['in_b'] = True
            entry['rig_a'] = wa['rig_name']
            entry['rig_b'] = wb['rig_name']
            entry['start_a'] = wa['planned_start']
            entry['start_b'] = wb['planned_start']
            entry['end_a'] = wa['planned_end']
            entry['end_b'] = wb['planned_end']
            entry['cost_a'] = wa['planned_drilling_cost']
            entry['cost_b'] = wb['planned_drilling_cost']
            entry['rig_changed'] = wa['rig_name'] != wb['rig_name']
            entry['dates_changed'] = wa['planned_start'] != wb['planned_start'] or wa['planned_end'] != wb['planned_end']
        elif wa:
            entry['in_a'] = True
            entry['in_b'] = False
            entry['rig_a'] = wa['rig_name']
            entry['start_a'] = wa['planned_start']
            entry['end_a'] = wa['planned_end']
            entry['cost_a'] = wa['planned_drilling_cost']
        else:
            entry['in_a'] = False
            entry['in_b'] = True
            entry['rig_b'] = wb['rig_name']
            entry['start_b'] = wb['planned_start']
            entry['end_b'] = wb['planned_end']
            entry['cost_b'] = wb['planned_drilling_cost']
        comparison.append(entry)

    return Response({
        'scenario_a': {'id': str(scenario_a.id), 'name': scenario_a.name, 'metrics': snap_a.get('metrics', {})},
        'scenario_b': {'id': scenario_b_id, 'name': name_b, 'metrics': snap_b.get('metrics', {})},
        'well_comparison': comparison,
    })


@api_view(['POST'])
def sem_apply_scenario(request, execution_id, scenario_id):
    """
    Apply a scenario — restore the execution state from the scenario's snapshot.
    Only unlocked wells are updated; locked wells are preserved as-is.
    """
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    if ex.status != 'ACTIVE':
        return Response({'error': 'Execution is not active'}, status=status.HTTP_400_BAD_REQUEST)

    scenario = get_object_or_404(ExecutionScenario, id=scenario_id, execution_schedule=ex)
    snap = scenario.snapshot

    with transaction.atomic():
        # Build lookup of snapshot wells
        snap_wells = {w['well_name']: w for w in snap.get('wells', [])}
        snap_rigs = {r['rig_name']: r for r in snap.get('rigs', [])}

        # Rig updates: activate/deactivate based on snapshot
        for r_data in snap.get('rigs', []):
            try:
                rig = Rig.objects.get(id=r_data['rig_id'])
                er, _ = ExecutionRig.objects.get_or_create(
                    execution_schedule=ex, rig=rig,
                    defaults={'is_active': r_data['is_active']}
                )
                if er.is_active != r_data['is_active']:
                    er.is_active = r_data['is_active']
                    er.removed_at = timezone.now() if not r_data['is_active'] else None
                    er.save(update_fields=['is_active', 'removed_at'])
            except Rig.DoesNotExist:
                continue

        # Well updates: only update unlocked wells
        updated_count = 0
        for ew in ex.execution_wells.select_related('well', 'rig').all():
            if ew.is_locked:
                continue  # Skip locked wells
            wn = ew.well.name
            if wn in snap_wells:
                sw = snap_wells[wn]
                try:
                    new_rig = Rig.objects.get(id=sw['rig_id'])
                except Rig.DoesNotExist:
                    new_rig = ew.rig
                ew.rig = new_rig
                ew.planned_start_date = date.fromisoformat(sw['planned_start'])
                ew.planned_end_date = date.fromisoformat(sw['planned_end'])
                ew.sequence_order = sw['sequence_order']
                ew.planned_drilling_cost = Decimal(str(sw['planned_drilling_cost']))
                ew.planned_ilm_cost = Decimal(str(sw['planned_ilm_cost']))
                ew.status = sw['status'] if sw['status'] != 'REMOVED' else 'PLANNED'
                ew.save()
                updated_count += 1
            else:
                # Well not in scenario — mark as removed
                ew.status = 'REMOVED'
                ew.save(update_fields=['status', 'updated_at'])

        ExecutionLog.objects.create(
            execution_schedule=ex,
            action='SCENARIO_APPLIED',
            description=f'Scenario "{scenario.name}" applied. {updated_count} wells updated.',
            details={'scenario_id': str(scenario.id), 'scenario_name': scenario.name, 'wells_updated': updated_count},
            performed_by=request.user,
        )

        ex.recalculate_metrics()

    return Response({
        'message': f'Scenario "{scenario.name}" applied. {updated_count} wells updated.',
        'wells_updated': updated_count,
    })


@api_view(['DELETE'])
def sem_delete_scenario(request, execution_id, scenario_id):
    """Delete a scenario."""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    scenario = get_object_or_404(ExecutionScenario, id=scenario_id, execution_schedule=ex)
    name = scenario.name
    scenario.delete()
    return Response({'message': f'Scenario "{name}" deleted'})


# =============================================================================
# API: AVAILABLE RIGS AND WELLS FOR ADDING
# =============================================================================

@api_view(['GET'])
def sem_available_wells(request, execution_id):
    """Get wells available to add to this execution (not already in it)"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    existing_well_ids = ex.execution_wells.exclude(status='REMOVED').values_list('well_id', flat=True)

    qs = Well.objects.exclude(id__in=existing_well_ids)
    if ex.location:
        qs = qs.filter(location=ex.location)

    data = [{
        'id': str(w.id),
        'name': w.name,
        'sn': w.sn,
        'well_type': w.well_type,
        'depth': w.depth,
        'duration': w.duration,
        'priority': w.priority,
        'asset_id': w.asset_id,
    } for w in qs[:100]]
    return Response(data)


@api_view(['GET'])
def sem_available_rigs(request, execution_id):
    """Get rigs available to add to this execution"""
    ex = get_object_or_404(ExecutionSchedule, id=execution_id)
    existing_rig_ids = ex.execution_rigs.filter(is_active=True).values_list('rig_id', flat=True)

    qs = Rig.objects.exclude(id__in=existing_rig_ids)
    if ex.location:
        qs = qs.filter(location=ex.location)

    data = [{
        'id': str(r.id),
        'name': r.name,
        'rig_type': r.rig_type,
        'rig_capacity_hp': r.rig_capacity_hp,
        'daily_cost_inr': float(r.daily_cost_inr),
        'start_date': r.start_date.isoformat(),
        'end_date': r.end_date.isoformat(),
    } for r in qs[:50]]
    return Response(data)
