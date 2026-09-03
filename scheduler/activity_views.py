"""
Activity Tracking Views
API endpoints and template view for the User Activity module.
Admin-only access to view all user activity logs.
"""

import logging
from datetime import datetime, timedelta
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .models import UserActivity

logger = logging.getLogger(__name__)


# =============================================================================
# TEMPLATE VIEW
# =============================================================================

@staff_member_required
def activity_dashboard(request):
    """Main activity tracking dashboard - admin only."""
    return render(request, 'scheduler/activity_dashboard.html')


# =============================================================================
# API ENDPOINTS
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAdminUser])
def activity_list(request):
    """
    List activity logs with filtering, search and pagination.
    
    Query params:
        - page (int): Page number, default 1
        - page_size (int): Items per page, default 50, max 200
        - category (str): Filter by category
        - user (str): Filter by username (partial match)
        - ip (str): Filter by IP address
        - action (str): Search in action text
        - severity (str): Filter by severity
        - target_model (str): Filter by target model
        - date_from (str): Start date YYYY-MM-DD
        - date_to (str): End date YYYY-MM-DD
        - search (str): Global search across action, description, username, IP
    """
    qs = UserActivity.objects.select_related('user').all()

    # Filters
    category = request.query_params.get('category')
    if category:
        qs = qs.filter(category=category)

    username = request.query_params.get('user')
    if username:
        qs = qs.filter(username__icontains=username)

    ip_addr = request.query_params.get('ip')
    if ip_addr:
        qs = qs.filter(ip_address__icontains=ip_addr)

    severity = request.query_params.get('severity')
    if severity:
        qs = qs.filter(severity=severity)

    target_model = request.query_params.get('target_model')
    if target_model:
        qs = qs.filter(target_model__icontains=target_model)

    date_from = request.query_params.get('date_from')
    if date_from:
        try:
            dt = datetime.strptime(date_from, '%Y-%m-%d')
            qs = qs.filter(created_at__date__gte=dt.date())
        except ValueError:
            pass

    date_to = request.query_params.get('date_to')
    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d')
            qs = qs.filter(created_at__date__lte=dt.date())
        except ValueError:
            pass

    search = request.query_params.get('search')
    if search:
        qs = qs.filter(
            Q(action__icontains=search) |
            Q(description__icontains=search) |
            Q(username__icontains=search) |
            Q(ip_address__icontains=search) |
            Q(target_name__icontains=search) |
            Q(request_path__icontains=search)
        )

    # Pagination
    page = int(request.query_params.get('page', 1))
    page_size = min(int(request.query_params.get('page_size', 50)), 200)
    total = qs.count()
    offset = (page - 1) * page_size
    activities = qs[offset:offset + page_size]

    data = []
    for a in activities:
        data.append({
            'id': str(a.id),
            'user': a.username,
            'user_id': a.user_id,
            'category': a.category,
            'category_display': a.get_category_display(),
            'action': a.action,
            'description': a.description,
            'severity': a.severity,
            'ip_address': a.ip_address,
            'user_agent': a.user_agent[:200] if a.user_agent else '',
            'request_method': a.request_method,
            'request_path': a.request_path,
            'target_model': a.target_model,
            'target_id': a.target_id,
            'target_name': a.target_name,
            'metadata': a.metadata,
            'session_key': a.session_key[:12] + '...' if a.session_key else '',
            'created_at': a.created_at.isoformat(),
        })

    return Response({
        'results': data,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size,
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def activity_stats(request):
    """
    Dashboard statistics and summary data.
    
    Query params:
        - days (int): Number of days to look back, default 30
    """
    days = int(request.query_params.get('days', 30))
    since = timezone.now() - timedelta(days=days)
    qs = UserActivity.objects.filter(created_at__gte=since)

    # Total counts
    total_activities = qs.count()
    total_logins = qs.filter(category='AUTH', action='User Login').count()
    failed_logins = qs.filter(category='AUTH', action='Login Failed').count()
    unique_users = qs.exclude(username='').values('username').distinct().count()
    unique_ips = qs.exclude(ip_address__isnull=True).values('ip_address').distinct().count()

    # Category breakdown
    category_counts = list(
        qs.values('category').annotate(count=Count('id')).order_by('-count')
    )

    # Severity breakdown
    severity_counts = list(
        qs.values('severity').annotate(count=Count('id')).order_by('-count')
    )

    # Top users by activity
    top_users = list(
        qs.exclude(username='').values('username')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )

    # Top IP addresses
    top_ips = list(
        qs.exclude(ip_address__isnull=True).values('ip_address')
        .annotate(
            count=Count('id'),
        )
        .order_by('-count')[:10]
    )
    
    # Enrich IPs with associated usernames
    for ip_entry in top_ips:
        usernames = list(
            qs.filter(ip_address=ip_entry['ip_address'])
            .exclude(username='')
            .values_list('username', flat=True)
            .distinct()[:5]
        )
        ip_entry['users'] = usernames

    # Activity over time (daily for last N days)
    daily_activity = list(
        qs.annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(count=Count('id'))
        .order_by('date')
    )
    for item in daily_activity:
        item['date'] = item['date'].isoformat()

    # Hourly distribution (for today)
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    hourly_activity = list(
        qs.filter(created_at__gte=today_start)
        .annotate(hour=TruncHour('created_at'))
        .values('hour')
        .annotate(count=Count('id'))
        .order_by('hour')
    )
    for item in hourly_activity:
        item['hour'] = item['hour'].isoformat()

    # Recent failed logins  
    recent_failures = list(
        qs.filter(category='AUTH', action='Login Failed')
        .order_by('-created_at')[:10]
        .values('ip_address', 'created_at', 'metadata')
    )
    for f in recent_failures:
        f['created_at'] = f['created_at'].isoformat()

    # Most accessed pages
    top_pages = list(
        qs.filter(category='PAGE_VIEW')
        .values('action')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )

    # User-IP mapping (which users logged in from which IPs)
    user_ip_map = list(
        qs.filter(category='AUTH', action='User Login')
        .values('username', 'ip_address')
        .annotate(count=Count('id'))
        .order_by('-count')[:20]
    )

    return Response({
        'period_days': days,
        'total_activities': total_activities,
        'total_logins': total_logins,
        'failed_logins': failed_logins,
        'unique_users': unique_users,
        'unique_ips': unique_ips,
        'category_counts': category_counts,
        'severity_counts': severity_counts,
        'top_users': top_users,
        'top_ips': top_ips,
        'daily_activity': daily_activity,
        'hourly_activity': hourly_activity,
        'recent_failures': recent_failures,
        'top_pages': top_pages,
        'user_ip_map': user_ip_map,
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def activity_user_detail(request, username):
    """
    Get detailed activity for a specific user.
    """
    days = int(request.query_params.get('days', 30))
    since = timezone.now() - timedelta(days=days)
    qs = UserActivity.objects.filter(username=username, created_at__gte=since)

    # User summary
    total = qs.count()
    last_login = qs.filter(action='User Login').order_by('-created_at').first()
    ips_used = list(
        qs.exclude(ip_address__isnull=True)
        .values('ip_address')
        .annotate(count=Count('id'), last_seen=Max('created_at'))
        .order_by('-last_seen')
    )
    for ip in ips_used:
        ip['last_seen'] = ip['last_seen'].isoformat()

    category_breakdown = list(
        qs.values('category').annotate(count=Count('id')).order_by('-count')
    )

    # Recent activity
    recent = list(
        qs.order_by('-created_at')[:50].values(
            'id', 'category', 'action', 'description', 'severity',
            'ip_address', 'request_path', 'target_model', 'target_name',
            'created_at'
        )
    )
    for r in recent:
        r['id'] = str(r['id'])
        r['created_at'] = r['created_at'].isoformat()

    return Response({
        'username': username,
        'period_days': days,
        'total_activities': total,
        'last_login': last_login.created_at.isoformat() if last_login else None,
        'last_login_ip': last_login.ip_address if last_login else None,
        'ips_used': ips_used,
        'category_breakdown': category_breakdown,
        'recent_activity': recent,
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def activity_ip_detail(request, ip_address):
    """
    Get detailed activity for a specific IP address.
    """
    days = int(request.query_params.get('days', 30))
    since = timezone.now() - timedelta(days=days)
    qs = UserActivity.objects.filter(ip_address=ip_address, created_at__gte=since)

    total = qs.count()
    users = list(
        qs.exclude(username='')
        .values('username')
        .annotate(count=Count('id'), last_seen=Max('created_at'))
        .order_by('-last_seen')
    )
    for u in users:
        u['last_seen'] = u['last_seen'].isoformat()

    category_breakdown = list(
        qs.values('category').annotate(count=Count('id')).order_by('-count')
    )

    recent = list(
        qs.order_by('-created_at')[:50].values(
            'id', 'username', 'category', 'action', 'description',
            'severity', 'request_path', 'created_at'
        )
    )
    for r in recent:
        r['id'] = str(r['id'])
        r['created_at'] = r['created_at'].isoformat()

    return Response({
        'ip_address': ip_address,
        'period_days': days,
        'total_activities': total,
        'users': users,
        'category_breakdown': category_breakdown,
        'recent_activity': recent,
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def activity_cleanup(request):
    """
    Delete old activity logs. 
    Body: { "older_than_days": 90 }
    """
    older_than_days = request.data.get('older_than_days', 90)
    if older_than_days < 7:
        return Response({'error': 'Minimum retention is 7 days'}, status=400)

    cutoff = timezone.now() - timedelta(days=older_than_days)
    count, _ = UserActivity.objects.filter(created_at__lt=cutoff).delete()

    UserActivity.log(
        request=request,
        category='ADMIN',
        action='Activity Log Cleanup',
        description=f'Deleted {count} activity records older than {older_than_days} days',
        severity='WARNING',
        metadata={'deleted_count': count, 'older_than_days': older_than_days},
    )

    return Response({
        'message': f'Deleted {count} records older than {older_than_days} days',
        'deleted_count': count,
    })
