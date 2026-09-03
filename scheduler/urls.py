from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import sem_views
from . import activity_views

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'rigs', views.RigViewSet)
router.register(r'wells', views.WellViewSet)
router.register(r'schedules', views.ScheduleViewSet)
router.register(r'assignments', views.AssignmentViewSet)

# The API URLs are now determined automatically by the router
urlpatterns = [
    path('', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('about/', views.about, name='about'),
    path('tutorials/', views.video_tutorials, name='video_tutorials'),
    path('tutorials/<uuid:tutorial_id>/', views.video_tutorial_detail, name='video_tutorial_detail'),
    path('tutorials/<uuid:tutorial_id>/stream/', views.stream_video_file, name='stream_video_file'),
    # HLS streaming endpoints for adaptive bitrate streaming
    path('tutorials/<uuid:tutorial_id>/hls/master.m3u8', views.stream_hls_master, name='stream_hls_master'),
    path('tutorials/<uuid:tutorial_id>/hls/<str:quality>/playlist.m3u8', views.stream_hls_playlist, name='stream_hls_playlist'),
    path('tutorials/<uuid:tutorial_id>/hls/<str:quality>/<str:segment>', views.stream_hls_segment, name='stream_hls_segment'),
    path('showcase/', views.product_showcase, name='product_showcase'),
    path('data/', views.data_management, name='data_management'),
    path('user-management/', views.user_management, name='user_management'),
    path('company-codes/', views.company_codes, name='company_codes'),
    path('scheduling/', views.scheduling, name='scheduling'),
    path('schedules/', views.schedules_list, name='schedules_list'),
    path('gantt/', views.interactive_gantt, name='interactive_gantt'),
    path('er-diagram/', views.er_diagram, name='er_diagram'),
    path('schedule-maps/', views.schedule_maps, name='schedule_maps'),
    path('well-upload/', views.well_upload, name='well_upload'),
    path('staged-wells/', views.staged_wells_management, name='staged_wells_management'),
    path('view-all-rigs/', views.view_all_rigs, name='view_all_rigs'),
    path('view-all-wells/', views.view_all_wells, name='view_all_wells'),
    path('test-appsense/', views.test_appsense, name='test_appsense'),
    path('api/get-appsense-url/', views.get_appsense_url, name='get_appsense_url'),
    path('schedule/<uuid:schedule_id>/', views.schedule_detail, name='schedule_detail'),
    path('schedule/compare/', views.schedule_comparison, name='schedule_comparison'),
    path('api/', include(router.urls)),
    path('api/bulk-upload/', views.bulk_upload_unified, name='bulk_upload_unified'),
    path('api/well-csv-upload/', views.well_csv_upload, name='well_csv_upload'),
    
    # Staged Wells API endpoints
    path('api/staged-wells/', views.get_staged_wells, name='get_staged_wells'),
    path('api/staged-wells/<uuid:staged_well_id>/', views.get_staged_well_detail, name='get_staged_well_detail'),
    path('api/staged-wells/<uuid:staged_well_id>/update/', views.update_staged_well, name='update_staged_well'),
    path('api/staged-wells/<uuid:staged_well_id>/finalize/', views.finalize_staged_well, name='finalize_staged_well'),
    path('api/staged-wells/finalize-all/', views.finalize_all_staged_wells, name='finalize_all_staged_wells'),
    path('api/staged-wells/bulk-set-rtd/', views.bulk_set_rtd_staged_wells, name='bulk_set_rtd_staged_wells'),
    path('api/staged-wells/bulk-update/', views.bulk_update_staged_wells, name='bulk_update_staged_wells'),
    path('api/staged-wells/<uuid:staged_well_id>/delete/', views.delete_staged_well, name='delete_staged_well'),
    path('api/staged-wells/bulk-delete/', views.bulk_delete_staged_wells, name='bulk_delete_staged_wells'),
    
    # Well Baskets Management
    path('baskets/', views.basket_creation_page, name='basket_creation'),
    path('api/baskets/', views.get_baskets, name='get_baskets'),
    path('api/baskets/<uuid:basket_id>/', views.get_basket_detail, name='get_basket_detail'),
    path('api/baskets/search-wells/', views.search_wells_for_basket, name='search_wells_for_basket'),
    path('api/baskets/create/', views.create_basket, name='create_basket'),
    path('api/baskets/<uuid:basket_id>/update/', views.update_basket, name='update_basket'),
    path('api/baskets/<uuid:basket_id>/delete/', views.delete_basket, name='delete_basket'),
    path('api/baskets/<uuid:basket_id>/wells/<uuid:well_id>/remove/', views.remove_well_from_basket, name='remove_well_from_basket'),
    path('api/baskets/<uuid:basket_id>/wells/add/', views.add_wells_to_basket, name='add_wells_to_basket'),
    path('api/baskets/<uuid:basket_id>/finalize/', views.finalize_basket_wells, name='finalize_basket_wells'),
    
    # Benchmark Management
    path('benchmarks/', views.benchmark_management, name='benchmark_management'),
    path('api/benchmarks/', views.get_benchmarks, name='get_benchmarks'),
    path('api/benchmarks/create/', views.create_benchmark, name='create_benchmark'),
    path('api/benchmarks/<uuid:benchmark_id>/update/', views.update_benchmark, name='update_benchmark'),
    path('api/benchmarks/<uuid:benchmark_id>/delete/', views.delete_benchmark, name='delete_benchmark'),
    
    # Rig Building Norms Management
    path('rig-norms/', views.rig_norms_management, name='rig_norms_management'),
    path('api/rig-norms/', views.get_rig_norms, name='get_rig_norms'),
    path('api/rig-norms/create/', views.create_rig_norm, name='create_rig_norm'),
    path('api/rig-norms/<uuid:norm_id>/update/', views.update_rig_norm, name='update_rig_norm'),
    path('api/rig-norms/<uuid:norm_id>/delete/', views.delete_rig_norm, name='delete_rig_norm'),
    path('api/rig-norms/map-rigs/', views.map_rigs_to_norms, name='map_rigs_to_norms'),
    path('api/rig-norms/save-mappings/', views.save_rig_norm_mappings, name='save_rig_norm_mappings'),
    
    # Rig Building Adjustment Rules API
    path('api/rig-adjustments/', views.get_rig_adjustments, name='get_rig_adjustments'),
    path('api/rig-adjustments/create/', views.create_rig_adjustment, name='create_rig_adjustment'),
    path('api/rig-adjustments/<uuid:adjustment_id>/update/', views.update_rig_adjustment, name='update_rig_adjustment'),
    path('api/rig-adjustments/<uuid:adjustment_id>/delete/', views.delete_rig_adjustment, name='delete_rig_adjustment'),
    
    # Daily Drilling Rate Management
    path('daily-drilling-rates/', views.daily_drilling_rate_management, name='daily_drilling_rate_management'),
    path('api/daily-drilling-rates/', views.get_daily_drilling_rates, name='get_daily_drilling_rates'),
    path('api/daily-drilling-rates/create/', views.create_daily_drilling_rate, name='create_daily_drilling_rate'),
    path('api/daily-drilling-rates/<uuid:rate_id>/update/', views.update_daily_drilling_rate, name='update_daily_drilling_rate'),
    path('api/daily-drilling-rates/<uuid:rate_id>/delete/', views.delete_daily_drilling_rate, name='delete_daily_drilling_rate'),
    
    # Location-Field Combinations Management
    path('api/location-field-combinations/', views.get_location_field_combinations, name='get_location_field_combinations'),
    path('api/location-field-combinations/update/', views.update_location_field_combination, name='update_location_field_combination'),
    
    # Additional Ops Drilling Management
    path('additional-ops/', views.additional_ops_drilling_management, name='additional_ops_drilling_management'),
    path('api/coring-norms/', views.get_coring_norms, name='get_coring_norms'),
    path('api/coring-norms/create/', views.create_coring_norm, name='create_coring_norm'),
    path('api/coring-norms/<uuid:norm_id>/update/', views.update_coring_norm, name='update_coring_norm'),
    path('api/coring-norms/<uuid:norm_id>/delete/', views.delete_coring_norm, name='delete_coring_norm'),
    path('api/casing-norms/', views.get_casing_norms, name='get_casing_norms'),
    path('api/casing-norms/create/', views.create_casing_norm, name='create_casing_norm'),
    path('api/casing-norms/<uuid:norm_id>/update/', views.update_casing_norm, name='update_casing_norm'),
    path('api/casing-norms/<uuid:norm_id>/delete/', views.delete_casing_norm, name='delete_casing_norm'),
    path('api/hermetical-testing-norms/', views.get_hermetical_testing_norms, name='get_hermetical_testing_norms'),
    path('api/hermetical-testing-norms/create/', views.create_hermetical_testing_norm, name='create_hermetical_testing_norm'),
    path('api/hermetical-testing-norms/<uuid:norm_id>/update/', views.update_hermetical_testing_norm, name='update_hermetical_testing_norm'),
    path('api/hermetical-testing-norms/<uuid:norm_id>/delete/', views.delete_hermetical_testing_norm, name='delete_hermetical_testing_norm'),
    path('api/operation-norms/', views.get_operation_norms, name='get_operation_norms'),
    path('api/operation-norms/create/', views.create_operation_norm, name='create_operation_norm'),
    path('api/operation-norms/<uuid:norm_id>/update/', views.update_operation_norm, name='update_operation_norm'),
    path('api/operation-norms/<uuid:norm_id>/delete/', views.delete_operation_norm, name='delete_operation_norm'),
    
    # Completion Testing Norms Management
    path('completion-testing/', views.completion_testing_management, name='completion_testing_management'),
    path('api/completion-testing-norms/', views.get_completion_testing_norms, name='get_completion_testing_norms'),
    path('api/completion-testing-norms/create/', views.create_completion_testing_norm, name='create_completion_testing_norm'),
    path('api/completion-testing-norms/<uuid:norm_id>/update/', views.update_completion_testing_norm, name='update_completion_testing_norm'),
    path('api/completion-testing-norms/<uuid:norm_id>/delete/', views.delete_completion_testing_norm, name='delete_completion_testing_norm'),
    
    # Additional Tests Management
    path('additional-tests/', views.additional_tests_management, name='additional_tests_management'),
    path('api/additional-tests/', views.get_additional_tests, name='get_additional_tests'),
    path('api/additional-tests/create/', views.create_additional_test, name='create_additional_test'),
    path('api/additional-tests/<uuid:test_id>/update/', views.update_additional_test, name='update_additional_test'),
    path('api/additional-tests/<uuid:test_id>/delete/', views.delete_additional_test, name='delete_additional_test'),
    
    # Location Spec Factors Management (Admin Only)
    path('loc-spec-factors/', views.loc_spec_factors_management, name='loc_spec_factors_management'),
    path('api/loc-spec-factors/', views.get_loc_spec_factors, name='get_loc_spec_factors'),
    path('api/loc-spec-factors/create/', views.create_loc_spec_factor, name='create_loc_spec_factor'),
    path('api/loc-spec-factors/<uuid:factor_id>/update/', views.update_loc_spec_factor, name='update_loc_spec_factor'),
    path('api/loc-spec-factors/<uuid:factor_id>/delete/', views.delete_loc_spec_factor, name='delete_loc_spec_factor'),
    path('api/loc-spec-factors/for-location/<str:location>/', views.get_factors_for_location, name='get_factors_for_location'),
    
    # Database Viewer (Admin Only)
    path('database-viewer/', views.database_viewer, name='database_viewer'),
    path('database-viewer/<str:app_label>/<str:model_name>/', views.database_table_detail, name='database_table_detail'),
    
    # Company Codes Management (Admin Only)
    path('api/company-codes/', views.get_company_codes, name='get_company_codes'),
    path('api/company-codes/create/', views.create_company_code, name='create_company_code'),
    path('api/company-codes/<uuid:code_id>/update/', views.update_company_code, name='update_company_code'),
    path('api/company-codes/<uuid:code_id>/delete/', views.delete_company_code, name='delete_company_code'),
    path('api/company-codes/upload/', views.upload_company_codes, name='upload_company_codes'),
    path('api/company-codes/locations/', views.get_unique_mpi_locations, name='get_unique_mpi_locations'),
    path('api/company-codes/fields/', views.get_unique_mpi_fields, name='get_unique_mpi_fields'),
    
    # Master Personnel Info (MPI) Management (Admin Only)
    path('api/mpi/upload/', views.upload_mpi, name='upload_mpi'),
    path('api/mpi/search/', views.search_mpi, name='search_mpi'),
    path('api/mpi/all/', views.get_all_mpi, name='get_all_mpi'),
    path('mpi-table/', views.mpi_table_view, name='mpi_table_view'),
    
    # User Role Management (Admin Only) - DEPRECATED
    path('api/user-roles/', views.list_user_roles, name='list_user_roles'),
    path('api/user-roles/get/', views.get_user_role, name='get_user_role'),
    path('api/user-roles/assign/', views.assign_user_role, name='assign_user_role'),
    path('api/user-roles/remove/', views.remove_user_role, name='remove_user_role'),
    
    # Authorized Users (LDAP) - NEW
    path('api/authorized-users/', views.list_authorized_users, name='list_authorized_users'),
    path('api/authorized-users/update/', views.update_authorized_user, name='update_authorized_user'),
    path('api/authorized-users/toggle/', views.toggle_user_active_status, name='toggle_user_active_status'),
    path('api/authorized-users/delete/', views.delete_authorized_user, name='delete_authorized_user'),
    path('api/authorized-users/reactivate/', views.reactivate_authorized_user, name='reactivate_authorized_user'),
    path('api/authorized-users/bulk-add-org-unit/', views.bulk_add_org_unit_users, name='bulk_add_org_unit_users'),
    
    # Auto-calculation endpoint
    path('api/calculate-well-parameters/', views.calculate_well_parameters, name='calculate_well_parameters'),
    
    # path('api/wells/by-location/', views.wells_by_location, name='wells_by_location'),
    # path('api/rigs/by-location/', views.rigs_by_location, name='rigs_by_location'),
    path('api/export/schedule/<uuid:schedule_id>/', views.export_schedule_csv, name='export_schedule_csv'),
    path('api/export/schedule/<uuid:schedule_id>/excel/', views.export_schedule_excel, name='export_schedule_excel'),
    
    # Location-based API endpoints
    path('api/user/location/', views.get_user_location_info, name='user_location_info'),
    path('api/locations/', views.get_all_locations, name='all_locations'),
    
    # ILM Cost - Well Pair Distance endpoints
    path('api/ilm-cost/distances/', views.get_well_pair_distances, name='get_well_pair_distances'),
    path('api/ilm-cost/recalculate/', views.recalculate_well_pair_distances, name='recalculate_well_pair_distances'),
    path('api/ilm-cost/summary/', views.get_ilm_cost_summary, name='get_ilm_cost_summary'),

    # =========================================================================
    # Schedule Execution Module (SEM)
    # =========================================================================
    # Template views
    path('execution/', sem_views.sem_dashboard, name='sem_dashboard'),
    path('execution/<uuid:execution_id>/', sem_views.sem_detail, name='sem_detail'),

    # API: List & Activate
    path('api/sem/executions/', sem_views.sem_list_executions, name='sem_list_executions'),
    path('api/sem/available-schedules/', sem_views.sem_available_schedules, name='sem_available_schedules'),
    path('api/sem/activate/', sem_views.sem_activate_schedule, name='sem_activate_schedule'),

    # API: Execution Detail & Gantt
    path('api/sem/executions/<uuid:execution_id>/', sem_views.sem_execution_detail, name='sem_execution_detail'),
    path('api/sem/executions/<uuid:execution_id>/gantt/', sem_views.sem_gantt_data, name='sem_gantt_data'),

    # API: Actuals & Locking
    path('api/sem/executions/<uuid:execution_id>/update-actuals/', sem_views.sem_update_actuals, name='sem_update_actuals'),
    path('api/sem/executions/<uuid:execution_id>/lock-well/', sem_views.sem_lock_well, name='sem_lock_well'),
    path('api/sem/executions/<uuid:execution_id>/unlock-well/', sem_views.sem_unlock_well, name='sem_unlock_well'),
    path('api/sem/executions/<uuid:execution_id>/apply-cutoff/', sem_views.sem_apply_cutoff, name='sem_apply_cutoff'),

    # API: Rig & Well Modifications
    path('api/sem/executions/<uuid:execution_id>/add-well/', sem_views.sem_add_well, name='sem_add_well'),
    path('api/sem/executions/<uuid:execution_id>/remove-well/', sem_views.sem_remove_well, name='sem_remove_well'),
    path('api/sem/executions/<uuid:execution_id>/defer-well/', sem_views.sem_defer_well, name='sem_defer_well'),
    path('api/sem/executions/<uuid:execution_id>/update-remarks/', sem_views.sem_update_remarks, name='sem_update_remarks'),
    path('api/sem/executions/<uuid:execution_id>/add-rig/', sem_views.sem_add_rig, name='sem_add_rig'),
    path('api/sem/executions/<uuid:execution_id>/remove-rig/', sem_views.sem_remove_rig, name='sem_remove_rig'),
    path('api/sem/executions/<uuid:execution_id>/replace-rig/', sem_views.sem_replace_rig, name='sem_replace_rig'),
    path('api/sem/executions/<uuid:execution_id>/replace-well/', sem_views.sem_replace_well, name='sem_replace_well'),
    path('api/sem/executions/<uuid:execution_id>/shift-dates/', sem_views.sem_shift_dates, name='sem_shift_dates'),

    # API: Re-optimization
    path('api/sem/executions/<uuid:execution_id>/reoptimize/', sem_views.sem_reoptimize, name='sem_reoptimize'),

    # API: Scenarios (What-If Analysis)
    path('api/sem/executions/<uuid:execution_id>/scenarios/', sem_views.sem_list_scenarios, name='sem_list_scenarios'),
    path('api/sem/executions/<uuid:execution_id>/scenarios/create/', sem_views.sem_create_scenario, name='sem_create_scenario'),
    path('api/sem/executions/<uuid:execution_id>/scenarios/<uuid:scenario_id>/', sem_views.sem_scenario_detail, name='sem_scenario_detail'),
    path('api/sem/executions/<uuid:execution_id>/scenarios/<uuid:scenario_id>/apply/', sem_views.sem_apply_scenario, name='sem_apply_scenario'),
    path('api/sem/executions/<uuid:execution_id>/scenarios/<uuid:scenario_id>/delete/', sem_views.sem_delete_scenario, name='sem_delete_scenario'),
    path('api/sem/executions/<uuid:execution_id>/scenarios/compare/', sem_views.sem_compare_scenarios, name='sem_compare_scenarios'),

    # API: Logs, Status & Analytics
    path('api/sem/executions/<uuid:execution_id>/logs/', sem_views.sem_execution_logs, name='sem_execution_logs'),
    path('api/sem/executions/<uuid:execution_id>/update-status/', sem_views.sem_update_status, name='sem_update_status'),
    path('api/sem/executions/<uuid:execution_id>/analytics/', sem_views.sem_analytics, name='sem_analytics'),

    # API: Available Rigs & Wells for adding
    path('api/sem/executions/<uuid:execution_id>/available-wells/', sem_views.sem_available_wells, name='sem_available_wells'),
    path('api/sem/executions/<uuid:execution_id>/available-rigs/', sem_views.sem_available_rigs, name='sem_available_rigs'),

    # =========================================================================
    # User Activity Tracking
    # =========================================================================
    path('activity/', activity_views.activity_dashboard, name='activity_dashboard'),
    path('api/activity/list/', activity_views.activity_list, name='activity_list'),
    path('api/activity/stats/', activity_views.activity_stats, name='activity_stats'),
    path('api/activity/user/<str:username>/', activity_views.activity_user_detail, name='activity_user_detail'),
    path('api/activity/ip/<str:ip_address>/', activity_views.activity_ip_detail, name='activity_ip_detail'),
    path('api/activity/cleanup/', activity_views.activity_cleanup, name='activity_cleanup'),
]
