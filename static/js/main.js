// Main JavaScript for Intelligent Drilling Rig Scheduler

// Global variables
let rigsData = [];
let wellsData = [];
let schedulesData = [];
let currentSchedule = null;
let companyCodesMap = {}; // Maps asset_id (uppercase) to location name for filtering

// CRITICAL: Global modal cleanup utility to prevent backdrop and body lock issues
function cleanupModalState() {
    // Remove all modal backdrops
    document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
        backdrop.remove();
    });
    
    // Remove modal-open class from body
    document.body.classList.remove('modal-open');
    
    // Reset body overflow and padding
    document.body.style.removeProperty('overflow');
    document.body.style.removeProperty('padding-right');
    
    // Log cleanup for debugging
    console.log('Modal state cleaned up');
}

// Add global event listeners for all Bootstrap modals to auto-cleanup
document.addEventListener('DOMContentLoaded', function() {
    // Listen for all modal hide events
    document.querySelectorAll('.modal').forEach(modalElement => {
        modalElement.addEventListener('hidden.bs.modal', function() {
            // Small delay to ensure Bootstrap's cleanup is done first
            setTimeout(cleanupModalState, 100);
        });
    });
});

// Initialize data with safety checks
function initializeData() {
    if (!rigsData) rigsData = [];
    if (!wellsData) wellsData = [];
    if (!schedulesData) schedulesData = [];
}

// API endpoints
const API_BASE = '/api';
// Add Indian currency formatting function - formats in K/L/Cr
function formatIndianCurrency(value) {
    try {
        // Convert to number
        const numValue = parseFloat(value);
        
        // Handle zero or invalid values
        if (!numValue || numValue === 0) return "₹0";
        
        // Format based on value ranges
        if (numValue >= 10000000) { // 1 Crore or more
            const crores = (numValue / 10000000).toFixed(2).replace(/\.?0+$/, '');
            return `₹${crores}Cr`;
        } else if (numValue >= 100000) { // 1 Lakh or more
            const lakhs = (numValue / 100000).toFixed(2).replace(/\.?0+$/, '');
            return `₹${lakhs}L`;
        } else if (numValue >= 1000) { // 1 Thousand or more
            const thousands = (numValue / 1000).toFixed(2).replace(/\.?0+$/, '');
            return `₹${thousands}K`;
        } else {
            return `₹${numValue}`;
        }
    } catch (error) {
        return value ? `₹${value}` : "₹0";
    }
}

// Add solve time formatting function
function formatSolveTime(value) {
    try {
        if (!value || value === 0) return "< 1 second";
        
        const timeValue = parseFloat(value);
        
        if (timeValue < 1) return "< 1 second";
        else if (timeValue < 60) {
            const seconds = timeValue.toFixed(1);
            return `${seconds} ${seconds === '1.0' ? 'second' : 'seconds'}`;
        } else {
            const minutes = Math.floor(timeValue / 60);
            const seconds = Math.floor(timeValue % 60);
            const minuteText = minutes === 1 ? 'minute' : 'minutes';
            const secondText = seconds === 1 ? 'second' : 'seconds';
            
            if (seconds === 0) {
                return `${minutes} ${minuteText}`;
            } else {
                return `${minutes} ${minuteText} ${seconds} ${secondText}`;
            }
        }
    } catch (error) {
        return "< 1 second";
    }
}

const ENDPOINTS = {
    rigs: `${API_BASE}/rigs/`,
    wells: `${API_BASE}/wells/`,
    schedules: `${API_BASE}/schedules/`,
    assignments: `${API_BASE}/assignments/`,
    unassigned: `${API_BASE}/unassigned-wells/`,
    bulkUpload: `${API_BASE}/bulk-upload/`,
    createSchedule: `${API_BASE}/schedules/create_schedule/`,
    companyCodes: `${API_BASE}/company-codes/`
};

// Helper function to load company codes map for location filtering
async function loadCompanyCodesMap() {
    try {
        const response = await fetch(ENDPOINTS.companyCodes, {
            credentials: 'same-origin'
        });
        if (response.ok) {
            const codes = await response.json();
            companyCodesMap = {};
            codes.forEach(code => {
                // Map company_code (asset_id) to location, case-insensitive
                if (code.company_code && code.location) {
                    companyCodesMap[code.company_code.toUpperCase()] = code.location;
                    // Also map location to itself (uppercase) for cases where asset_id IS the location value
                    companyCodesMap[code.location.toUpperCase()] = code.location;
                }
            });
            console.log('Loaded companyCodesMap:', companyCodesMap);
        }
    } catch (error) {
        console.error('Error loading company codes map:', error);
    }
}

// Helper function to get location from a rig or well item
function getLocationFromData(item) {
    // First check if location_value is directly available (from serializer)
    if (item.location_value) {
        return item.location_value;
    }
    // Then check if location_name is available
    if (item.location_name) {
        return item.location_name;
    }
    // Fallback: use asset_id mapping
    if (item.asset_id && companyCodesMap[item.asset_id.toUpperCase()]) {
        return companyCodesMap[item.asset_id.toUpperCase()];
    }
    // Final fallback: return asset_id itself
    return item.asset_id || null;
}

// Utility functions
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function getCSRFToken() {
    // First try to get from meta tag (more reliable)
    const metaToken = document.querySelector('meta[name="csrf-token"]');
    if (metaToken && metaToken.content) {
        return metaToken.content;
    }
    // Fallback to cookie with unique name for this app
    return getCookie('idrs_csrftoken');
}

function showAlert(message, type = 'info', duration = 5000) {
    const alertsContainer = document.getElementById('alerts-container');
    const alertId = 'alert-' + Date.now();
    
    // Map alert types to Bootstrap classes and improve styling
    const alertTypeMap = {
        'info': 'alert-primary',
        'success': 'alert-success',
        'warning': 'alert-warning',
        'danger': 'alert-danger',
        'error': 'alert-danger'
    };
    
    const alertClass = alertTypeMap[type] || 'alert-primary';
    
    const alertHTML = `
        <div id="${alertId}" class="alert ${alertClass} alert-dismissible fade show shadow-sm border-0" 
             role="alert" style="background-color: white; backdrop-filter: none; margin-bottom: 10px;">
            <div class="d-flex align-items-center">
                <i class="bi bi-${getAlertIcon(type)} me-2"></i>
                <div class="flex-grow-1">${message}</div>
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        </div>
    `;
    
    alertsContainer.insertAdjacentHTML('beforeend', alertHTML);
    
    if (duration > 0) {
        setTimeout(() => {
            const alertElement = document.getElementById(alertId);
            if (alertElement) {
                alertElement.remove();
            }
        }, duration);
    }
}

function getAlertIcon(type) {
    const iconMap = {
        'info': 'info-circle-fill',
        'success': 'check-circle-fill',
        'warning': 'exclamation-triangle-fill',
        'danger': 'x-circle-fill',
        'error': 'x-circle-fill'
    };
    return iconMap[type] || 'info-circle-fill';
}

function setLoading(elementId, isLoading) {
    const element = document.getElementById(elementId);
    if (element) {
        if (isLoading) {
            element.classList.add('loading');
        } else {
            element.classList.remove('loading');
        }
    }
    // Silently skip if element doesn't exist - different pages have different elements
}

// API functions
async function apiRequest(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('idrs_csrftoken')
        }
    };
    
    const response = await fetch(url, { ...defaultOptions, ...options });
    
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || errorData.detail || `HTTP error! status: ${response.status}`);
    }
    
    // For DELETE requests, there might be no response body
    if (options.method === 'DELETE' && response.status === 204) {
        return {}; // Return empty object for successful DELETE
    }
    
    // Check if response has content before trying to parse JSON
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
        return response.json();
    }
    
    return {}; // Return empty object if no JSON content
}

// Flag to prevent duplicate loading
let isLoadingData = false;

async function loadData() {
    // Prevent duplicate calls
    if (isLoadingData) {
        console.log('loadData() already in progress, skipping duplicate call');
        return;
    }
    
    isLoadingData = true;
    
    try {
        console.log('Starting data load...');
        setLoading('dashboard', true);
        
        // Fetch ALL pages of data for each resource
        let rigs = [];
        let wells = [];
        let schedules = [];
        
        // Fetch all rigs
        let rigsUrl = ENDPOINTS.rigs;
        while (rigsUrl) {
            const response = await apiRequest(rigsUrl);
            const results = response.results || response;
            if (Array.isArray(results)) {
                rigs = rigs.concat(results);
            } else if (Array.isArray(response)) {
                rigs = rigs.concat(response);
            }
            rigsUrl = response.next || null;
        }
        
        // Fetch all wells
        let wellsUrl = ENDPOINTS.wells;
        while (wellsUrl) {
            const response = await apiRequest(wellsUrl);
            const results = response.results || response;
            if (Array.isArray(results)) {
                wells = wells.concat(results);
            } else if (Array.isArray(response)) {
                wells = wells.concat(response);
            }
            wellsUrl = response.next || null;
        }
        
        // Fetch all schedules
        let schedulesUrl = ENDPOINTS.schedules;
        while (schedulesUrl) {
            const response = await apiRequest(schedulesUrl);
            const results = response.results || response;
            if (Array.isArray(results)) {
                schedules = schedules.concat(results);
            } else if (Array.isArray(response)) {
                schedules = schedules.concat(response);
            }
            schedulesUrl = response.next || null;
        }
        
        rigsData = rigs;
        wellsData = wells;
        schedulesData = schedules;
        
        console.log('Processed data:', { 
            rigs: rigsData.length, 
            wells: wellsData.length, 
            schedules: schedulesData.length 
        });
        
        console.log('Calling updateDashboard...');
        updateDashboard();
        console.log('updateDashboard completed');
        
        console.log('Calling populateDropdowns...');
        // Add a small delay to ensure DOM elements are fully rendered
        setTimeout(() => {
            populateDropdowns();
            console.log('populateDropdowns completed');
        }, 100);
        
    } catch (error) {
        console.error('Error loading data:', error);
        showAlert(`Error loading data: ${error.message}`, 'danger');
        
        // Initialize with empty arrays if API fails
        rigsData = [];
        wellsData = [];
        schedulesData = [];
        updateDashboard();
        
    } finally {
        setLoading('dashboard', false);
        isLoadingData = false; // Reset the loading flag
    }
}

function updateDashboard() {
    // GUARD: Absolutely prevent this from running on data management page
    // Data management page has its own initialization
    if (document.getElementById('data-management-page-indicator')) {
        console.log('updateDashboard: Skipped - data management page detected');
        return;
    }
    
    // Ensure data arrays are initialized
    initializeData();
    
    console.log('updateDashboard called with data lengths:', { 
        rigs: rigsData ? rigsData.length : 0, 
        wells: wellsData ? wellsData.length : 0, 
        schedules: schedulesData ? schedulesData.length : 0 
    });
    
    const totalRigsEl = document.getElementById('total-rigs');
    const totalWellsEl = document.getElementById('total-wells');
    const activeSchedulesEl = document.getElementById('active-schedules');
    const optimizationScoreEl = document.getElementById('optimization-score');
    
    console.log('Dashboard elements found:', {
        totalRigsEl: !!totalRigsEl,
        totalWellsEl: !!totalWellsEl,
        activeSchedulesEl: !!activeSchedulesEl,
        optimizationScoreEl: !!optimizationScoreEl
    });
    
    // Update main dashboard stats
    if (totalRigsEl) {
        totalRigsEl.textContent = rigsData ? rigsData.length : 0;
        console.log('Updated total-rigs to:', rigsData ? rigsData.length : 0);
    }
    if (totalWellsEl) {
        totalWellsEl.textContent = wellsData ? wellsData.length : 0;
        console.log('Updated total-wells to:', wellsData ? wellsData.length : 0);
    }
    if (activeSchedulesEl) {
        activeSchedulesEl.textContent = schedulesData ? schedulesData.length : 0;
        console.log('Updated active-schedules to:', schedulesData ? schedulesData.length : 0);
    }
    
    // Calculate optimization score based on multiple factors
    if (optimizationScoreEl) {
        const score = calculateOptimizationScore();
        optimizationScoreEl.textContent = score;
        console.log('Updated optimization-score to:', score);
    }
    
    // Update data management section counters (only if NOT on data management page)
    // Data management page has its own updateLocationStats() function
    const isDataManagementPage = document.getElementById('data-management-page-indicator');
    if (!isDataManagementPage) {
        updateDataManagementCounters();
    } else {
        console.log('Skipping updateDataManagementCounters - data management page has its own handler');
    }
    
    // Update recent schedules table
    updateRecentSchedulesTable();
    
    console.log('Dashboard update completed');
}

function updateDataManagementCounters() {
    // GUARD: Absolutely prevent this from running on data management page
    // Data management page has its own updateLocationStats() function
    if (document.getElementById('data-management-page-indicator')) {
        console.log('updateDataManagementCounters: Skipped - data management page detected');
        return;
    }
    
    // Ensure data arrays are initialized
    initializeData();
    
    console.log('updateDataManagementCounters called with data:', {
        rigs: rigsData ? rigsData.length : 'null/undefined',
        wells: wellsData ? wellsData.length : 'null/undefined'
    });
    
    // Update existing counters (only if elements exist - different pages have different elements)
    const currentRigsEl = document.getElementById('current-rigs-count');
    const currentWellsEl = document.getElementById('current-wells-count');
    
    if (currentRigsEl) {
        currentRigsEl.textContent = rigsData ? rigsData.length : 0;
        console.log('Updated current-rigs-count to:', rigsData ? rigsData.length : 0);
    }
    if (currentWellsEl) {
        currentWellsEl.textContent = wellsData ? wellsData.length : 0;
        console.log('Updated current-wells-count to:', wellsData ? wellsData.length : 0);
    }
    
    // Update new statistics cards (only if they exist on this page)
    const statsTotalRigsEl = document.getElementById('stats-total-rigs');
    const statsTotalWellsEl = document.getElementById('stats-total-wells');
    const statsHighPriorityWellsEl = document.getElementById('stats-high-priority-wells');
    const statsAvgDailyCostEl = document.getElementById('stats-avg-daily-cost');
    
    // Total rigs
    if (statsTotalRigsEl) {
        statsTotalRigsEl.textContent = rigsData ? rigsData.length : 0;
        console.log('Updated stats-total-rigs to:', rigsData ? rigsData.length : 0);
    }
    
    // Total wells
    if (statsTotalWellsEl) {
        statsTotalWellsEl.textContent = wellsData ? wellsData.length : 0;
        console.log('Updated stats-total-wells to:', wellsData ? wellsData.length : 0);
    }
    
    // High priority wells
    if (statsHighPriorityWellsEl) {
        const highPriorityCount = wellsData ? wellsData.filter(well => 
            well.priority === 'HIGH' || well.priority === 'High' || well.priority === 'high'
        ).length : 0;
        statsHighPriorityWellsEl.textContent = highPriorityCount;
        console.log('Updated stats-high-priority-wells to:', highPriorityCount);
    }
    
    // Average daily cost
    if (statsAvgDailyCostEl) {
        if (rigsData && rigsData.length > 0) {
            const totalCost = rigsData.reduce((sum, rig) => {
                const dailyCost = parseFloat(rig.daily_cost_inr) || 0;
                return sum + dailyCost;
            }, 0);
            const avgCost = totalCost / rigsData.length / 100000; // Convert to lakhs
            statsAvgDailyCostEl.textContent = `₹${avgCost.toFixed(1)}L`;
            console.log('Updated stats-avg-daily-cost to:', `₹${avgCost.toFixed(1)}L`);
        } else {
            statsAvgDailyCostEl.textContent = '-';
            console.log('Updated stats-avg-daily-cost to: -');
        }
    }
}

function calculateOptimizationScore() {
    // Ensure data arrays are initialized
    initializeData();
    
    // If no data available, return placeholder
    if (!rigsData || !wellsData || rigsData.length === 0 || wellsData.length === 0) {
        return '-';
    }
    
    let score = 0;
    let totalFactors = 0;
    
    // Factor 1: Cost minimization efficiency (40% weight)
    if (rigsData.length > 0) {
        const avgCost = rigsData.reduce((sum, rig) => sum + (parseFloat(rig.daily_cost_inr) || 0), 0) / rigsData.length;
        const minCost = Math.min(...rigsData.map(rig => parseFloat(rig.daily_cost_inr) || 0));
        const costEfficiency = minCost > 0 ? (minCost / avgCost) * 100 : 50;
        score += costEfficiency * 0.4;
        totalFactors += 0.4;
    }
    
    // Factor 2: Resource utilization (30% weight)
    const totalAssignments = schedulesData ? schedulesData.reduce((count, schedule) => {
        return count + (schedule.assignments ? schedule.assignments.length : 0);
    }, 0) : 0;
    
    const utilizationRate = wellsData.length > 0 ? (totalAssignments / wellsData.length) * 100 : 0;
    score += Math.min(utilizationRate, 100) * 0.3;
    totalFactors += 0.3;
    
    // Factor 3: Schedule adherence (20% weight)
    const highPriorityWells = wellsData.filter(well => 
        well.priority === 'HIGH' || well.priority === 'High' || well.priority === 'high'
    ).length;
    const scheduleAdherence = wellsData.length > 0 ? 
        ((wellsData.length - highPriorityWells) / wellsData.length * 50 + 50) : 75;
    score += scheduleAdherence * 0.2;
    totalFactors += 0.2;
    
    // Factor 4: Constraint satisfaction (10% weight)
    const rigCapacityMatch = rigsData.length > 0 && wellsData.length > 0 ? 
        (rigsData.length >= wellsData.length ? 100 : (rigsData.length / wellsData.length) * 100) : 50;
    score += Math.min(rigCapacityMatch, 100) * 0.1;
    totalFactors += 0.1;
    
    // Normalize and return score
    const finalScore = totalFactors > 0 ? Math.round(score / totalFactors) : 0;
    return `${Math.min(Math.max(finalScore, 0), 100)}%`;
}

// Note: populateOptimizationScoreModal is defined in dashboard.html as an async function
// that fetches data from the API. Do not duplicate it here to avoid conflicts.

// Note: openOptimizationScoreModal is defined in dashboard.html
// Do not duplicate it here to avoid conflicts.

// Note: Optimization score modal event listeners are set up in dashboard.html
// Do not duplicate them here to avoid race conditions and conflicts.

// Refresh all data function for Data Management page
function refreshAllData() {
    console.log('Refreshing all data...');
    showAlert('Refreshing all data...', 'info', 2000);
    
    // Force reload all data
    loadData().then(() => {
        showAlert('Data refreshed successfully!', 'success', 3000);
    }).catch(error => {
        console.error('Error refreshing data:', error);
        showAlert('Error refreshing data. Please try again.', 'danger');
    });
}

function updateRecentSchedulesTable() {
    const tableBody = document.querySelector('#recent-schedules-table tbody');
    if (!tableBody) return;
    
    if (!schedulesData || schedulesData.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No schedules available</td></tr>';
        return;
    }
    
    // Sort schedules by creation date (most recent first)
    const sortedSchedules = [...schedulesData].sort((a, b) => 
        new Date(b.created_at) - new Date(a.created_at)
    );
    
    // Take only the first 5 most recent schedules
    const recentSchedules = sortedSchedules.slice(0, 5);
    
    const rows = recentSchedules.map(schedule => {
        const createdDate = new Date(schedule.created_at).toLocaleDateString();
        const assignmentCount = schedule.assignments ? schedule.assignments.length : 0;
        
        // Calculate total cost - prefer API calculated total_cost
        let totalCost = '0.00';
        if (schedule.total_cost && schedule.total_cost !== null && schedule.total_cost > 0) {
            totalCost = (parseFloat(schedule.total_cost) / 10000000).toFixed(2);
        } else if (schedule.total_drilling_cost && schedule.total_ilm_cost) {
            // Use individual cost fields if available
            const drillingCost = parseFloat(schedule.total_drilling_cost || 0);
            const ilmCost = parseFloat(schedule.total_ilm_cost || 0);
            totalCost = ((drillingCost + ilmCost) / 10000000).toFixed(2);
        } else if (schedule.assignments && schedule.assignments.length > 0) {
            // Calculate from assignments as fallback
            const calculatedCost = schedule.assignments.reduce((sum, assignment) => {
                const drillingCost = parseFloat(assignment.drilling_cost || 0);
                const ilmCost = parseFloat(assignment.ilm_cost || 0);
                return sum + drillingCost + ilmCost;
            }, 0);
            totalCost = (calculatedCost / 10000000).toFixed(2);
        }
        
        const status = schedule.status || 'COMPLETED';
        
        // Use proper Bootstrap 5 badge classes with better color mapping
        let badgeClass = 'bg-success';
        if (status === 'PENDING' || status === 'IN_PROGRESS') {
            badgeClass = 'bg-warning text-dark';
        } else if (status === 'FAILED' || status === 'ERROR') {
            badgeClass = 'bg-danger';
        } else if (status === 'COMPLETED') {
            badgeClass = 'bg-success';
        }
        
        return `
            <tr>
                <td>${schedule.name}</td>
                <td><span class="badge ${badgeClass}">${status}</span></td>
                <td>${createdDate}</td>
                <td>${assignmentCount}</td>
                <td>₹${totalCost}</td>
                <td>
                    <button class="btn btn-sm btn-primary" onclick="viewSchedule('${schedule.id}')">
                        <i class="bi bi-eye"></i> View
                    </button>
                </td>
            </tr>
        `;
    }).join('');
    
    tableBody.innerHTML = rows;
}

function populateDropdowns() {
    try {
        // GUARD: Absolutely prevent this from running on data management page
        // Data management page doesn't have these dropdowns
        if (document.getElementById('data-management-page-indicator')) {
            console.log('populateDropdowns: Skipped - data management page detected');
            return;
        }
        
        // Ensure data arrays are initialized
        initializeData();
        
        console.log('populateDropdowns: Starting with data:', { 
            rigs: rigsData ? rigsData.length : 'null', 
            wells: wellsData ? wellsData.length : 'null' 
        });
        
        // Check if we're on a page that has these elements
        const selectedRigs = document.getElementById('selected-rigs');
        const selectedWells = document.getElementById('selected-wells');
        
        console.log('populateDropdowns: Found elements:', {
            selectedRigs: !!selectedRigs,
            selectedWells: !!selectedWells
        });
        
        // Populate rig multi-select (Schedule Optimization section)
        if (selectedRigs) {
            console.log('Found selected-rigs element');
            selectedRigs.innerHTML = '';
            if (!rigsData || rigsData.length === 0) {
                selectedRigs.innerHTML = '<option disabled>Loading rigs...</option>';
            } else {
                console.log('Populating rigs dropdown with', rigsData.length, 'rigs');
                rigsData.forEach((rig, index) => {
                    try {
                        const rigName = rig.name || rig.rig_name || `Rig ${rig.id}`;
                        selectedRigs.innerHTML += `<option value="${rig.id}">${rigName}</option>`;
                    } catch (rigError) {
                        console.error('Error processing rig at index', index, ':', rigError, rig);
                    }
                });
            }
        } else {
            console.log('selected-rigs element not found');
        }
        
        // Populate wells multi-select (Schedule Optimization section)
        if (selectedWells) {
            console.log('Found selected-wells element');
            selectedWells.innerHTML = '';
            if (!wellsData || wellsData.length === 0) {
                selectedWells.innerHTML = '<option disabled>Loading wells...</option>';
            } else {
                console.log('Populating wells dropdown with', wellsData.length, 'wells');
                wellsData.forEach((well, index) => {
                    try {
                        const wellName = well.name || well.well_name || `Well ${well.id}`;
                        selectedWells.innerHTML += `<option value="${well.id}">${wellName}</option>`;
                    } catch (wellError) {
                        console.error('Error processing well at index', index, ':', wellError, well);
                    }
                });
            }
        } else {
            console.log('selected-wells element not found');
        }
        
        // Populate rig filter dropdown (if it exists)
        const rigSelect = document.getElementById('rig-select');
        if (rigSelect) {
            console.log('Found rig-select element');
            rigSelect.innerHTML = '<option value="">All Rigs</option>';
            if (!rigsData || rigsData.length === 0) {
                rigSelect.innerHTML += '<option value="" disabled>Loading rigs...</option>';
            } else {
                rigsData.forEach(rig => {
                    const rigName = rig.name || rig.rig_name || `Rig ${rig.id}`;
                    rigSelect.innerHTML += `<option value="${rig.id}">${rigName}</option>`;
                });
            }
        }
        
        // Populate well type filter dropdown (if it exists)
        const wellTypes = wellsData && wellsData.length > 0 ? 
            [...new Set(wellsData.map(well => well.well_type).filter(Boolean))] : [];
        const wellTypeSelect = document.getElementById('well-type-select');
        if (wellTypeSelect) {
            console.log('Found well-type-select element');
            wellTypeSelect.innerHTML = '<option value="">All Well Types</option>';
            if (!wellsData || wellsData.length === 0) {
                wellTypeSelect.innerHTML += '<option value="" disabled>Loading wells...</option>';
            } else if (wellTypes.length === 0) {
                wellTypeSelect.innerHTML += '<option value="" disabled>No well types found</option>';
            } else {
                wellTypes.forEach(type => {
                    wellTypeSelect.innerHTML += `<option value="${type}">${type}</option>`;
                });
            }
        }
        
        console.log('populateDropdowns completed successfully');
        
    } catch (error) {
        console.error('Error in populateDropdowns:', error);
        
        // Show error in dropdowns
        const selectedRigs = document.getElementById('selected-rigs');
        const selectedWells = document.getElementById('selected-wells');
        const rigSelect = document.getElementById('rig-select');
        const wellTypeSelect = document.getElementById('well-type-select');
        
        if (selectedRigs) {
            selectedRigs.innerHTML = '<option disabled>Error loading rigs</option>';
        }
        if (selectedWells) {
            selectedWells.innerHTML = '<option disabled>Error loading wells</option>';
        }
        if (rigSelect) {
            rigSelect.innerHTML = '<option value="">All Rigs</option><option value="" disabled>Error loading rigs</option>';
        }
        if (wellTypeSelect) {
            wellTypeSelect.innerHTML = '<option value="">All Well Types</option><option value="" disabled>Error loading wells</option>';
        }
    }
}

// File upload functionality
function setupFileUpload() {
    console.log('Setting up file upload handlers...');
    
    const rigsUpload = document.getElementById('rig-file');
    const wellsUpload = document.getElementById('well-file');
    
    // File inputs are now handled by form submit events
    // No need for change event listeners that auto-trigger upload
    
    if (rigsUpload) {
        console.log('Rigs file input found');
    }
    
    if (wellsUpload) {
        console.log('Wells file input found');
    }
    
    // Silently skip if elements don't exist - different pages have different elements
    console.log('File upload setup complete - using form submit handlers');
}

function setupDragAndDrop(areaId, fileInput) {
    const area = document.getElementById(areaId);
    
    if (!area) {
        // Silently skip if element doesn't exist - different pages have different elements
        return;
    }
    
    if (!fileInput) {
        // Silently skip if file input doesn't exist
        return;
    }
    
    area.addEventListener('dragover', (e) => {
        e.preventDefault();
        area.classList.add('dragover');
    });
    
    area.addEventListener('dragleave', () => {
        area.classList.remove('dragover');
    });
    
    area.addEventListener('drop', (e) => {
        e.preventDefault();
        area.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            const dataType = areaId.includes('rigs') ? 'rigs' : 'wells';
            handleFileUpload({ target: fileInput }, dataType);
        }
    });
    
    console.log(`Drag and drop setup complete for ${areaId}`);
}

async function handleFileUpload(event, dataType) {
    console.log(`Starting file upload for ${dataType}...`);
    
    const file = event.target.files[0];
    if (!file) {
        console.warn('No file selected');
        return;
    }
    
    console.log(`File selected: ${file.name} (${file.size} bytes, ${file.type})`);
    
    // Validate file type
    if (!file.name.toLowerCase().endsWith('.csv')) {
        showAlert('Please select a CSV file', 'warning');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('data_type', dataType);
    
    try {
        // Use the form ID for loading state
        const formId = dataType === 'rigs' ? 'rig-upload-form' : 'well-upload-form';
        setLoading(formId, true);
        showAlert(`Uploading ${dataType} data...`, 'info');
        
        console.log(`Uploading to: ${ENDPOINTS.bulkUpload}`);
        
        const response = await fetch(ENDPOINTS.bulkUpload, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('idrs_csrftoken')
            },
            body: formData
        });
        
        console.log(`Upload response status: ${response.status}`);
        
        if (response.ok) {
            const result = await response.json();
            console.log('Upload result:', result);
            
            // Show detailed upload results
            let message = `Successfully uploaded ${result.created || 0} ${dataType} records`;
            if (result.updated && result.updated > 0) {
                message += `, updated ${result.updated} records`;
            }
            if (result.error_count && result.error_count > 0) {
                message += `. ${result.error_count} rows had errors.`;
                showAlert(message, 'warning');
                
                // Show error details if any
                if (result.errors && result.errors.length > 0) {
                    console.error('Upload errors:', result.errors);
                    // Show first few errors to user
                    const errorSummary = result.errors.slice(0, 3).join('\n');
                    showAlert(`Errors:\n${errorSummary}${result.errors.length > 3 ? '\n...and more. Check console for details.' : ''}`, 'danger');
                }
            } else {
                showAlert(message, 'success');
            }
            
            await loadData(); // Reload data for scheduling page
            
            // If on data management page, also reload the tables
            if (document.getElementById('rigs-table-body')) {
                await loadRigsTable();
            }
            if (document.getElementById('wells-table-body')) {
                await loadWellsTable();
            }
            
            // Update stats if on data management page
            if (typeof updateLocationStats === 'function') {
                await updateLocationStats();
            }
        } else {
            const errorText = await response.text();
            console.error('Upload error response:', errorText);
            
            let errorMessage = 'Upload failed';
            try {
                const errorData = JSON.parse(errorText);
                errorMessage = errorData.detail || errorData.error || errorMessage;
            } catch (e) {
                errorMessage = `HTTP ${response.status}: ${response.statusText}`;
            }
            
            showAlert(`Upload failed: ${errorMessage}`, 'danger');
        }
        
    } catch (error) {
        console.error('Upload error:', error);
        showAlert(`Upload failed: ${error.message}`, 'danger');
    } finally {
        const formId = dataType === 'rigs' ? 'rig-upload-form' : 'well-upload-form';
        setLoading(formId, false);
        
        // Clear the file input
        event.target.value = '';
    }
}

// Schedule creation
async function createSchedule() {
    const scheduleName = document.getElementById('schedule-name').value;
    const timeLimitElement = document.getElementById('time-limit');
    const timeLimit = timeLimitElement ? parseInt(timeLimitElement.value) : 60;
    
    // Get selected rigs and wells from multi-select boxes
    const selectedRigsElement = document.getElementById('selected-rigs');
    const selectedWellsElement = document.getElementById('selected-wells');
    
    const selectedRigIds = selectedRigsElement ? 
        Array.from(selectedRigsElement.selectedOptions).map(option => option.value) : [];
    const selectedWellIds = selectedWellsElement ? 
        Array.from(selectedWellsElement.selectedOptions).map(option => option.value) : [];
    
    if (!scheduleName.trim()) {
        showOptimizationError('Please enter a schedule name');
        return;
    }
    
    if (selectedRigIds.length === 0) {
        showOptimizationError('Please select at least one rig');
        return;
    }
    
    if (selectedWellIds.length === 0) {
        showOptimizationError('Please select at least one well');
        return;
    }

    // Get financial year
    const financialYear = document.getElementById('financial-year').value;
    
    if (!financialYear) {
        showOptimizationError('Please select a financial year');
        return;
    }

    const scheduleData = {
        name: scheduleName,
        financial_year: financialYear,
        time_limit_seconds: timeLimit,
        rig_ids: selectedRigIds,
        well_ids: selectedWellIds
    };
    
    try {
        setLoading('schedule-form', true);
        showOptimizationProgress(timeLimit);
        
        // Start the activity log simulation
        simulateOptimizationProcess(timeLimit);
        
        const result = await apiRequest(ENDPOINTS.createSchedule, {
            method: 'POST',
            body: JSON.stringify(scheduleData)
        });
        
        showOptimizationResults(result);
        currentSchedule = result;
        
        // Clear form
        document.getElementById('schedule-name').value = '';
        document.getElementById('financial-year').selectedIndex = 0; // Reset to "Select FY"
        if (timeLimitElement) timeLimitElement.value = '60';
        if (selectedRigsElement) selectedRigsElement.selectedIndex = -1;
        if (selectedWellsElement) selectedWellsElement.selectedIndex = -1;
        
        await loadData();
        updateGanttChart(result);
        
    } catch (error) {
        console.error('Schedule creation error:', error);
        showOptimizationError(`Failed to create schedule: ${error.message}`);
        showOptimizationActivityError(`Failed to create schedule: ${error.message}`);
    } finally {
        setLoading('schedule-form', false);
    }
}

// Optimization Status Functions
function showOptimizationProgress(timeLimit) {
    const statusDiv = document.getElementById('optimization-status');
    const progressDiv = document.getElementById('optimization-progress');
    const resultsDiv = document.getElementById('optimization-results');
    
    if (statusDiv) statusDiv.style.display = 'none';
    if (resultsDiv) resultsDiv.style.display = 'none';
    if (progressDiv) {
        progressDiv.style.display = 'block';
        startCountdown(timeLimit);
    }
}

function showOptimizationResults(result) {
    const statusDiv = document.getElementById('optimization-status');
    const progressDiv = document.getElementById('optimization-progress');
    const resultsDiv = document.getElementById('optimization-results');
    
    // Store the schedule ID for later use
    if (result.id) {
        window.lastScheduleId = result.id;
    }
    
    if (statusDiv) statusDiv.style.display = 'none';
    if (progressDiv) progressDiv.style.display = 'none';
    if (resultsDiv) {
        resultsDiv.style.display = 'block';
        
        // Update result values
        const assignmentsSpan = document.getElementById('result-assignments');
        const unassignedSpan = document.getElementById('result-unassigned');
        const costSpan = document.getElementById('result-cost');
        const timeSpan = document.getElementById('result-time');
        
        if (assignmentsSpan) assignmentsSpan.textContent = result.assignments ? result.assignments.length : 0;
        if (unassignedSpan) unassignedSpan.textContent = result.unassigned_wells ? result.unassigned_wells.length : 0;
        if (costSpan) costSpan.textContent = result.total_cost ? formatIndianCurrency(result.total_cost) : '0';
        if (timeSpan) timeSpan.textContent = result.solve_time_seconds ? formatSolveTime(result.solve_time_seconds) : '< 1 second';
    }
}

function showOptimizationError(errorMessage) {
    const statusDiv = document.getElementById('optimization-status');
    const progressDiv = document.getElementById('optimization-progress');
    const resultsDiv = document.getElementById('optimization-results');
    
    if (progressDiv) progressDiv.style.display = 'none';
    if (resultsDiv) resultsDiv.style.display = 'none';
    if (statusDiv) {
        statusDiv.style.display = 'block';
        statusDiv.innerHTML = `
            <i class="bi bi-exclamation-triangle-fill fs-1 text-danger"></i>
            <p class="mt-2 text-danger">${errorMessage}</p>
            <button class="btn btn-outline-secondary btn-sm" onclick="resetOptimizationStatus()">
                <i class="bi bi-arrow-clockwise me-1"></i>Reset
            </button>
        `;
    }
}

function resetOptimizationStatus() {
    const statusDiv = document.getElementById('optimization-status');
    const progressDiv = document.getElementById('optimization-progress');
    const resultsDiv = document.getElementById('optimization-results');
    const activityDiv = document.getElementById('scheduler-activity');
    
    if (progressDiv) progressDiv.style.display = 'none';
    if (resultsDiv) resultsDiv.style.display = 'none';
    if (statusDiv) {
        statusDiv.style.display = 'block';
        statusDiv.innerHTML = `
            <i class="bi bi-hourglass-split fs-1"></i>
            <p class="mt-2">Ready to optimize</p>
        `;
    }
    
    // Reset activity log
    if (activityDiv) {
        activityDiv.innerHTML = `
            <div class="text-center text-muted py-3">
                <i class="bi bi-info-circle fs-4"></i>
                <p class="mt-2 mb-0">Activity log will appear here when optimization starts</p>
            </div>
        `;
    }
}

function startCountdown(timeLimit) {
    const progressDiv = document.getElementById('optimization-progress');
    if (!progressDiv) return;
    
    let remainingTime = timeLimit;
    const progressBar = progressDiv.querySelector('.progress-bar');
    const progressText = progressDiv.querySelector('p');
    
    const countdownInterval = setInterval(() => {
        remainingTime--;
        const percentage = Math.max(0, (remainingTime / timeLimit) * 100);
        
        if (progressBar) {
            progressBar.style.width = `${100 - percentage}%`;
            progressBar.textContent = ''; // Remove text from progress bar
        }
        
        if (progressText) {
            progressText.textContent = `Optimisation in process... ${remainingTime} seconds remaining`;
        }
        
        if (remainingTime <= 0) {
            clearInterval(countdownInterval);
            if (progressBar) {
                progressBar.textContent = 'Finalizing results...';
            }
            if (progressText) {
                progressText.textContent = 'Finalizing optimization results...';
            }
        }
    }, 1000);
    
    // Store the interval ID so we can clear it if needed
    if (progressDiv) {
        progressDiv.countdownInterval = countdownInterval;
    }
}

// Scheduler Activity Log Functions
function clearActivityLog() {
    console.log('clearActivityLog called');
    const activityDiv = document.getElementById('scheduler-activity');
    console.log('activityDiv found:', !!activityDiv);
    if (activityDiv) {
        activityDiv.innerHTML = `
            <div class="text-center text-muted py-3">
                <i class="bi bi-info-circle fs-4"></i>
                <p class="mt-2 mb-0">Starting optimization process...</p>
            </div>
        `;
        console.log('Activity log cleared and set to starting state');
    }
}

function addActivityLog(message, type = 'info', icon = 'info-circle') {
    console.log('addActivityLog called:', message, type, icon);
    const activityDiv = document.getElementById('scheduler-activity');
    if (!activityDiv) {
        console.error('scheduler-activity element not found!');
        return;
    }
    
    // Remove the placeholder message if it exists
    const placeholder = activityDiv.querySelector('.text-center.text-muted');
    if (placeholder) {
        placeholder.remove();
        console.log('Placeholder removed');
    }
    
    const timestamp = new Date().toLocaleTimeString();
    const activityItem = document.createElement('div');
    activityItem.className = `activity-item ${type}`;
    activityItem.innerHTML = `
        <div class="activity-icon">
            <i class="bi bi-${icon}"></i>
        </div>
        <div class="activity-text">${message}</div>
        <div class="activity-time">${timestamp}</div>
    `;
    
    activityDiv.appendChild(activityItem);
    
    // Auto-scroll to bottom
    activityDiv.scrollTop = activityDiv.scrollHeight;
    
    // Limit to 50 items to prevent memory issues
    const items = activityDiv.querySelectorAll('.activity-item');
    if (items.length > 50) {
        items[0].remove();
    }
}

function simulateOptimizationProcess(timeLimit) {
    console.log('simulateOptimizationProcess called with timeLimit:', timeLimit);
    clearActivityLog();
    
    // Add initial activities
    addActivityLog('Initializing optimization engine...', 'info', 'gear');
    
    setTimeout(() => {
        addActivityLog('Loading rig and well data...', 'info', 'database');
    }, 500);
    
    setTimeout(() => {
        addActivityLog('Validating constraints and requirements...', 'info', 'check-circle');
    }, 1000);
    
    setTimeout(() => {
        addActivityLog('Setting up CP-SAT solver...', 'info', 'cpu');
    }, 1500);
    
    setTimeout(() => {
        addActivityLog('Creating decision variables...', 'info', 'diagram-3');
    }, 2000);
    
    setTimeout(() => {
        addActivityLog('Adding assignment constraints...', 'info', 'link');
    }, 3000);
    
    setTimeout(() => {
        addActivityLog('Calculating inter-location movements (ILM)...', 'info', 'arrow-left-right');
    }, 4000);
    
    setTimeout(() => {
        addActivityLog('Applying date and capacity constraints...', 'info', 'calendar-check');
    }, 5000);
    
    setTimeout(() => {
        addActivityLog('Setting optimization objective...', 'info', 'bullseye');
    }, 6000);
    
    setTimeout(() => {
        addActivityLog('Starting solver with portfolio search...', 'warning', 'play-circle');
    }, 7000);
    
    // Add periodic progress updates during solving
    const progressMessages = [
        'Exploring solution space...',
        'Evaluating constraint satisfaction...',
        'Optimizing cost and makespan...',
        'Searching for better solutions...',
        'Refining assignment quality...',
        'Checking feasibility bounds...',
        'Applying local search improvements...',
        'Validating solution integrity...'
    ];
    
    let messageIndex = 0;
    const progressInterval = setInterval(() => {
        if (messageIndex < progressMessages.length) {
            addActivityLog(progressMessages[messageIndex], 'info', 'arrow-repeat');
            messageIndex++;
        } else {
            // Cycle through messages
            messageIndex = 0;
        }
    }, 2000);
    
    // Final completion messages
    setTimeout(() => {
        clearInterval(progressInterval);
        addActivityLog('Solver completed successfully', 'success', 'check-circle-fill');
        
        setTimeout(() => {
            addActivityLog('Extracting optimal solution...', 'info', 'download');
        }, 500);
        
        setTimeout(() => {
            addActivityLog('Creating assignment records...', 'info', 'file-earmark-plus');
        }, 1000);
        
        setTimeout(() => {
            addActivityLog('Calculating final costs and statistics...', 'info', 'calculator');
        }, 1500);
        
        setTimeout(() => {
            addActivityLog('Optimization completed!', 'success', 'trophy');
        }, 2000);
        
    }, Math.max(0, (timeLimit - 3) * 1000)); // Complete a few seconds before timeout
}

function showOptimizationActivityError(errorMessage) {
    addActivityLog(`Error: ${errorMessage}`, 'error', 'exclamation-triangle');
}

// Gantt chart functionality
// Global variables for Gantt chart
let ganttChart = null;

function updateGanttChart(schedule) {
    if (!schedule || !schedule.assignments) {
        document.getElementById('gantt-container').innerHTML = 
            `<div class="d-flex align-items-center justify-content-center h-100 text-muted">
                <div class="text-center">
                    <i class="bi bi-bar-chart fs-1"></i>
                    <p class="mt-2">No schedule data available</p>
                </div>
            </div>`;
        return;
    }

    currentSchedule = schedule;
    
    // Convert schedule assignments to Frappe Gantt format
    const tasks = schedule.assignments.map((assignment, index) => {
        // Add safety checks for date parsing
        let startDate, endDate;
        
        try {
            startDate = assignment.well_start_date ? new Date(assignment.well_start_date) : new Date();
            endDate = assignment.well_end_date ? new Date(assignment.well_end_date) : new Date();
            
            // Check if dates are valid
            if (isNaN(startDate.getTime())) {
                console.warn(`Invalid well_start_date for assignment ${index}:`, assignment.well_start_date);
                startDate = new Date();
            }
            if (isNaN(endDate.getTime())) {
                console.warn(`Invalid well_end_date for assignment ${index}:`, assignment.well_end_date);
                endDate = new Date(startDate.getTime() + 24 * 60 * 60 * 1000); // Default to 1 day after start
            }
        } catch (error) {
            console.error(`Error parsing dates for assignment ${index}:`, error);
            startDate = new Date();
            endDate = new Date(startDate.getTime() + 24 * 60 * 60 * 1000);
        }
        
        return {
            id: `task-${index}`,
            name: assignment.well_name || `Well ${assignment.well}`,
            start: startDate.toISOString().split('T')[0],
            end: endDate.toISOString().split('T')[0],
            progress: 0, // Can be updated based on actual progress
            custom_class: `rig-${assignment.rig}`,
            details: {
                assignment_id: assignment.id,
                rig_name: assignment.rig_name || `Rig ${assignment.rig}`,
                rig_id: assignment.rig,
                well_id: assignment.well,
                drilling_cost: assignment.drilling_cost || 0,
                validation_checks: assignment.validation_checks || {}
            }
        };
        
        // Debug logging for assignment IDs
        console.log(`Task ${index}: assignment.id = "${assignment.id}" (type: ${typeof assignment.id})`);
        
        return taskObj;
    });

    // Clear the container and create Gantt chart
    const container = document.getElementById('gantt-container');
    if (!container) {
        console.log('No gantt-container found, skipping Gantt chart update');
        return;
    }
    container.innerHTML = '<div id="gantt"></div>';
    
    try {
        // Initialize Frappe Gantt
        ganttChart = new Gantt("#gantt", tasks, {
            header_height: 50,
            column_width: 30,
            step: 24,
            view_modes: ['Quarter Day', 'Half Day', 'Day', 'Week', 'Month'],
            bar_height: 20,
            bar_corner_radius: 3,
            arrow_curve: 5,
            padding: 18,
            view_mode: 'Day',
            date_format: 'YYYY-MM-DD',
            language: 'en',
            custom_popup_html: function(task) {
                const details = task.details || {};
                return `
                    <div class="details-container" style="padding: 10px; min-width: 200px;">
                        <h6 style="margin-bottom: 10px; color: #333;">${task.name}</h6>
                        <p style="margin: 5px 0;"><strong>Rig:</strong> ${details.rig_name}</p>
                        <p style="margin: 5px 0;"><strong>Start:</strong> ${task.start}</p>
                        <p style="margin: 5px 0;"><strong>End:</strong> ${task.end}</p>
                        <p style="margin: 5px 0;"><strong>Duration:</strong> ${task.duration || 'N/A'} days</p>
                        ${details.drilling_cost ? `<p style="margin: 5px 0;"><strong>Cost:</strong> ₹${(details.drilling_cost / 10000000).toFixed(2)} Cr</p>` : ''}
                    </div>
                `;
            },
            on_click: function(task) {
                showTaskDetails(task);
            },
            on_date_change: function(task, start, end) {
                handleTaskDateChange(task, start, end);
            },
            on_progress_change: function(task, progress) {
                handleTaskProgressChange(task, progress);
            },
            on_view_change: function(mode) {
                console.log('View mode changed to:', mode);
            }
        });

        // Add custom styling for different rigs
        addCustomGanttStyles();
        
        // Update schedule selector
        updateScheduleSelector();
        
        showAlert(`Gantt chart updated with ${tasks.length} assignments`, 'success');
        
    } catch (error) {
        console.error('Error creating Gantt chart:', error);
        container.innerHTML = 
            `<div class="alert alert-danger">
                Error creating Gantt chart: ${error.message}
            </div>`;
    }
}

function addCustomGanttStyles() {
    // Add custom CSS for different rig colors
    if (!document.getElementById('gantt-custom-styles')) {
        const style = document.createElement('style');
        style.id = 'gantt-custom-styles';
        style.textContent = `
            .gantt .bar.rig-1 { fill: #1f77b4; }
            .gantt .bar.rig-2 { fill: #ff7f0e; }
            .gantt .bar.rig-3 { fill: #2ca02c; }
            .gantt .bar.rig-4 { fill: #d62728; }
            .gantt .bar.rig-5 { fill: #9467bd; }
            .gantt .bar.rig-6 { fill: #8c564b; }
            .gantt .bar.rig-7 { fill: #e377c2; }
            .gantt .bar.rig-8 { fill: #7f7f7f; }
            .gantt .bar.rig-9 { fill: #bcbd22; }
            .gantt .bar.rig-10 { fill: #17becf; }
            
            .gantt .bar:hover {
                opacity: 0.8;
                cursor: pointer;
            }
            
            #gantt {
                overflow: auto;
                height: 100%;
            }
        `;
        document.head.appendChild(style);
    }
}

function showTaskDetails(task) {
    const details = task.details || {};
    const modalContent = `
        <div class="modal fade" id="taskDetailsModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Task Details: ${task.name}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="row">
                            <div class="col-6">
                                <strong>Rig:</strong> ${details.rig_name}<br>
                                <strong>Start Date:</strong> ${task.start}<br>
                                <strong>End Date:</strong> ${task.end}<br>
                                <strong>Progress:</strong> ${task.progress}%
                            </div>
                            <div class="col-6">
                                ${details.drilling_cost ? `<strong>Drilling Cost:</strong> ₹${(details.drilling_cost / 10000000).toFixed(2)} Cr<br>` : ''}
                                <strong>Rig ID:</strong> ${details.rig_id}<br>
                                <strong>Well ID:</strong> ${details.well_id}<br>
                                <strong>Assignment ID:</strong> ${details.assignment_id}
                            </div>
                        </div>
                        ${details.validation_checks ? `
                            <hr>
                            <h6>Validation Checks:</h6>
                            <div class="small">
                                ${Object.entries(details.validation_checks).map(([key, value]) => 
                                    `<span class="badge ${value === 'OK' ? 'bg-success' : 'bg-danger'} me-1">${key}: ${value}</span>`
                                ).join('')}
                            </div>
                        ` : ''}
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        <button type="button" class="btn btn-danger" onclick="console.log('Delete button clicked:', '${task.id}', '${task.name}', '${details.assignment_id}'); deleteTaskFromSchedule('${task.id}', '${task.name}', '${details.assignment_id}')" data-bs-dismiss="modal">Delete Task</button>
                        <button type="button" class="btn btn-primary" onclick="editTask('${task.id}')">Edit Task</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal if any
    const existingModal = document.getElementById('taskDetailsModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Add modal to page and show
    document.body.insertAdjacentHTML('beforeend', modalContent);
    const modal = new bootstrap.Modal(document.getElementById('taskDetailsModal'));
    modal.show();
}

function handleTaskDateChange(task, start, end) {
    console.log(`Task ${task.name} date changed:`, { start, end });
    
    // Here you would typically call your backend API to validate and update the schedule
    // For now, just show a notification
    showAlert(`Task "${task.name}" rescheduled from ${start} to ${end}`, 'info');
    
    // TODO: Implement backend API call for constraint validation
    // validateTaskReschedule(task, start, end);
}

function handleTaskProgressChange(task, progress) {
    console.log(`Task ${task.name} progress changed to: ${progress}%`);
    showAlert(`Task "${task.name}" progress updated to ${progress}%`, 'info');
    
    // TODO: Implement backend API call to update task progress
    // updateTaskProgress(task.id, progress);
}

function editTask(taskId) {
    console.log('Edit task:', taskId);
    // TODO: Implement task editing functionality
    showAlert('Task editing functionality coming soon!', 'info');
    
    // Close the modal
    const modal = bootstrap.Modal.getInstance(document.getElementById('taskDetailsModal'));
    if (modal) {
        modal.hide();
    }
}

function updateScheduleSelector() {
    const selector = document.getElementById('schedule-selector');
    if (!selector) return;
    
    // Clear existing options except the first one
    selector.innerHTML = '<option value="">Select a schedule...</option>';
    
    // Add current schedule if available
    if (currentSchedule) {
        const option = document.createElement('option');
        option.value = currentSchedule.id;
        option.textContent = `${currentSchedule.name} (Current)`;
        option.selected = true;
        selector.appendChild(option);
    }
    
    // Add other schedules from schedulesData
    if (schedulesData && schedulesData.length > 0) {
        schedulesData.forEach(schedule => {
            if (!currentSchedule || schedule.id !== currentSchedule.id) {
                const option = document.createElement('option');
                option.value = schedule.id;
                option.textContent = schedule.name;
                selector.appendChild(option);
            }
        });
    }
}

function loadGanttChart() {
    const selector = document.getElementById('schedule-selector');
    const scheduleId = selector.value;
    
    // Enable/disable download buttons based on schedule selection
    const downloadExcelBtn = document.getElementById('download-excel-btn');
    const downloadCSVBtn = document.getElementById('download-csv-btn');
    
    if (!scheduleId) {
        document.getElementById('gantt-container').innerHTML = 
            `<div class="d-flex align-items-center justify-content-center h-100 text-muted">
                <div class="text-center">
                    <i class="bi bi-bar-chart fs-1"></i>
                    <p class="mt-2">Select a completed schedule to view the Gantt chart</p>
                </div>
            </div>`;
        
        // Disable download buttons
        if (downloadExcelBtn) downloadExcelBtn.disabled = true;
        if (downloadCSVBtn) downloadCSVBtn.disabled = true;
        return;
    }
    
    // Enable download buttons
    if (downloadExcelBtn) downloadExcelBtn.disabled = false;
    if (downloadCSVBtn) downloadCSVBtn.disabled = false;
    
    const schedule = schedulesData.find(s => s.id == scheduleId);
    if (schedule) {
        updateGanttChart(schedule);
    } else {
        showAlert('Schedule not found', 'danger');
    }
}

// Schedule management
async function loadSchedule(scheduleId) {
    try {
        const schedule = await apiRequest(`${ENDPOINTS.schedules}${scheduleId}/`);
        currentSchedule = schedule;
        updateGanttChart(schedule);
        showAlert(`Loaded schedule: ${schedule.name}`, 'info');
    } catch (error) {
        console.error('Error loading schedule:', error);
        showAlert(`Failed to load schedule: ${error.message}`, 'danger');
    }
}

// Export functionality
function exportSchedule() {
    if (!currentSchedule) {
        showAlert('No schedule to export', 'warning');
        return;
    }
    
    const dataStr = JSON.stringify(currentSchedule, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    
    const link = document.createElement('a');
    link.href = URL.createObjectURL(dataBlob);
    link.download = `schedule_${currentSchedule.name}_${new Date().toISOString().split('T')[0]}.json`;
    link.click();
}

// Initialize application
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM Content Loaded - Initializing iDRS...');
    
    // Initialize data arrays with safety checks
    initializeData();
    
    // Pre-load company codes map for location filtering
    loadCompanyCodesMap();
    
    // Only load data on dashboard page to prevent duplicate loads on other pages
    const isDashboardPage = window.location.pathname === '/' || 
                           window.location.pathname.endsWith('/dashboard') ||
                           window.location.pathname.endsWith('/dashboard/') ||
                           document.getElementById('dashboard-page-indicator');
    
    const isDataManagementPage = window.location.pathname.includes('data-management') ||
                                 document.getElementById('data-management-page-indicator');
    
    if (isDashboardPage) {
        console.log('Dashboard page detected - loading data');
        loadData();
    } else if (isDataManagementPage) {
        console.log('Data Management page detected - skipping loadData() (page has its own initialization)');
    } else {
        console.log('Non-dashboard page detected - skipping automatic data load');
    }
    
    // Note: Data management page has its own DOMContentLoaded handler in data_management.html
    // that handles its specific initialization without calling loadData()
    
    // Setup file upload
    setupFileUpload();
    
    // Setup event listeners
    const createScheduleBtn = document.getElementById('create-schedule-btn');
    if (createScheduleBtn) {
        createScheduleBtn.addEventListener('click', createSchedule);
    }

    // Setup schedule form submission
    const scheduleForm = document.getElementById('schedule-form');
    if (scheduleForm) {
        scheduleForm.addEventListener('submit', function(e) {
            e.preventDefault();
            createSchedule();
        });
    }
    
    // Setup form submissions with proper event handling
    const rigsUploadForm = document.getElementById('rig-upload-form');
    if (rigsUploadForm) {
        rigsUploadForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const fileInput = document.getElementById('rig-file');
            if (fileInput && fileInput.files.length > 0) {
                handleFileUpload({ target: fileInput }, 'rigs');
            } else {
                showAlert('Please select a CSV file to upload', 'warning');
            }
        });
    }
    
    const wellsUploadForm = document.getElementById('well-upload-form');
    if (wellsUploadForm) {
        wellsUploadForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const fileInput = document.getElementById('well-file');
            if (fileInput && fileInput.files.length > 0) {
                handleFileUpload({ target: fileInput }, 'wells');
            } else {
                showAlert('Please select a CSV file to upload', 'warning');
            }
        });
    }

    // Auto-calculate total duration when drilling/testing days change
    const drlDaysInput = document.getElementById('well-drl-days');
    const ptDaysInput = document.getElementById('well-pt-days');
    const durationInput = document.getElementById('well-duration');
    
    function calculateDuration() {
        const drlDays = parseInt(drlDaysInput.value) || 0;
        const ptDays = parseInt(ptDaysInput.value) || 0;
        durationInput.value = drlDays + ptDays;
    }
    
    if (drlDaysInput && ptDaysInput && durationInput) {
        drlDaysInput.addEventListener('input', calculateDuration);
        ptDaysInput.addEventListener('input', calculateDuration);
    }
    
    // Load management tables when page loads (only if elements exist)
    if (document.getElementById('rigs-table-body')) {
        loadRigsTable();
    }
    if (document.getElementById('wells-table-body')) {
        loadWellsTable();
    }
    
    // Initialize download buttons as disabled
    const downloadExcelBtn = document.getElementById('download-excel-btn');
    const downloadCSVBtn = document.getElementById('download-csv-btn');
    if (downloadExcelBtn) downloadExcelBtn.disabled = true;
    if (downloadCSVBtn) downloadCSVBtn.disabled = true;
    
    // Load schedules list if the element exists
    const schedulesTableElement = document.getElementById('schedules-table-body');
    console.log('Checking for schedules table element:', !!schedulesTableElement);
    if (schedulesTableElement) {
        console.log('Schedules table element found, calling loadSchedulesList...');
        loadSchedulesList();
    } else {
        console.log('Schedules table element not found, skipping loadSchedulesList');
    }
    
    // Setup keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey || e.metaKey) {
            switch(e.key) {
                case 's':
                    e.preventDefault();
                    if (currentSchedule) {
                        exportSchedule();
                    }
                    break;
                case 'n':
                    e.preventDefault();
                    const scheduleNameInput = document.getElementById('schedule-name');
                    if (scheduleNameInput) {
                        scheduleNameInput.focus();
                    }
                    break;
            }
        }
    });
    
    console.log('iDRS initialization complete');
});

// Generate Gantt Chart
function generateGanttChart() {
    fetch('/api/schedules/')
        .then(response => response.json())
        .then(schedules => {
            if (schedules.length === 0) {
                document.getElementById('gantt-chart').innerHTML = 
                    '<div class="alert alert-info">No schedules available. Upload data and run optimization first.</div>';
                return;
            }
            
            // Use the most recent schedule
            const latestSchedule = schedules[schedules.length - 1];
            updateGanttChart(latestSchedule);
        })
        .catch(error => {
            console.error('Error loading schedules:', error);
            document.getElementById('gantt-chart').innerHTML = 
                '<div class="alert alert-danger">Error loading schedule data.</div>';
        });
}

// Helper functions for multi-select boxes
function selectAllRigs() {
    const selectedRigs = document.getElementById('selected-rigs');
    if (selectedRigs) {
        for (let i = 0; i < selectedRigs.options.length; i++) {
            selectedRigs.options[i].selected = true;
        }
        showAlert('All rigs selected', 'info');
    }
}

function selectAllWells() {
    const selectedWells = document.getElementById('selected-wells');
    if (selectedWells) {
        for (let i = 0; i < selectedWells.options.length; i++) {
            selectedWells.options[i].selected = true;
        }
        showAlert('All wells selected', 'info');
    }
}

// Helper functions for form interactions
function selectAllRigs() {
    const selectedRigs = document.getElementById('selected-rigs');
    if (selectedRigs) {
        for (let option of selectedRigs.options) {
            if (!option.disabled) {
                option.selected = true;
            }
        }
    }
}

function selectAllWells() {
    const selectedWells = document.getElementById('selected-wells');
    if (selectedWells) {
        for (let option of selectedWells.options) {
            if (!option.disabled) {
                option.selected = true;
            }
        }
    }
}

// Refresh functions for data management section
async function loadRigs() {
    try {
        setLoading('current-rigs-count', true);
        const rigsResponse = await apiRequest(ENDPOINTS.rigs);
        rigsData = rigsResponse.results || rigsResponse || [];
        
        // Only update counters if NOT on data management page
        const isDataManagementPage = document.getElementById('data-management-page-indicator');
        if (!isDataManagementPage) {
            updateDataManagementCounters();
            populateDropdowns();
        }
        
        showAlert(`Loaded ${rigsData.length} rigs successfully!`, 'success');
    } catch (error) {
        console.error('Error loading rigs:', error);
        showAlert(`Error loading rigs: ${error.message}`, 'danger');
    } finally {
        setLoading('current-rigs-count', false);
    }
}

async function loadWells() {
    try {
        setLoading('current-wells-count', true);
        const wellsResponse = await apiRequest(ENDPOINTS.wells);
        wellsData = wellsResponse.results || wellsResponse || [];
        
        // Only update counters if NOT on data management page
        const isDataManagementPage = document.getElementById('data-management-page-indicator');
        if (!isDataManagementPage) {
            updateDataManagementCounters();
            populateDropdowns();
        }
        
        showAlert(`Loaded ${wellsData.length} wells successfully!`, 'success');
    } catch (error) {
        console.error('Error loading wells:', error);
        showAlert(`Error loading wells: ${error.message}`, 'danger');
    } finally {
        setLoading('current-wells-count', false);
    }
}

// Auto-refresh data every 5 minutes
setInterval(loadData, 5 * 60 * 1000);

// Handle window resize for responsive charts
window.addEventListener('resize', function() {
    if (currentSchedule && ganttChart) {
        // Frappe Gantt handles resize automatically
        ganttChart.refresh();
    }
});

// Function to view gantt chart - redirect to Interactive Gantt Chart page
function viewGanttChart() {
    window.location.href = '/gantt/';
}

// Function to view a specific schedule
function viewSchedule(scheduleId) {
    const schedule = schedulesData.find(s => s.id === scheduleId);
    if (schedule) {
        updateGanttChart(schedule);
        showAlert(`Viewing schedule: ${schedule.name}`, 'info');
        
        // Scroll to the Gantt chart section
        viewGanttChart();
    } else {
        showAlert('Schedule not found', 'danger');
    }
}

// ===== RIG AND WELL MANAGEMENT FUNCTIONS =====

// Table sorting state
let rigsSortColumn = -1;
let rigsSortAscending = true;
let wellsSortColumn = -1;
let wellsSortAscending = true;

// Sort rigs table by column index
function sortRigsTable(columnIndex) {
    const table = document.getElementById('rigs-table');
    const tbody = document.getElementById('rigs-table-body');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    // Toggle sort direction if clicking the same column
    if (rigsSortColumn === columnIndex) {
        rigsSortAscending = !rigsSortAscending;
    } else {
        rigsSortColumn = columnIndex;
        rigsSortAscending = true;
    }
    
    rows.sort((a, b) => {
        const cellA = a.cells[columnIndex];
        const cellB = b.cells[columnIndex];
        
        let aValue, bValue;
        
        // Extract text content based on column
        if (columnIndex === 0) {
            // Name - use strong tag text
            aValue = cellA.querySelector('strong')?.textContent || cellA.textContent;
            bValue = cellB.querySelector('strong')?.textContent || cellB.textContent;
        } else if (columnIndex === 1) {
            // Type - use badge text
            aValue = cellA.querySelector('.badge')?.textContent || cellA.textContent;
            bValue = cellB.querySelector('.badge')?.textContent || cellB.textContent;
        } else if (columnIndex === 2) {
            // Capacity - extract number
            aValue = parseInt(cellA.textContent.replace(/[^0-9]/g, '')) || 0;
            bValue = parseInt(cellB.textContent.replace(/[^0-9]/g, '')) || 0;
        } else if (columnIndex === 3) {
            // Daily Cost - extract number from Lakhs format
            aValue = parseFloat(cellA.textContent.replace(/[^0-9.]/g, '')) || 0;
            bValue = parseFloat(cellB.textContent.replace(/[^0-9.]/g, '')) || 0;
        }
        
        // Compare values
        let comparison = 0;
        if (typeof aValue === 'string') {
            comparison = aValue.localeCompare(bValue);
        } else {
            comparison = aValue - bValue;
        }
        
        return rigsSortAscending ? comparison : -comparison;
    });
    
    // Reorder rows
    rows.forEach(row => tbody.appendChild(row));
}

// Sort wells table by column index
function sortWellsTable(columnIndex) {
    const table = document.getElementById('wells-table');
    const tbody = document.getElementById('wells-table-body');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    // Toggle sort direction if clicking the same column
    if (wellsSortColumn === columnIndex) {
        wellsSortAscending = !wellsSortAscending;
    } else {
        wellsSortColumn = columnIndex;
        wellsSortAscending = true;
    }
    
    rows.sort((a, b) => {
        const cellA = a.cells[columnIndex];
        const cellB = b.cells[columnIndex];
        
        let aValue, bValue;
        
        // Extract text content based on column
        if (columnIndex === 0) {
            // Name - use strong tag text
            aValue = cellA.querySelector('strong')?.textContent || cellA.textContent;
            bValue = cellB.querySelector('strong')?.textContent || cellB.textContent;
        } else if (columnIndex === 1 || columnIndex === 2 || columnIndex === 3) {
            // Asset ID, Type, Priority - use text or badge text
            const badgeA = cellA.querySelector('.badge');
            const badgeB = cellB.querySelector('.badge');
            aValue = badgeA ? badgeA.textContent : cellA.textContent;
            bValue = badgeB ? badgeB.textContent : cellB.textContent;
        } else if (columnIndex === 4) {
            // Duration - extract number
            aValue = parseInt(cellA.textContent.replace(/[^0-9]/g, '')) || 0;
            bValue = parseInt(cellB.textContent.replace(/[^0-9]/g, '')) || 0;
        }
        
        // Compare values
        let comparison = 0;
        if (typeof aValue === 'string') {
            comparison = aValue.localeCompare(bValue);
        } else {
            comparison = aValue - bValue;
        }
        
        return wellsSortAscending ? comparison : -comparison;
    });
    
    // Reorder rows
    rows.forEach(row => tbody.appendChild(row));
}

// Load and display rigs in management table
async function loadRigsTable() {
    try {
        // Ensure company codes map is loaded for location filtering
        if (Object.keys(companyCodesMap).length === 0) {
            await loadCompanyCodesMap();
        }
        
        // Get current location filter if it exists
        const locationSelector = document.getElementById('location-selector');
        const currentLocationFilter = locationSelector ? locationSelector.value : '';
        
        // Fetch ALL rigs (no server-side filter) - we'll filter client-side
        let url = ENDPOINTS.rigs;
        
        // Fetch ALL pages of rigs data
        let allRigs = [];
        let nextUrl = url;
        
        while (nextUrl) {
            const response = await fetch(nextUrl, {
                credentials: 'same-origin'
            });
            const data = await response.json();
            
            // Add results from this page
            const results = data.results || data;
            if (Array.isArray(results)) {
                allRigs = allRigs.concat(results);
            } else if (Array.isArray(data)) {
                allRigs = allRigs.concat(data);
            }
            
            // Check for next page
            nextUrl = data.next || null;
        }
        
        // Apply client-side location filtering
        if (currentLocationFilter && typeof currentLocationFilter === 'string' && currentLocationFilter.trim() !== '') {
            rigsData = allRigs.filter(rig => {
                const rigLocation = getLocationFromData(rig);
                return rigLocation && rigLocation.toLowerCase() === currentLocationFilter.toLowerCase();
            });
            console.log(`Filtered rigs by location "${currentLocationFilter}": ${rigsData.length} of ${allRigs.length}`);
        } else {
            rigsData = allRigs;
        }
        
        const tableBody = document.getElementById('rigs-table-body');
        if (!tableBody) {
            console.warn('rigs-table-body element not found');
            return;
        }
        
        if (!rigsData || rigsData.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No rigs found</td></tr>';
            return;
        }
        
        tableBody.innerHTML = rigsData.map(rig => {
            // Format cost in Lakhs (K, L, Cr format)
            const cost = parseFloat(rig.daily_cost_inr);
            let formattedCost;
            
            if (cost >= 10000000) { // 1 Crore or more
                const crores = (cost / 10000000).toFixed(2).replace(/\.?0+$/, '');
                formattedCost = `₹${crores}Cr`;
            } else if (cost >= 100000) { // 1 Lakh or more
                const lakhs = (cost / 100000).toFixed(2).replace(/\.?0+$/, '');
                formattedCost = `₹${lakhs}L`;
            } else if (cost >= 1000) { // 1 Thousand or more
                const thousands = (cost / 1000).toFixed(2).replace(/\.?0+$/, '');
                formattedCost = `₹${thousands}K`;
            } else {
                formattedCost = `₹${cost}`;
            }
            
            // Check if soft-deleted
            const isDeleted = rig.is_deleted === true;
            const deletedBadge = isDeleted ? '<span class="badge bg-danger ms-2">DELETED</span>' : '';
            const rowStyle = isDeleted ? 'opacity: 0.6; background-color: #fee;' : '';
            const displayName = rig.display_name || rig.name;  // Use clean display name
            
            return `
            <tr data-asset-id="${rig.asset_id || ''}" data-rig-id="${rig.id}" style="cursor: pointer; ${rowStyle}" onclick="showRigDetails('${rig.id}')" title="Click to view details">
                <td data-asset-id="${rig.asset_id || ''}">
                    <strong>${displayName}${deletedBadge}</strong><br>
                    <small class="text-muted">${rig.start_date} to ${rig.end_date}</small>
                </td>
                <td>
                    <span class="badge bg-${rig.rig_type === 'Mobile' ? 'primary' : 'secondary'}">${rig.rig_type}</span>
                </td>
                <td>${rig.rig_capacity_hp} HP</td>
                <td>${formattedCost}</td>
                <td style="white-space: nowrap;">
                    <button class="btn btn-sm btn-outline-primary me-1" onclick="event.stopPropagation(); editRig('${rig.id}')" title="Edit">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="event.stopPropagation(); deleteRig('${rig.id}', '${rig.name}')" title="Delete">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            </tr>
        `}).join('');
        
        // Apply pagination after table is loaded
        if (typeof paginateRigsTable === 'function') {
            paginateRigsTable(1);
        }
        
    } catch (error) {
        console.error('Error loading rigs:', error);
        const tableBody = document.getElementById('rigs-table-body');
        if (tableBody) {
            tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Error loading rigs</td></tr>';
        }
    }
}

// Load and display wells in management table
async function loadWellsTable() {
    try {
        // Ensure company codes map is loaded for location filtering
        if (Object.keys(companyCodesMap).length === 0) {
            await loadCompanyCodesMap();
        }
        
        // Get current location filter if it exists
        const locationSelector = document.getElementById('location-selector');
        const currentLocationFilter = locationSelector ? locationSelector.value : '';
        
        // Fetch ALL wells (no server-side filter) - we'll filter client-side
        let url = ENDPOINTS.wells;
        
        // Fetch ALL pages of wells data
        let allWells = [];
        let nextUrl = url;
        
        while (nextUrl) {
            const response = await fetch(nextUrl, {
                credentials: 'same-origin'
            });
            const data = await response.json();
            
            // Add results from this page
            const results = data.results || data;
            if (Array.isArray(results)) {
                allWells = allWells.concat(results);
            } else if (Array.isArray(data)) {
                allWells = allWells.concat(data);
            }
            
            // Check for next page
            nextUrl = data.next || null;
        }
        
        // Apply client-side location filtering
        if (currentLocationFilter && typeof currentLocationFilter === 'string' && currentLocationFilter.trim() !== '') {
            wellsData = allWells.filter(well => {
                const wellLocation = getLocationFromData(well);
                return wellLocation && wellLocation.toLowerCase() === currentLocationFilter.toLowerCase();
            });
            console.log(`Filtered wells by location "${currentLocationFilter}": ${wellsData.length} of ${allWells.length}`);
        } else {
            wellsData = allWells;
        }
        
        const tableBody = document.getElementById('wells-table-body');
        if (!tableBody) {
            console.warn('wells-table-body element not found');
            return;
        }
        
        if (!wellsData || wellsData.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="20" class="text-center text-muted">No wells found</td></tr>';
            return;
        }
        
        tableBody.innerHTML = wellsData.map((well, index) => {
            // Check if well has duration mismatch warning
            const hasWarning = well.has_duration_mismatch;
            const warningMessage = well.duration_validation_message || '';
            const warningIcon = hasWarning ? `<i class="bi bi-exclamation-triangle-fill text-warning ms-2" title="${warningMessage}" style="cursor: help;"></i>` : '';
            
            // Check if soft-deleted
            const isDeleted = well.is_deleted === true;
            const deletedBadge = isDeleted ? '<span class="badge bg-danger ms-2">DELETED</span>' : '';
            const rowStyle = isDeleted ? 'opacity: 0.6; background-color: #fee;' : '';
            const displayName = well.display_name || well.name;  // Use clean display name
            
            // Get location
            const location = well.location_value || well.location_name || well.asset_id || 'N/A';
            
            return `
            <tr style="${rowStyle}">
                <td style="white-space: nowrap;">${index + 1}</td>
                <td style="white-space: nowrap;">
                    <strong>${displayName}${deletedBadge}</strong>${warningIcon}
                </td>
                <td style="white-space: nowrap;">${location}</td>
                <td style="white-space: nowrap;">${well.field_name || well.field || 'N/A'}</td>
                <td style="white-space: nowrap;">
                    <span class="badge bg-${well.well_type === 'EXP' ? 'info' : 'success'}">${well.well_type || 'N/A'}</span>
                </td>
                <td style="white-space: nowrap;">${well.profile || well.well_profile || 'N/A'}</td>
                <td style="white-space: nowrap;">${well.depth || 'N/A'}</td>
                <td style="white-space: nowrap;">${well.rig_capacity_hp || well.rig_capacity_required_hp || 'N/A'}</td>
                <td style="white-space: nowrap;">${well.drl_days !== null && well.drl_days !== undefined ? well.drl_days : 'N/A'}</td>
                <td style="white-space: nowrap;">${well.pt_days !== null && well.pt_days !== undefined ? well.pt_days : 'N/A'}</td>
                <td style="white-space: nowrap;">${well.duration || 'N/A'} days</td>
                <td style="white-space: nowrap;">${well.latitude !== null && well.latitude !== undefined ? parseFloat(well.latitude).toFixed(6) : 'N/A'}</td>
                <td style="white-space: nowrap;">${well.longitude !== null && well.longitude !== undefined ? parseFloat(well.longitude).toFixed(6) : 'N/A'}</td>
                <td style="white-space: nowrap;">${well.rtd || 'N/A'}</td>
                <td style="white-space: nowrap;">${well.bop_stack || 'N/A'}</td>
                <td style="white-space: nowrap;">${well.tds_requirement || well.tds || 'N/A'}</td>
                <td style="white-space: nowrap;">${well.footprint || 'N/A'}</td>
                <td style="white-space: nowrap;">${well.preferred_rig || 'N/A'}</td>
                <td style="white-space: nowrap;">
                    <span class="badge bg-${well.priority === 'HIGH' ? 'danger' : well.priority === 'MEDIUM' ? 'warning' : 'secondary'}">${well.priority || 'N/A'}</span>
                </td>
                <td style="white-space: nowrap;">
                    <button class="btn btn-sm btn-outline-primary me-1" onclick="event.stopPropagation(); editWell('${well.id}')" title="Edit">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="event.stopPropagation(); deleteWell('${well.id}', '${well.name}')" title="Delete">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            </tr>
        `;
        }).join('');
        
        // Apply pagination after table is loaded
        if (typeof paginateWellsTable === 'function') {
            paginateWellsTable(1);
        }
        
    } catch (error) {
        console.error('Error loading wells:', error);
        const tableBody = document.getElementById('wells-table-body');
        if (tableBody) {
            tableBody.innerHTML = '<tr><td colspan="20" class="text-center text-danger">Error loading wells</td></tr>';
        }
    }
}

// Save new rig
async function saveRig() {
    const form = document.getElementById('add-rig-form');
    const formData = new FormData(form);
    
    // Convert FormData to JSON
    const rigData = {};
    for (let [key, value] of formData.entries()) {
        rigData[key] = value;
    }
    
    try {
        const response = await fetch(ENDPOINTS.rigs, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('idrs_csrftoken')
            },
            body: JSON.stringify(rigData)
        });
        
        if (response.ok) {
            const newRig = await response.json();
            showAlert(`Rig "${newRig.name}" added successfully!`, 'success');
            
            // Close modal and refresh data
            const modal = bootstrap.Modal.getInstance(document.getElementById('addRigModal'));
            modal.hide();
            form.reset();
            
            await loadRigsTable();
            await loadRigs(); // Refresh dashboard stats
        } else {
            const errorData = await response.json();
            showAlert(`Error adding rig: ${errorData.message || 'Unknown error'}`, 'danger');
        }
    } catch (error) {
        console.error('Error saving rig:', error);
        showAlert('Network error while saving rig', 'danger');
    }
}

// Save new well
async function saveWell() {
    const form = document.getElementById('add-well-form');
    const formData = new FormData(form);
    
    // Convert FormData to JSON
    const wellData = {};
    for (let [key, value] of formData.entries()) {
        wellData[key] = value;
    }
    
    // Calculate total duration from drilling and testing days
    const drlDays = parseInt(wellData.drl_days) || 0;
    const ptDays = parseInt(wellData.pt_days) || 0;
    wellData.duration = drlDays + ptDays;
    
    try {
        const response = await fetch(ENDPOINTS.wells, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('idrs_csrftoken')
            },
            body: JSON.stringify(wellData)
        });
        
        if (response.ok) {
            const newWell = await response.json();
            showAlert(`Well "${newWell.name}" added successfully!`, 'success');
            
            // Close modal and refresh data
            const modal = bootstrap.Modal.getInstance(document.getElementById('addWellModal'));
            modal.hide();
            form.reset();
            
            await loadWellsTable();
            await loadWells(); // Refresh dashboard stats
        } else {
            const errorData = await response.json();
            showAlert(`Error adding well: ${errorData.message || 'Unknown error'}`, 'danger');
        }
    } catch (error) {
        console.error('Error saving well:', error);
        showAlert('Network error while saving well', 'danger');
    }
}

// Delete rig
async function deleteRig(rigId, rigName) {
    if (!confirm(`Are you sure you want to delete rig "${rigName}"? This action cannot be undone.`)) {
        return;
    }
    
    try {
        const response = await fetch(`${ENDPOINTS.rigs}${rigId}/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCookie('idrs_csrftoken')
            }
        });
        
        if (response.ok) {
            showAlert(`Rig "${rigName}" deleted successfully!`, 'success');
            await loadRigsTable();
            await loadRigs(); // Refresh dashboard stats
        } else {
            const errorData = await response.json();
            showAlert(`Error deleting rig: ${errorData.message || 'Unknown error'}`, 'danger');
        }
    } catch (error) {
        console.error('Error deleting rig:', error);
        showAlert('Network error while deleting rig', 'danger');
    }
}

// Delete well
async function deleteWell(wellId, wellName) {
    if (!confirm(`Are you sure you want to delete well "${wellName}"? This action cannot be undone.`)) {
        return;
    }
    
    try {
        const response = await fetch(`${ENDPOINTS.wells}${wellId}/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCookie('idrs_csrftoken')
            }
        });
        
        if (response.ok) {
            showAlert(`Well "${wellName}" deleted successfully!`, 'success');
            await loadWellsTable();
            await loadWells(); // Refresh dashboard stats
        } else {
            const errorData = await response.json();
            showAlert(`Error deleting well: ${errorData.message || 'Unknown error'}`, 'danger');
        }
    } catch (error) {
        console.error('Error deleting well:', error);
        showAlert('Network error while deleting well', 'danger');
    }
}

// Delete task from schedule and re-optimize remaining wells
async function deleteTaskFromSchedule(taskId, taskName, assignmentId) {
    if (!confirm(`Are you sure you want to remove "${taskName}" from the schedule?\n\nThis will re-optimize the remaining wells in the schedule.`)) {
        return;
    }
    
    if (!currentSchedule || !currentSchedule.id) {
        showAlert('No active schedule found', 'danger');
        return;
    }
    
    if (!assignmentId) {
        showAlert('Assignment ID not found', 'danger');
        return;
    }
    
    try {
        showAlert('Removing task and re-optimizing schedule...', 'info');
        
        console.log('Delete operation details:');
        console.log('- Task ID:', taskId);
        console.log('- Task Name:', taskName);
        console.log('- Assignment ID:', assignmentId);
        console.log('- Schedule ID:', currentSchedule.id);
        
        const deleteUrl = `${ENDPOINTS.schedules}${currentSchedule.id}/delete_assignment/`;
        console.log('- Delete URL construction:');
        console.log('  - ENDPOINTS.schedules:', ENDPOINTS.schedules);
        console.log('  - currentSchedule.id:', currentSchedule.id);
        console.log('  - Final URL:', deleteUrl);
        
        // Validate the URL format
        const expectedUrlPattern = /^\/api\/schedules\/[a-f0-9\-]+\/delete_assignment\/$/;
        if (!expectedUrlPattern.test(deleteUrl)) {
            console.error('Invalid URL format detected:', deleteUrl);
            showAlert('Invalid URL format for delete operation', 'danger');
            return;
        }
        
        const requestBody = {
            task_id: assignmentId  // Using assignment_id as task_id for the assignment deletion
        };
        console.log('- Request body:', requestBody);
        
        const response = await fetch(deleteUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('idrs_csrftoken')
            },
            body: JSON.stringify(requestBody)
        });
        
        console.log('Response status:', response.status);
        console.log('Response headers:', response.headers);
        
        if (response.ok) {
            const result = await response.json();
            console.log('Delete successful:', result);
            
            // Show success message
            showAlert(`Task "${taskName}" removed successfully! Schedule re-optimized.`, 'success');
            
            // Update the Gantt chart with the new optimized schedule
            if (result.schedule) {
                updateGanttChart(result.schedule);
            }
        } else {
            const errorText = await response.text();
            console.error('Delete failed - Status:', response.status);
            console.error('Delete failed - Response:', errorText);
            
            let errorData;
            try {
                errorData = JSON.parse(errorText);
            } catch (e) {
                errorData = { error: errorText };
            }
            
            showAlert(`Error removing task: ${errorData.error || 'Unknown error'}`, 'danger');
        }
    } catch (error) {
        console.error('Network error during delete operation:', error);
        showAlert('Network error while removing task', 'danger');
    }
}

// Remove all rigs
async function removeAllRigs() {
    if (!confirm('⚠️ Are you sure you want to remove ALL rigs?\n\nThis will soft-delete all rig data.')) {
        return;
    }
    
    try {
        // Check CSRF token availability
        const csrfToken = getCookie('idrs_csrftoken');
        console.log('CSRF Token:', csrfToken ? 'Present' : 'MISSING!', csrfToken ? `(${csrfToken.substring(0, 10)}...)` : '');
        
        if (!csrfToken) {
            alert('CSRF token not found. Please refresh the page and try again.');
            return;
        }
        
        console.log('Fetching all rigs...');
        // Get all rigs first with cache-busting
        const response = await fetch(`${ENDPOINTS.rigs}?_=${Date.now()}`, {
            credentials: 'same-origin'
        });
        
        if (!response.ok) {
            throw new Error(`Failed to fetch rigs: ${response.status} ${response.statusText}`);
        }
        
        const data = await response.json();
        const rigs = data.results || data;
        
        console.log(`Found ${rigs.length} rigs to delete`);
        
        if (rigs.length === 0) {
            alert('No rigs to remove.');
            return;
        }
        
        // Show loading message
        document.getElementById('rigs-table-body').innerHTML = 
            '<tr><td colspan="5" class="text-center text-info">Removing all rigs...</td></tr>';
        
        // Delete each rig with proper error handling
        let successCount = 0;
        let failCount = 0;
        
        for (const rig of rigs) {
            try {
                console.log(`Deleting rig: ${rig.name} (${rig.id})`);
                const deleteResponse = await fetch(`${ENDPOINTS.rigs}${rig.id}/`, { 
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': csrfToken
                    },
                    credentials: 'same-origin'
                });
                
                if (!deleteResponse.ok) {
                    const errorText = await deleteResponse.text();
                    console.error(`Failed to delete rig ${rig.name}:`, deleteResponse.status, errorText);
                    failCount++;
                } else {
                    console.log(`Successfully deleted: ${rig.name}`);
                    successCount++;
                }
            } catch (error) {
                console.error(`Error deleting rig ${rig.name}:`, error);
                failCount++;
            }
        }
        
        console.log(`Delete completed: ${successCount} succeeded, ${failCount} failed`);
        
        // Reload the table
        await loadRigsTable();
        await loadRigs(); // Refresh dashboard stats
        
        if (failCount > 0) {
            alert(`Partial success: ${successCount} rigs deleted, ${failCount} failed.\n\nCheck console for details.`);
        } else {
            alert(`Successfully removed ${successCount} rigs.`);
        }
        
    } catch (error) {
        console.error('Error removing all rigs:', error);
        alert('Error removing rigs. Please try again.');
        await loadRigsTable(); // Reload table to show current state
    }
}

// Remove all wells
async function removeAllWells() {
    if (!confirm('⚠️ Are you sure you want to remove ALL wells?\n\nThis will soft-delete all well data.')) {
        return;
    }
    
    try {
        // Check CSRF token availability
        const csrfToken = getCookie('idrs_csrftoken');
        console.log('CSRF Token:', csrfToken ? 'Present' : 'MISSING!', csrfToken ? `(${csrfToken.substring(0, 10)}...)` : '');
        
        if (!csrfToken) {
            alert('CSRF token not found. Please refresh the page and try again.');
            return;
        }
        
        console.log('Fetching all wells...');
        // Get all wells first with cache-busting
        const response = await fetch(`${ENDPOINTS.wells}?_=${Date.now()}`, {
            credentials: 'same-origin'
        });
        
        if (!response.ok) {
            throw new Error(`Failed to fetch wells: ${response.status} ${response.statusText}`);
        }
        
        const data = await response.json();
        const wells = data.results || data;
        
        console.log(`Found ${wells.length} wells to delete`);
        
        if (wells.length === 0) {
            alert('No wells to remove.');
            return;
        }
        
        // Show loading message
        document.getElementById('wells-table-body').innerHTML = 
            '<tr><td colspan="6" class="text-center text-info">Removing all wells...</td></tr>';
        
        // Delete each well with proper error handling
        let successCount = 0;
        let failCount = 0;
        
        for (const well of wells) {
            try {
                console.log(`Deleting well: ${well.name} (${well.id})`);
                const deleteResponse = await fetch(`${ENDPOINTS.wells}${well.id}/`, { 
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': csrfToken
                    },
                    credentials: 'same-origin'
                });
                
                if (!deleteResponse.ok) {
                    const errorText = await deleteResponse.text();
                    console.error(`Failed to delete well ${well.name}:`, deleteResponse.status, errorText);
                    failCount++;
                } else {
                    console.log(`Successfully deleted: ${well.name}`);
                    successCount++;
                }
            } catch (error) {
                console.error(`Error deleting well ${well.name}:`, error);
                failCount++;
            }
        }
        
        console.log(`Delete completed: ${successCount} succeeded, ${failCount} failed`);
        
        // Reload the table
        await loadWellsTable();
        await loadWells(); // Refresh dashboard stats
        
        if (failCount > 0) {
            alert(`Partial success: ${successCount} wells deleted, ${failCount} failed.\n\nCheck console for details.`);
        } else {
            alert(`Successfully removed ${successCount} wells.`);
        }
        
    } catch (error) {
        console.error('Error removing all wells:', error);
        alert('Error removing wells. Please try again.');
        await loadWellsTable(); // Reload table to show current state
    }
}

// Show delete options for rigs - Bootstrap modal
function showDeleteRigsOptions() {
    const modal = document.getElementById('deleteConfirmModal');
    if (!modal) {
        // Fallback if modal not in DOM (e.g. different page)
        const choice = prompt('DELETE ALL RIGS\n\nType "soft" (recoverable) or "hard" (permanent):');
        if (!choice) return;
        const n = choice.trim().toLowerCase();
        if (n === 'hard') { if (confirm('PERMANENT delete of ALL rigs. Cannot be undone. Continue?')) hardDeleteAllRigs(); }
        else if (n === 'soft') { softDeleteAllRigs(); }
        else { alert('Invalid choice.'); }
        return;
    }
    
    document.getElementById('deleteConfirmModalTitle').innerHTML = '<i class="bi bi-trash me-2"></i>Delete All Rigs';
    document.getElementById('deleteConfirmModalText').textContent = 'Choose how to delete all rigs:';
    
    const softBtn = document.getElementById('deleteConfirmSoftBtn');
    const hardBtn = document.getElementById('deleteConfirmHardBtn');
    
    // Clone to remove old listeners
    const newSoft = softBtn.cloneNode(true);
    const newHard = hardBtn.cloneNode(true);
    softBtn.parentNode.replaceChild(newSoft, softBtn);
    hardBtn.parentNode.replaceChild(newHard, hardBtn);
    
    const bsModal = new bootstrap.Modal(modal);
    
    newSoft.addEventListener('click', function() {
        bsModal.hide();
        softDeleteAllRigs();
    });
    
    newHard.addEventListener('click', function() {
        bsModal.hide();
        if (confirm('FINAL CONFIRMATION: This will PERMANENTLY delete ALL rigs and all related schedules, assignments, and execution data.\n\nThis CANNOT be undone. Continue?')) {
            hardDeleteAllRigs();
        }
    });
    
    bsModal.show();
}

// Show delete options for wells - Bootstrap modal
function showDeleteWellsOptions() {
    const modal = document.getElementById('deleteConfirmModal');
    if (!modal) {
        const choice = prompt('DELETE ALL WELLS\n\nType "soft" (recoverable) or "hard" (permanent):');
        if (!choice) return;
        const n = choice.trim().toLowerCase();
        if (n === 'hard') { if (confirm('PERMANENT delete of ALL wells. Cannot be undone. Continue?')) hardDeleteAllWells(); }
        else if (n === 'soft') { softDeleteAllWells(); }
        else { alert('Invalid choice.'); }
        return;
    }
    
    document.getElementById('deleteConfirmModalTitle').innerHTML = '<i class="bi bi-trash me-2"></i>Delete All Wells';
    document.getElementById('deleteConfirmModalText').textContent = 'Choose how to delete all wells:';
    
    const softBtn = document.getElementById('deleteConfirmSoftBtn');
    const hardBtn = document.getElementById('deleteConfirmHardBtn');
    
    const newSoft = softBtn.cloneNode(true);
    const newHard = hardBtn.cloneNode(true);
    softBtn.parentNode.replaceChild(newSoft, softBtn);
    hardBtn.parentNode.replaceChild(newHard, hardBtn);
    
    const bsModal = new bootstrap.Modal(modal);
    
    newSoft.addEventListener('click', function() {
        bsModal.hide();
        softDeleteAllWells();
    });
    
    newHard.addEventListener('click', function() {
        bsModal.hide();
        if (confirm('FINAL CONFIRMATION: This will PERMANENTLY delete ALL wells and all related schedules, assignments, and execution data.\n\nThis CANNOT be undone. Continue?')) {
            hardDeleteAllWells();
        }
    });
    
    bsModal.show();
}

// Hard delete all rigs (permanent deletion with auto-cascade)
async function hardDeleteAllRigs() {
    try {
        const csrfToken = getCookie('idrs_csrftoken');
        if (!csrfToken) {
            alert('CSRF token not found. Please refresh the page and try again.');
            return;
        }
        
        // Get all rigs (including soft-deleted)
        const response = await fetch(`${ENDPOINTS.rigs}?include_deleted=true&_=${Date.now()}`, {
            credentials: 'same-origin'
        });
        
        if (!response.ok) {
            throw new Error(`Failed to fetch rigs: ${response.status}`);
        }
        
        const data = await response.json();
        const rigs = data.results || data;
        
        if (rigs.length === 0) {
            alert('No rigs to delete.');
            return;
        }
        
        // Extract IDs
        const rigIds = rigs.map(r => r.id);
        
        // Delete with auto-cascade (server handles all related records)
        const deleteResponse = await fetch(`${ENDPOINTS.rigs}bulk_hard_delete/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            credentials: 'same-origin',
            body: JSON.stringify({ rig_ids: rigIds })
        });
        
        const result = await deleteResponse.json();
        
        if (deleteResponse.ok) {
            let msg = `Successfully deleted ${result.deleted_count} rig(s)`;
            if (result.deleted_schedules > 0 || result.deleted_assignments > 0) {
                msg += `\n• ${result.deleted_schedules} schedule(s)\n• ${result.deleted_assignments} assignment(s)`;
            }
            alert(msg);
            await loadRigsTable();
            await loadRigs();
        } else {
            alert(`Error: ${result.error || result.message || 'Failed to delete rigs'}`);
        }
        
    } catch (error) {
        console.error('Error hard deleting rigs:', error);
        alert('Error permanently deleting rigs. Please try again.');
    }
}

// Soft delete all rigs (recoverable, uses bulk endpoint)
async function softDeleteAllRigs() {
    try {
        const csrfToken = getCookie('idrs_csrftoken');
        if (!csrfToken) {
            alert('CSRF token not found. Please refresh the page and try again.');
            return;
        }
        
        // Get all active rigs
        const response = await fetch(`${ENDPOINTS.rigs}?_=${Date.now()}`, {
            credentials: 'same-origin'
        });
        
        if (!response.ok) {
            throw new Error(`Failed to fetch rigs: ${response.status}`);
        }
        
        const data = await response.json();
        const rigs = data.results || data;
        
        if (rigs.length === 0) {
            alert('No rigs to delete.');
            return;
        }
        
        const rigIds = rigs.map(r => r.id);
        
        const deleteResponse = await fetch(`${ENDPOINTS.rigs}bulk_soft_delete/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            credentials: 'same-origin',
            body: JSON.stringify({ rig_ids: rigIds })
        });
        
        const result = await deleteResponse.json();
        
        if (deleteResponse.ok) {
            alert(`Successfully soft-deleted ${result.deleted_count} rig(s). They can be recovered later.`);
            await loadRigsTable();
            await loadRigs();
        } else {
            alert(`Error: ${result.error || result.message || 'Failed to soft-delete rigs'}`);
        }
        
    } catch (error) {
        console.error('Error soft deleting rigs:', error);
        alert('Error soft-deleting rigs. Please try again.');
    }
}

// Hard delete all wells (permanent deletion with auto-cascade)
async function hardDeleteAllWells() {
    try {
        const csrfToken = getCookie('idrs_csrftoken');
        if (!csrfToken) {
            alert('CSRF token not found. Please refresh the page and try again.');
            return;
        }
        
        // Get all wells (including soft-deleted)
        const response = await fetch(`${ENDPOINTS.wells}?include_deleted=true&_=${Date.now()}`, {
            credentials: 'same-origin'
        });
        
        if (!response.ok) {
            throw new Error(`Failed to fetch wells: ${response.status}`);
        }
        
        const data = await response.json();
        const wells = data.results || data;
        
        if (wells.length === 0) {
            alert('No wells to delete.');
            return;
        }
        
        // Extract IDs
        const wellIds = wells.map(w => w.id);
        
        // Delete with auto-cascade (server handles all related records)
        const deleteResponse = await fetch(`${ENDPOINTS.wells}bulk_hard_delete/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            credentials: 'same-origin',
            body: JSON.stringify({ well_ids: wellIds })
        });
        
        const result = await deleteResponse.json();
        
        if (deleteResponse.ok) {
            let msg = `Successfully deleted ${result.deleted_count} well(s)`;
            if (result.deleted_schedules > 0 || result.deleted_assignments > 0) {
                msg += `\n• ${result.deleted_schedules} schedule(s)\n• ${result.deleted_assignments} assignment(s)`;
            }
            alert(msg);
            await loadWellsTable();
            await loadWells();
        } else {
            alert(`Error: ${result.error || result.message || 'Failed to delete wells'}`);
        }
        
    } catch (error) {
        console.error('Error hard deleting wells:', error);
        alert('Error permanently deleting wells. Please try again.');
    }
}

// Soft delete all wells (recoverable, uses bulk endpoint)
async function softDeleteAllWells() {
    try {
        const csrfToken = getCookie('idrs_csrftoken');
        if (!csrfToken) {
            alert('CSRF token not found. Please refresh the page and try again.');
            return;
        }
        
        // Get all active wells
        const response = await fetch(`${ENDPOINTS.wells}?_=${Date.now()}`, {
            credentials: 'same-origin'
        });
        
        if (!response.ok) {
            throw new Error(`Failed to fetch wells: ${response.status}`);
        }
        
        const data = await response.json();
        const wells = data.results || data;
        
        if (wells.length === 0) {
            alert('No wells to delete.');
            return;
        }
        
        const wellIds = wells.map(w => w.id);
        
        const deleteResponse = await fetch(`${ENDPOINTS.wells}bulk_soft_delete/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            credentials: 'same-origin',
            body: JSON.stringify({ well_ids: wellIds })
        });
        
        const result = await deleteResponse.json();
        
        if (deleteResponse.ok) {
            alert(`Successfully soft-deleted ${result.deleted_count} well(s). They can be recovered later.`);
            await loadWellsTable();
            await loadWells();
        } else {
            alert(`Error: ${result.error || result.message || 'Failed to soft-delete wells'}`);
        }
        
    } catch (error) {
        console.error('Error soft deleting wells:', error);
        alert('Error soft-deleting wells. Please try again.');
    }
}

// Edit rig - fetch data and open edit modal
async function editRig(rigId) {
    if (!rigId) {
        console.error('No rig ID provided to editRig');
        return;
    }

    try {
        // Show the modal
        const modal = new bootstrap.Modal(document.getElementById('editRigModal'));
        modal.show();

        // Fetch rig details from API
        const response = await fetch(`${ENDPOINTS.rigs}${rigId}/`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const rig = await response.json();
        
        // Populate the edit form
        populateRigEditForm(rig);

    } catch (error) {
        console.error('Error fetching rig for edit:', error);
        showAlert(`Error loading rig data: ${error.message}`, 'error');
    }
}

// Edit well - fetch data and open edit modal
async function editWell(wellId) {
    if (!wellId) {
        console.error('No well ID provided to editWell');
        return;
    }

    try {
        // Show the modal
        const modal = new bootstrap.Modal(document.getElementById('editWellModal'));
        modal.show();

        // Fetch well details from API
        const response = await fetch(`${ENDPOINTS.wells}${wellId}/`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const well = await response.json();
        
        // Populate the edit form
        populateWellEditForm(well);

    } catch (error) {
        console.error('Error fetching well for edit:', error);
        showAlert(`Error loading well data: ${error.message}`, 'error');
    }
}

// Download schedule as Excel
function downloadScheduleExcel() {
    const scheduleSelector = document.getElementById('schedule-selector');
    const selectedScheduleId = scheduleSelector.value;
    
    if (!selectedScheduleId) {
        alert('Please select a schedule first.');
        return;
    }
    
    const selectedOption = scheduleSelector.options[scheduleSelector.selectedIndex];
    const scheduleName = selectedOption.text;
    
    // Show loading message
    const downloadBtn = document.getElementById('download-excel-btn');
    const originalText = downloadBtn.innerHTML;
    downloadBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Downloading...';
    downloadBtn.disabled = true;
    
    // Create download link
    const downloadUrl = `/api/export/schedule/${selectedScheduleId}/excel/`;
    
    fetch(downloadUrl)
        .then(response => {
            if (response.ok) {
                return response.blob();
            }
            throw new Error('Download failed');
        })
        .then(blob => {
            // Create download link
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = `schedule_${sanitizeFileName(scheduleName)}_${new Date().toISOString().slice(0, 10)}.xlsx`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            // Show success message
            showAlert('Schedule "' + scheduleName + '" downloaded successfully as Excel file.', 'success');
        })
        .catch(error => {
            console.error('Download error:', error);
            showAlert('Failed to download schedule. Please try again.', 'danger');
        })
        .finally(() => {
            // Restore button
            downloadBtn.innerHTML = originalText;
            downloadBtn.disabled = false;
        });
}

// Download schedule as CSV
function downloadScheduleCSV() {
    const scheduleSelector = document.getElementById('schedule-selector');
    const selectedScheduleId = scheduleSelector.value;
    
    if (!selectedScheduleId) {
        alert('Please select a schedule first.');
        return;
    }
    
    const selectedOption = scheduleSelector.options[scheduleSelector.selectedIndex];
    const scheduleName = selectedOption.text;
    
    // Show loading message
    const downloadBtn = document.getElementById('download-csv-btn');
    const originalText = downloadBtn.innerHTML;
    downloadBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Downloading...';
    downloadBtn.disabled = true;
    
    // Create download link
    const downloadUrl = `/api/export/schedule/${selectedScheduleId}/`;
    
    fetch(downloadUrl)
        .then(response => {
            if (response.ok) {
                return response.blob();
            }
            throw new Error('Download failed');
        })
        .then(blob => {
            // Create download link
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = `schedule_${sanitizeFileName(scheduleName)}_${new Date().toISOString().slice(0, 10)}.csv`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            // Show success message
            showAlert('Schedule "' + scheduleName + '" downloaded successfully as CSV file.', 'success');
        })
        .catch(error => {
            console.error('Download error:', error);
            showAlert('Failed to download schedule. Please try again.', 'danger');
        })
        .finally(() => {
            // Restore button
            downloadBtn.innerHTML = originalText;
            downloadBtn.disabled = false;
        });
}

// Schedules Management Functions
// Global variable to track current location filter for schedules
let currentSchedulesLocationFilter = '';

async function loadSchedulesList(locationFilter = null) {
    console.log('loadSchedulesList called with location:', locationFilter);
    const loadingDiv = document.getElementById('schedules-loading');
    const listDiv = document.getElementById('schedules-list');
    const emptyDiv = document.getElementById('schedules-empty');
    const tableBody = document.getElementById('schedules-table-body');
    
    // Store the location filter for use in refresh
    if (locationFilter !== null) {
        currentSchedulesLocationFilter = locationFilter;
    }
    
    console.log('Elements found:', {
        loadingDiv: !!loadingDiv,
        listDiv: !!listDiv,
        emptyDiv: !!emptyDiv,
        tableBody: !!tableBody
    });
    
    if (loadingDiv) loadingDiv.style.display = 'block';
    if (listDiv) listDiv.style.display = 'none';
    if (emptyDiv) emptyDiv.style.display = 'none';
    
    try {
        // Build URL with optional location filter
        let url = ENDPOINTS.schedules;
        if (currentSchedulesLocationFilter) {
            url += `?asset_id=${encodeURIComponent(currentSchedulesLocationFilter)}`;
        }
        console.log('Fetching schedules from:', url);
        const response = await apiRequest(url);
        console.log('API response received:', response);
        
        // Handle paginated response
        const schedules = response.results || response;
        console.log('Schedules array:', schedules);
        
        if (loadingDiv) loadingDiv.style.display = 'none';
        
        if (schedules && schedules.length > 0) {
            console.log('Displaying schedules, count:', schedules.length);
            if (listDiv) listDiv.style.display = 'block';
            if (tableBody) {
                // Organize schedules into hierarchy first
                const hierarchicalSchedules = organizeSchedulesHierarchy(schedules);
                console.log('Hierarchical schedules:', hierarchicalSchedules);
                
                // Group completed schedules by hash for all users
                // (admin sees raw hash in group row; non-admin sees only short fingerprint)
                const tableHtml = renderHashGroupedSchedules(hierarchicalSchedules);
                
                tableBody.innerHTML = tableHtml;
                console.log('Table HTML updated');
                
                // Add event listeners for the buttons
                setupScheduleButtonEvents();
                
                // Setup hash group toggle listeners
                setupHashGroupToggleEvents();
                
                // Update comparison checkboxes based on localStorage
                updateComparisonCheckboxes();
                
                // Show compare button if schedules exist
                const toggleCompareBtn = document.getElementById('toggle-compare-btn');
                if (toggleCompareBtn && schedules.length > 1) {
                    toggleCompareBtn.style.display = 'inline-block';
                }
                
            }
        } else {
            console.log('No schedules found, showing empty state');
            if (emptyDiv) emptyDiv.style.display = 'block';
        }
    } catch (error) {
        console.error('Error loading schedules:', error);
        if (loadingDiv) loadingDiv.style.display = 'none';
        if (emptyDiv) {
            emptyDiv.style.display = 'block';
            emptyDiv.innerHTML = `
                <i class="bi bi-exclamation-triangle fs-1 text-danger"></i>
                <p class="mt-2 text-danger">Error loading schedules</p>
                <p class="small">${error.message}</p>
            `;
        }
    }
}

function renderHashGroupedSchedules(hierarchicalSchedules) {
    // Separate non-completed from completed schedules
    const nonCompleted = [];
    const completedByHash = new Map(); // hash -> [scheduleData, ...]
    const completedNoHash = [];
    
    for (const scheduleData of hierarchicalSchedules) {
        const s = scheduleData.schedule;
        const status = (s.status || 'PENDING').toUpperCase();
        if (status !== 'COMPLETED') {
            nonCompleted.push(scheduleData);
        } else if (s.schedule_hash) {
            if (!completedByHash.has(s.schedule_hash)) {
                completedByHash.set(s.schedule_hash, []);
            }
            completedByHash.get(s.schedule_hash).push(scheduleData);
        } else {
            completedNoHash.push(scheduleData);
        }
    }
    
    let html = '';
    
    // Render non-completed schedules first (running, pending, failed)
    for (const sd of nonCompleted) {
        html += renderScheduleRow(sd.schedule, sd.level);
    }
    
    // Render hash-grouped completed schedules
    for (const [hash, group] of completedByHash) {
        if (group.length === 1) {
            // Single schedule in group — render normally
            html += renderScheduleRow(group[0].schedule, group[0].level);
        } else {
            // Multiple schedules with same hash — render consolidated group row
            html += renderHashGroupRow(hash, group);
            // Render individual schedules as hidden children
            for (const sd of group) {
                html += renderScheduleRow(sd.schedule, sd.level, hash);
            }
        }
    }
    
    // Render completed without hash
    for (const sd of completedNoHash) {
        html += renderScheduleRow(sd.schedule, sd.level);
    }
    
    return html;
}

function renderHashGroupRow(hash, group) {
    // Consolidate metadata from schedules in this group
    const schedules = group.map(g => g.schedule);
    const wellCounts = schedules.map(s => s.assignments_count || (s.assignments ? s.assignments.length : 0));
    const avgWells = Math.round(wellCounts.reduce((a, b) => a + b, 0) / wellCounts.length);
    const locations = [...new Set(schedules.map(s => s.location_name || s.location_code || '—'))];
    const fys = [...new Set(schedules.map(s => s.financial_year || '—'))];
    const isAdmin = window.USER_IS_ADMIN;
    const shortHash = hash.substring(0, 12);
    
    return `
        <tr class="hash-group-row" data-hash-group="${escapeHtml(hash)}" style="cursor:pointer;">
            <td class="compare-checkbox-cell" style="display: none;"></td>
            <td>
                <div class="d-flex align-items-center">
                    <i class="bi bi-chevron-right hash-group-chevron me-2" style="transition:transform 0.2s; color:#10b981;"></i>
                    <div>
                        <span class="fw-semibold" style="color:#059669;">
                            <i class="bi bi-copy me-1"></i>${schedules.length} Identical Runs
                        </span>
                        ${isAdmin ? `<br><span class="font-monospace text-muted" style="font-size:0.7rem;">#${escapeHtml(shortHash)}</span>` : ''}
                    </div>
                </div>
            </td>
            <td><span class="text-muted">${escapeHtml(fys.join(', '))}</span></td>
            <td><span class="text-muted">${escapeHtml(locations.join(', '))}</span></td>
            <td></td>
            <td><span class="badge bg-success">Completed</span></td>
            <td>
                <span class="fw-semibold">${avgWells} wells</span>
                <span class="text-muted ms-1">· same result across all runs</span>
            </td>
            <td></td>
        </tr>
    `;
}

function setupHashGroupToggleEvents() {
    document.querySelectorAll('.hash-group-row').forEach(row => {
        row.addEventListener('click', function() {
            const hash = this.getAttribute('data-hash-group');
            const childRows = document.querySelectorAll(`.hash-child-row[data-parent-hash="${hash}"]`);
            const chevron = this.querySelector('.hash-group-chevron');
            const isExpanded = this.classList.toggle('hash-expanded');
            
            childRows.forEach(childRow => {
                childRow.style.display = isExpanded ? '' : 'none';
            });
            
            if (chevron) {
                chevron.style.transform = isExpanded ? 'rotate(90deg)' : 'rotate(0deg)';
            }
        });
    });
}

function organizeSchedulesHierarchy(schedules) {
    // Create a map of schedule ID to schedule
    const scheduleMap = new Map();
    schedules.forEach(schedule => {
        scheduleMap.set(schedule.id, schedule);
    });
    
    // Find root schedules (those without parents or whose parents don't exist)
    const rootSchedules = schedules.filter(schedule => 
        !schedule.parent_schedule_id || !scheduleMap.has(schedule.parent_schedule_id)
    );
    
    // Recursively build hierarchy
    const result = [];
    
    function addScheduleWithChildren(schedule, level = 0) {
        result.push({ schedule, level });
        
        // Find children of this schedule
        const children = schedules.filter(s => s.parent_schedule_id === schedule.id);
        
        // Sort children by created_at or version_number
        children.sort((a, b) => {
            if (a.version_number && b.version_number) {
                return a.version_number - b.version_number;
            }
            return new Date(a.created_at) - new Date(b.created_at);
        });
        
        children.forEach(child => addScheduleWithChildren(child, level + 1));
    }
    
    // Sort root schedules by created_at (newest first)
    rootSchedules.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    
    rootSchedules.forEach(rootSchedule => addScheduleWithChildren(rootSchedule));
    
    return result;
}

function renderScheduleRow(schedule, level, parentHash = null) {
    const indent = level > 0 ? '<span style="display:inline-block;width:' + (level * 20) + 'px"></span>' : '';
    const treeSymbol = level > 0 ? '<span class="text-muted me-1">└</span>' : '';
    const creatorName = schedule.created_by_username || '—';
    const fy = schedule.financial_year || '—';
    const location = schedule.location_name || schedule.location_code || '—';
    const isAdmin = window.USER_IS_ADMIN;
    let scheduleStatus = (schedule.status || 'PENDING').toUpperCase();
    const isStale = schedule.is_stale;
    const isCompleted = scheduleStatus === 'COMPLETED';
    
    // --- Status badge (compact, single line) ---
    let statusBadge = '';
    if (scheduleStatus === 'COMPLETED') {
        statusBadge = `<span class="badge bg-success">Completed</span>`;
    } else if (scheduleStatus === 'RUNNING') {
        if (isStale) {
            statusBadge = `<span class="badge text-bg-secondary"><i class="bi bi-exclamation-triangle me-1"></i>Stale</span>`;
        } else {
            const elapsed = Math.round((Date.now() - new Date(schedule.created_at).getTime()) / 1000);
            const elapsedMin = Math.floor(elapsed / 60);
            const elapsedSec = elapsed % 60;
            statusBadge = `<span class="badge text-bg-warning"><i class="bi bi-hourglass-split me-1"></i>Running ${elapsedMin}m ${elapsedSec}s</span>`;
        }
    } else if (scheduleStatus === 'FAILED') {
        statusBadge = `<span class="badge bg-danger">Failed</span>`;
    } else if (scheduleStatus === 'PENDING') {
        statusBadge = `<span class="badge bg-secondary"><i class="bi bi-clock me-1"></i>Queued</span>`;
    } else if (scheduleStatus === 'CANCELLED') {
        statusBadge = `<span class="badge bg-dark">Cancelled</span>`;
    } else {
        statusBadge = `<span class="badge bg-secondary">${escapeHtml(scheduleStatus)}</span>`;
    }
    
    // --- Summary content ---
    let summaryHtml = '';
    if (isCompleted) {
        const wellCount = schedule.assignments_count || (schedule.assignments ? schedule.assignments.length : 0);
        const cost = schedule.total_drilling_cost ? `₹${formatCurrency(schedule.total_drilling_cost)}` : '—';
        const solveTime = schedule.solve_time_seconds ? `${parseFloat(schedule.solve_time_seconds).toFixed(1)}s` : '';
        
        // Optimality Gap (admin only)
        let gapHtml = '';
        if (isAdmin && schedule.optimality_gap_percent != null) {
            const gapPct = schedule.optimality_gap_percent;
            if (gapPct === 0) {
                gapHtml = `<span class="text-success" style="font-size:0.78rem;">Optimality Gap: 0.00% ✓</span>`;
            } else if (gapPct < 1) {
                gapHtml = `<span class="text-success" style="font-size:0.78rem;">Optimality Gap: ${gapPct.toFixed(4)}%</span>`;
            } else if (gapPct < 5) {
                gapHtml = `<span class="text-warning" style="font-size:0.78rem;">Optimality Gap: ${gapPct.toFixed(4)}%</span>`;
            } else if (schedule.unassigned_wells_count === 0) {
                // High gap but all wells assigned — solution is implementable
                gapHtml = `<span class="text-info" style="font-size:0.78rem;">Optimality Gap: ${gapPct.toFixed(2)}% <i class="bi bi-info-circle" title="All wells assigned. High gap = solver could not prove near-optimality within time limit, not that the solution is poor."></i></span>`;
            } else {
                gapHtml = `<span class="text-danger" style="font-size:0.78rem;">Optimality Gap: ${gapPct.toFixed(2)}%</span>`;
            }
        } else if (schedule.solver_status) {
            gapHtml = `<span class="text-muted" style="font-size:0.78rem;">${escapeHtml(schedule.solver_status)}</span>`;
        }
        
        summaryHtml = `<span class="fw-semibold">${wellCount} wells</span> at <span class="fw-semibold">${cost}</span>`;
        if (solveTime) summaryHtml += `<span class="text-muted ms-2" style="font-size:0.78rem;"><i class="bi bi-clock-history"></i> ${solveTime}</span>`;
        if (gapHtml) summaryHtml += `<br>${gapHtml}`;
        // Hash (admin only)
        if (isAdmin && schedule.schedule_hash) {
            summaryHtml += `<br><span class="font-monospace text-muted" style="font-size:0.68rem;" title="Schedule fingerprint">#${escapeHtml(schedule.schedule_hash)}</span>`;
        }
    } else if (scheduleStatus === 'RUNNING' || scheduleStatus === 'PENDING') {
        const metaParts = [];
        if (schedule.input_wells_count) metaParts.push(`${schedule.input_wells_count} wells`);
        if (schedule.input_rigs_count) metaParts.push(`${schedule.input_rigs_count} rigs`);
        if (schedule.time_limit_seconds) {
            const mins = Math.floor(schedule.time_limit_seconds / 60);
            const secs = schedule.time_limit_seconds % 60;
            metaParts.push(mins > 0 ? (secs > 0 ? `${mins}m ${secs}s limit` : `${mins} mins limit`) : `${secs}s limit`);
        }
        if (isStale) {
            summaryHtml = `<span class="text-muted"><i class="bi bi-exclamation-circle me-1"></i>Process may have been interrupted</span>`;
            if (metaParts.length) summaryHtml += `<br><span class="text-muted" style="font-size:0.78rem;">${metaParts.join(' · ')}</span>`;
        } else {
            summaryHtml = `<span class="text-warning"><i class="bi bi-gear-wide-connected me-1"></i>Optimization in progress...</span>`;
            if (metaParts.length) summaryHtml += `<br><span class="text-muted" style="font-size:0.78rem;">${metaParts.join(' · ')}</span>`;
        }
    } else if (scheduleStatus === 'FAILED') {
        summaryHtml = `<span class="text-danger"><i class="bi bi-x-circle me-1"></i>Optimization failed</span>`;
        if (schedule.solver_status) summaryHtml += `<br><span class="text-muted" style="font-size:0.78rem;">${escapeHtml(schedule.solver_status)}</span>`;
    } else {
        summaryHtml = '<span class="text-muted">—</span>';
    }
    
    // --- Date display ---
    let dateStr = '';
    if (isCompleted && schedule.completed_at) {
        dateStr = formatCompactDateTime(schedule.completed_at);
    } else {
        dateStr = formatCompactDateTime(schedule.created_at);
    }
    
    // --- Row class ---
    const isHashChild = !!parentHash;
    const trClass = isHashChild 
        ? `hash-child-row schedule-level-${level}`
        : `schedule-level-${level}`;
    const trHashAttr = isHashChild 
        ? `data-parent-hash="${escapeHtml(parentHash)}" style="display:none;"` 
        : '';
    
    return `
        <tr class="${trClass}" ${trHashAttr}>
            <td class="compare-checkbox-cell" style="display: none;">
                <input class="form-check-input schedule-compare-checkbox" type="checkbox" 
                       value="${schedule.id}" id="schedule-${schedule.id}"
                       onchange="toggleScheduleForComparison('${schedule.id}', '${escapeJavaScript(schedule.name)}', null, false)">
            </td>
            <td>
                ${indent}${treeSymbol}<span class="fw-medium">${escapeHtml(schedule.name)}</span>
            </td>
            <td><span class="text-muted">${escapeHtml(fy)}</span></td>
            <td><span class="text-muted">${escapeHtml(location)}</span></td>
            <td><span class="text-muted" style="font-size:0.82rem;"><i class="bi bi-person me-1"></i>${escapeHtml(creatorName)}</span></td>
            <td>${statusBadge}<br><span class="text-muted" style="font-size:0.75rem;">${dateStr}</span></td>
            <td class="summary-cell">${summaryHtml}</td>
            <td>
                <div class="btn-group btn-group-sm" role="group">
                    ${isCompleted ? `
                    <button type="button" class="btn btn-outline-info view-schedule-details-btn" data-schedule-id="${schedule.id}" title="View Details">
                        <i class="bi bi-file-text"></i>
                    </button>
                    <button type="button" class="btn btn-outline-primary view-schedule-btn" data-schedule-id="${schedule.id}" title="Gantt Chart">
                        <i class="bi bi-bar-chart"></i>
                    </button>
                    <a href="/schedule-maps/?schedule_id=${schedule.id}" class="btn btn-outline-warning btn-sm" title="Maps" target="_blank">
                        <i class="bi bi-geo-alt"></i>
                    </a>
                    <a href="/api/export/schedule/${schedule.id}/excel/" class="btn btn-outline-success btn-sm" title="Excel" download>
                        <i class="bi bi-file-earmark-excel"></i>
                    </a>
                    ` : ''}
                    ${window.USER_IS_ADMIN ? `
                    <button type="button" class="btn btn-outline-secondary rename-schedule-btn" data-schedule-id="${schedule.id}" data-schedule-name="${escapeHtml(schedule.name)}" title="Rename">
                        <i class="bi bi-pencil-square"></i>
                    </button>
                    ` : ''}
                    <button type="button" class="btn btn-outline-danger delete-schedule-btn" data-schedule-id="${schedule.id}" data-schedule-name="${escapeHtml(schedule.name)}" title="Delete">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `;
}

function getStatusBadgeClass(status) {
    switch (status) {
        case 'COMPLETED': return 'bg-success';
        case 'RUNNING': return 'bg-warning';
        case 'FAILED': return 'bg-danger';
        default: return 'bg-secondary';
    }
}

function formatDateTime(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
}

function formatCompactDateTime(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    const day = date.getDate().toString().padStart(2, '0');
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const year = date.getFullYear();
    const hours = date.getHours();
    const minutes = date.getMinutes().toString().padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours % 12 || 12;
    
    return `${day}/${month}/${year} ${displayHours}:${minutes}${ampm}`;
}

function formatCurrency(amount) {
    if (!amount) return '0';
    const num = parseFloat(amount);
    if (num >= 10000000) { // 1 crore
        return (num / 10000000).toFixed(1) + ' Cr';
    } else if (num >= 100000) { // 1 lakh
        return (num / 100000).toFixed(1) + ' L';
    } else if (num >= 1000) { // 1 thousand
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toFixed(0);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeJavaScript(text) {
    return text.replace(/\\/g, '\\\\')
               .replace(/'/g, "\\'")
               .replace(/"/g, '\\"')
               .replace(/\n/g, '\\n')
               .replace(/\r/g, '\\r')
               .replace(/\t/g, '\\t');
}

function sanitizeFileName(text) {
    return text.replace(/[^a-zA-Z0-9\-_\s]/g, '_').replace(/\s+/g, '_');
}

function setupScheduleButtonEvents() {
    // Add event listeners for view details buttons
    document.querySelectorAll('.view-schedule-details-btn').forEach(button => {
        button.addEventListener('click', function() {
            const scheduleId = this.getAttribute('data-schedule-id');
            viewScheduleDetails(scheduleId);
        });
    });
    
    // Add event listeners for view Gantt buttons
    document.querySelectorAll('.view-schedule-btn').forEach(button => {
        button.addEventListener('click', function() {
            const scheduleId = this.getAttribute('data-schedule-id');
            viewScheduleInGantt(scheduleId);
        });
    });
    
    // Add event listeners for rename buttons (admin only)
    document.querySelectorAll('.rename-schedule-btn').forEach(button => {
        button.addEventListener('click', function() {
            const scheduleId = this.getAttribute('data-schedule-id');
            const scheduleName = this.getAttribute('data-schedule-name');
            openRenameModal(scheduleId, scheduleName);
        });
    });
    
    // Add event listeners for delete buttons
    document.querySelectorAll('.delete-schedule-btn').forEach(button => {
        button.addEventListener('click', function() {
            const scheduleId = this.getAttribute('data-schedule-id');
            const scheduleName = this.getAttribute('data-schedule-name');
            confirmDeleteSchedule(scheduleId, scheduleName);
        });
    });
}

function refreshSchedulesList() {
    // Use current location filter when refreshing
    loadSchedulesList(currentSchedulesLocationFilter);
}

function viewScheduleDetails(scheduleId) {
    window.location.href = `/schedule/${scheduleId}/`;
}

function viewLastScheduleDetails() {
    if (currentSchedule && currentSchedule.id) {
        viewScheduleDetails(currentSchedule.id);
    } else {
        showAlert('No schedule available to view details.', 'warning');
    }
}

function viewScheduleInGantt(scheduleId) {
    window.open(`/gantt/?schedule=${scheduleId}`, '_blank');
}

function confirmDeleteSchedule(scheduleId, scheduleName) {
    if (confirm('Are you sure you want to delete the schedule "' + scheduleName + '"?\n\nThis action cannot be undone.')) {
        deleteSchedule(scheduleId, scheduleName);
    }
}

async function deleteSchedule(scheduleId, scheduleName) {
    try {
        await apiRequest(`${ENDPOINTS.schedules}${scheduleId}/`, {
            method: 'DELETE'
        });
        
        showAlert('Schedule "' + scheduleName + '" deleted successfully.', 'success');
        loadSchedulesList(); // Refresh the list
        
    } catch (error) {
        console.error('Error deleting schedule:', error);
        showAlert('Failed to delete schedule "' + scheduleName + '": ' + error.message, 'danger');
    }
}

// Activity logging functions
function showActivityMessage(message, type = 'info') {
    const activityContainer = document.getElementById('scheduler-activity');
    if (!activityContainer) return;
    
    const timestamp = new Date().toLocaleTimeString();
    const alertClass = type === 'error' ? 'alert-danger' : type === 'success' ? 'alert-success' : 'alert-info';
    
    const messageHTML = `
        <div class="alert ${alertClass} alert-sm mb-2" role="alert">
            <small class="text-muted">${timestamp}</small><br>
            ${message}
        </div>
    `;
    
    // If it's the first message, replace the placeholder
    if (activityContainer.querySelector('.text-center.text-muted')) {
        activityContainer.innerHTML = '';
    }
    
    activityContainer.insertAdjacentHTML('beforeend', messageHTML);
    
    // Scroll to bottom
    activityContainer.scrollTop = activityContainer.scrollHeight;
}

// View schedule details functions
function viewLastScheduleDetails() {
    if (window.lastScheduleId) {
        window.open(`/schedule/${window.lastScheduleId}/`, '_blank');
    } else {
        showAlert('No recent schedule found', 'warning');
    }
}

function viewGanttChart() {
    if (window.lastScheduleId) {
        window.open(`/gantt/?schedule=${window.lastScheduleId}`, '_blank');
    } else {
        showAlert('No recent schedule found', 'warning');
    }
}

// Schedule comparison functionality
let isCompareMode = false;

function toggleCompareMode() {
    isCompareMode = !isCompareMode;
    
    const compareHeader = document.getElementById('compare-header');
    const compareCheckboxCells = document.querySelectorAll('.compare-checkbox-cell');
    const toggleBtn = document.getElementById('toggle-compare-btn');
    
    if (isCompareMode) {
        // Show compare mode
        if (compareHeader) compareHeader.style.display = 'table-cell';
        compareCheckboxCells.forEach(cell => cell.style.display = 'table-cell');
        
        if (toggleBtn) {
            toggleBtn.innerHTML = '<i class="bi bi-x-circle me-1"></i>Cancel Compare';
            toggleBtn.classList.remove('btn-outline-primary');
            toggleBtn.classList.add('btn-outline-danger');
        }
        
        // Update comparison controls
        updateComparisonControls();
    } else {
        // Hide compare mode
        if (compareHeader) compareHeader.style.display = 'none';
        compareCheckboxCells.forEach(cell => cell.style.display = 'none');
        
        if (toggleBtn) {
            toggleBtn.innerHTML = '<i class="bi bi-check-square me-1"></i>Compare Schedules';
            toggleBtn.classList.remove('btn-outline-danger');
            toggleBtn.classList.add('btn-outline-primary');
        }
        
        // Hide comparison controls
        const viewComparisonBtn = document.getElementById('view-comparison-btn');
        if (viewComparisonBtn) viewComparisonBtn.style.display = 'none';
        
        // Uncheck all checkboxes
        document.querySelectorAll('.schedule-compare-checkbox').forEach(checkbox => {
            checkbox.checked = false;
        });
        
        // Clear comparison data
        localStorage.removeItem('scheduleComparison');
    }
}

function selectAllSchedules(checked) {
    const checkboxes = document.querySelectorAll('.schedule-compare-checkbox');
    const totalCheckboxes = checkboxes.length;
    
    // If trying to check all but there are more than 3, show warning and don't proceed
    if (checked && totalCheckboxes > 3) {
        showAlert('Cannot select all - maximum 3 schedules can be compared at once', 'warning');
        return;
    }
    
    checkboxes.forEach(checkbox => {
        checkbox.checked = checked;
        const scheduleId = checkbox.value;
        const scheduleName = checkbox.closest('tr').querySelector('.schedule-name-cell strong, .schedule-name-cell span').textContent.trim();
        
        // Suppress individual alerts when doing bulk operations
        toggleScheduleForComparison(scheduleId, scheduleName, checked, true);
    });
    
    // Show single summary alert after bulk operation
    if (checked) {
        const count = Math.min(totalCheckboxes, 3);
        showAlert(`Added ${count} schedule${count > 1 ? 's' : ''} to comparison`, 'success');
    } else {
        showAlert('Cleared comparison selection', 'info');
    }
}

function toggleScheduleForComparison(scheduleId, scheduleName, forceAction = null, suppressAlerts = false) {
    let comparisonList = JSON.parse(localStorage.getItem('scheduleComparison') || '[]');
    
    console.log('toggleScheduleForComparison called:', {
        scheduleId: scheduleId,
        scheduleName: scheduleName,
        currentListLength: comparisonList.length,
        currentList: comparisonList,
        forceAction: forceAction,
        suppressAlerts: suppressAlerts
    });
    
    const existingIndex = comparisonList.findIndex(item => item.id === scheduleId);
    
    // Determine shouldAdd based on forceAction or checkbox state
    let shouldAdd;
    if (forceAction !== null) {
        shouldAdd = forceAction;
    } else {
        // Check the actual checkbox state to determine action
        const checkbox = document.getElementById(`schedule-${scheduleId}`);
        shouldAdd = checkbox ? checkbox.checked : existingIndex === -1;
    }
    
    console.log('Action determined:', { shouldAdd, existingIndex, itemAlreadyInList: existingIndex !== -1 });
    
    if (!shouldAdd && existingIndex !== -1) {
        // Remove from comparison
        comparisonList.splice(existingIndex, 1);
        console.log('Removed from comparison, new length:', comparisonList.length);
        if (forceAction === null && !suppressAlerts) {
            showAlert(`Removed "${scheduleName}" from comparison`, 'info');
        }
    } else if (shouldAdd) {
        // Check if already in list
        if (existingIndex !== -1) {
            console.log('Item already in list, skipping add');
            return; // Already in list, don't add again
        }
        
        // Add to comparison (limit to 3 schedules)
        if (comparisonList.length >= 3) {
            console.log('Limit reached, cannot add more');
            // Find the checkbox and uncheck it
            const checkbox = document.getElementById(`schedule-${scheduleId}`);
            if (checkbox) checkbox.checked = false;
            
            if (forceAction === null && !suppressAlerts) {
                showAlert('Maximum 3 schedules can be compared at once', 'warning');
            }
            return;
        }
        
        // Add to list
        comparisonList.push({
            id: scheduleId,
            name: scheduleName
        });
        console.log('Added to comparison, new length:', comparisonList.length);
        if (forceAction === null && !suppressAlerts) {
            showAlert(`Added "${scheduleName}" to comparison`, 'success');
        }
    }
    
    // Update localStorage with the new list
    localStorage.setItem('scheduleComparison', JSON.stringify(comparisonList));
    
    console.log('Updated comparison list:', comparisonList);
    
    // Update controls and checkboxes
    updateComparisonControls();
    
    // If the list is empty, ensure all checkboxes are unchecked
    if (comparisonList.length === 0) {
        document.querySelectorAll('.schedule-compare-checkbox').forEach(checkbox => {
            checkbox.checked = false;
        });
    }
}

function updateComparisonCheckboxes() {
    let comparisonList = JSON.parse(localStorage.getItem('scheduleComparison') || '[]');
    
    console.log('updateComparisonCheckboxes: Initial comparison list from localStorage:', comparisonList);
    
    // Clean up localStorage - only keep schedules that exist on the current page
    const validScheduleIds = Array.from(document.querySelectorAll('.schedule-compare-checkbox'))
        .map(checkbox => String(checkbox.value)); // Convert to string for comparison
    
    console.log('Valid schedule IDs on this page:', validScheduleIds);
    
    // Filter to only include schedules that exist on this page (convert IDs to strings for comparison)
    const validComparisonList = comparisonList.filter(item => validScheduleIds.includes(String(item.id)));
    
    if (validComparisonList.length !== comparisonList.length) {
        console.log('Cleaned up comparison list - removed non-existent schedules:', {
            before: comparisonList.length,
            after: validComparisonList.length,
            removed: comparisonList.filter(item => !validScheduleIds.includes(String(item.id)))
        });
    }
    
    comparisonList = validComparisonList;
    
    // Limit to max 3 schedules
    if (comparisonList.length > 3) {
        console.log('Trimming comparison list from', comparisonList.length, 'to 3');
        comparisonList = comparisonList.slice(0, 3);
    }
    
    // Save cleaned list BEFORE updating controls
    localStorage.setItem('scheduleComparison', JSON.stringify(comparisonList));
    console.log('Final comparison list saved to localStorage:', comparisonList);
    
    // Check the boxes for schedules in the comparison list
    comparisonList.forEach(item => {
        const checkbox = document.getElementById(`schedule-${item.id}`);
        if (checkbox) {
            console.log('Checking checkbox for schedule:', item.id);
            // Temporarily remove the onchange handler to avoid triggering alerts
            const originalHandler = checkbox.onchange;
            checkbox.onchange = null;
            checkbox.checked = true;
            // Restore the handler
            checkbox.onchange = originalHandler;
        } else {
            console.warn('Checkbox not found for schedule:', item.id);
        }
    });
    
    // Now update the controls with the cleaned list
    updateComparisonControls();
}

function updateComparisonControls() {
    const comparisonList = JSON.parse(localStorage.getItem('scheduleComparison') || '[]');
    const viewComparisonBtn = document.getElementById('view-comparison-btn');
    const comparisonCountSpan = document.getElementById('comparison-count');
    
    console.log('updateComparisonControls called:', {
        comparisonListLength: comparisonList.length,
        isCompareMode: isCompareMode,
        comparisonList: comparisonList
    });
    
    // Always update the count first
    if (comparisonCountSpan) {
        comparisonCountSpan.textContent = comparisonList.length;
    }
    
    if (isCompareMode && comparisonList.length >= 2) {
        // Show view comparison button
        if (viewComparisonBtn) {
            viewComparisonBtn.style.display = 'inline-block';
        }
    } else {
        // Hide view comparison button
        if (viewComparisonBtn) {
            viewComparisonBtn.style.display = 'none';
        }
    }
}

function viewComparison() {
    const comparisonList = JSON.parse(localStorage.getItem('scheduleComparison') || '[]');
    
    if (comparisonList.length < 2) {
        showAlert('Please select at least 2 schedules for comparison', 'warning');
        return;
    }
    
    const scheduleIds = comparisonList.map(item => item.id);
    const queryParams = scheduleIds.map(id => `schedules=${id}`).join('&');
    
    window.open(`/schedule/compare/?${queryParams}`, '_blank');
}

function clearComparison() {
    if (confirm('Are you sure you want to clear all schedules from comparison?')) {
        // Clear localStorage
        localStorage.removeItem('scheduleComparison');
        
        // Uncheck all checkboxes
        document.querySelectorAll('.schedule-compare-checkbox').forEach(checkbox => {
            checkbox.checked = false;
        });
        
        // Uncheck select all checkbox
        const selectAllCheckbox = document.getElementById('select-all-schedules');
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = false;
        }
        
        // Update controls to hide the comparison button
        updateComparisonControls();
        
        console.log('Comparison cleared, localStorage:', localStorage.getItem('scheduleComparison'));
        
        showAlert('Comparison cleared successfully', 'success');
    }
}

// Add a function to force refresh comparison state
function refreshComparisonState() {
    const comparisonList = JSON.parse(localStorage.getItem('scheduleComparison') || '[]');
    
    console.log('Refreshing comparison state:', comparisonList);
    
    // Update all checkboxes to match localStorage
    document.querySelectorAll('.schedule-compare-checkbox').forEach(checkbox => {
        const scheduleId = checkbox.id.replace('schedule-', '');
        const isSelected = comparisonList.some(item => item.id === scheduleId);
        checkbox.checked = isSelected;
    });
    
    // Update controls
    updateComparisonControls();
}

// Debug function to check current state
function debugComparisonState() {
    const comparisonList = JSON.parse(localStorage.getItem('scheduleComparison') || '[]');
    const viewComparisonBtn = document.getElementById('view-comparison-btn');
    const comparisonCountSpan = document.getElementById('comparison-count');
    
    console.log('=== COMPARISON DEBUG STATE ===');
    console.log('localStorage scheduleComparison:', comparisonList);
    console.log('isCompareMode:', typeof isCompareMode !== 'undefined' ? isCompareMode : 'undefined');
    console.log('View comparison button:', viewComparisonBtn ? viewComparisonBtn.style.display : 'not found');
    console.log('Comparison count span:', comparisonCountSpan ? comparisonCountSpan.textContent : 'not found');
    
    // Check all checkboxes
    const checkedCheckboxes = [];
    document.querySelectorAll('.schedule-compare-checkbox').forEach(checkbox => {
        if (checkbox.checked) {
            checkedCheckboxes.push(checkbox.id);
        }
    });
    console.log('Checked checkboxes:', checkedCheckboxes);
    console.log('===============================');
    
    return {
        localStorage: comparisonList,
        isCompareMode: typeof isCompareMode !== 'undefined' ? isCompareMode : undefined,
        buttonVisible: viewComparisonBtn ? viewComparisonBtn.style.display !== 'none' : false,
        count: comparisonCountSpan ? comparisonCountSpan.textContent : null,
        checkedCheckboxes: checkedCheckboxes
    };
}

// ===== RIG DETAILS MODAL FUNCTIONS =====

/**
 * Show detailed information for a specific rig
 * @param {string} rigId - The UUID of the rig to display
 */
async function showRigDetails(rigId) {
    if (!rigId) {
        console.error('No rig ID provided to showRigDetails');
        return;
    }

    // Show the modal
    const modal = new bootstrap.Modal(document.getElementById('rigDetailsModal'));
    modal.show();

    // Show loading state
    document.getElementById('rigDetailsLoading').style.display = 'block';
    document.getElementById('rigDetailsContent').style.display = 'none';
    document.getElementById('rigDetailsError').style.display = 'none';

    try {
        // Fetch rig details from API
        const response = await fetch(`${ENDPOINTS.rigs}${rigId}/`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const rig = await response.json();
        
        // Populate modal with rig details
        populateRigDetailsModal(rig);
        
        // Show content and hide loading
        document.getElementById('rigDetailsLoading').style.display = 'none';
        document.getElementById('rigDetailsContent').style.display = 'block';
        
        // Store rig ID for edit button
        document.getElementById('editRigFromDetails').setAttribute('data-rig-id', rigId);
        document.getElementById('editRigFromDetails').style.display = 'inline-block';

    } catch (error) {
        console.error('Error fetching rig details:', error);
        
        // Show error state
        document.getElementById('rigDetailsLoading').style.display = 'none';
        document.getElementById('rigDetailsError').style.display = 'block';
        document.getElementById('rigDetailsContent').style.display = 'none';
        document.getElementById('editRigFromDetails').style.display = 'none';
    }
}

/**
 * Populate the rig details modal with data
 * @param {Object} rig - The rig data object
 */
function populateRigDetailsModal(rig) {
    // Helper function to safely display values
    const displayValue = (value, defaultValue = 'Not specified') => {
        return (value !== null && value !== undefined && value !== '') ? value : defaultValue;
    };

    // Helper function to format currency
    const formatCurrency = (value) => {
        if (value === null || value === undefined || value === '') return 'Not specified';
        return `₹${parseFloat(value).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
    };

    // Helper function to format Yes/No values
    const formatYesNo = (value) => {
        if (value === 'Y') return 'Yes';
        if (value === 'N') return 'No';
        return displayValue(value);
    };

    // Helper function to format dates
    const formatDate = (dateString) => {
        if (!dateString) return 'Not specified';
        try {
            return new Date(dateString).toLocaleDateString('en-GB', {
                day: '2-digit',
                month: '2-digit', 
                year: 'numeric'
            });
        } catch (e) {
            return dateString;
        }
    };

    // Helper function to calculate duration
    const calculateDuration = (startDate, endDate) => {
        if (!startDate || !endDate) return 'Not available';
        try {
            const start = new Date(startDate);
            const end = new Date(endDate);
            const diffTime = Math.abs(end - start);
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1; // +1 to include both start and end dates
            return `${diffDays} days`;
        } catch (e) {
            return 'Not available';
        }
    };

    // Helper function to determine current availability status
    const getAvailabilityStatus = (startDate, endDate) => {
        if (!startDate || !endDate) return 'Unknown';
        try {
            const today = new Date();
            const start = new Date(startDate);
            const end = new Date(endDate);
            
            if (today >= start && today <= end) {
                return '<span class="badge bg-success">Currently Available</span>';
            } else if (today < start) {
                return '<span class="badge bg-warning">Future Availability</span>';
            } else {
                return '<span class="badge bg-secondary">Past Availability</span>';
            }
        } catch (e) {
            return 'Unknown';
        }
    };

    // Basic Information
    document.getElementById('rigDetailName').textContent = displayValue(rig.name);
    document.getElementById('rigDetailAssetId').textContent = displayValue(rig.asset_id);
    document.getElementById('rigDetailType').innerHTML = rig.rig_type ? 
        `<span class="badge bg-${rig.rig_type === 'Mobile' ? 'primary' : 'secondary'}">${rig.rig_type}</span>` : 
        'Not specified';
    
    document.getElementById('rigDetailAvailability').textContent = 
        `${formatDate(rig.start_date)} to ${formatDate(rig.end_date)}`;
    document.getElementById('rigDetailDuration').textContent = 
        calculateDuration(rig.start_date, rig.end_date);
    document.getElementById('rigDetailStatus').innerHTML = 
        getAvailabilityStatus(rig.start_date, rig.end_date);

    // Technical Specifications
    document.getElementById('rigDetailCapacity').textContent = 
        rig.rig_capacity_hp ? `${rig.rig_capacity_hp} HP` : 'Not specified';
    document.getElementById('rigDetailDrillingCapacity').textContent = 
        rig.drilling_capacity_m ? `${rig.drilling_capacity_m} meters` : 'Not specified';
    document.getElementById('rigDetailBopStack').textContent = displayValue(rig.bop_stack);
    document.getElementById('rigDetailTds').textContent = formatYesNo(rig.tds_availability);
    document.getElementById('rigDetailHpht').textContent = formatYesNo(rig.hpht_suitability);
    document.getElementById('rigDetailCrewAvailability').textContent = displayValue(rig.crew_availability);

    // Cost Information
    document.getElementById('rigDetailDailyCost').textContent = formatCurrency(rig.daily_cost_inr);
    document.getElementById('rigDetailIlmFixed').textContent = formatCurrency(rig.ilm_cost_fixed);
    document.getElementById('rigDetailIlmPerKm').textContent = formatCurrency(rig.ilm_cost_per_km);
    document.getElementById('rigDetailIlmCluster').textContent = formatCurrency(rig.ilm_cost_cluster);

    // Additional Information
    document.getElementById('rigDetailMobilization').textContent = displayValue(rig.mobilization_time_days);
    document.getElementById('rigDetailMaintenance').textContent = displayValue(rig.maintenance_schedule);
}

// Add event listener for edit button in rig details modal
document.addEventListener('DOMContentLoaded', function() {
    const editButton = document.getElementById('editRigFromDetails');
    if (editButton) {
        editButton.addEventListener('click', function() {
            const rigId = this.getAttribute('data-rig-id');
            if (rigId && typeof editRig === 'function') {
                // Close the details modal first
                const modal = bootstrap.Modal.getInstance(document.getElementById('rigDetailsModal'));
                if (modal) {
                    modal.hide();
                }
                // Open the edit modal
                editRig(rigId);
            }
        });
    }
});

// Make showRigDetails globally available
window.showRigDetails = showRigDetails;

// Debug: Log that the function is available
console.log('showRigDetails function loaded:', typeof showRigDetails);
console.log('showRigDetails available on window:', typeof window.showRigDetails);

// ===== EDIT FORM POPULATION FUNCTIONS =====

/**
 * Populate the rig edit form with existing data
 * @param {Object} rig - The rig data object
 */
function populateRigEditForm(rig) {
    // Helper function to safely set input values
    const setValue = (id, value) => {
        const element = document.getElementById(id);
        if (element) {
            element.value = value || '';
        }
    };

    // Basic Information
    setValue('edit-rig-id', rig.id);
    setValue('edit-rig-name', rig.name);
    setValue('edit-rig-asset-id', rig.asset_id);
    setValue('edit-rig-type', rig.rig_type);
    setValue('edit-rig-start-date', rig.start_date);
    setValue('edit-rig-end-date', rig.end_date);

    // Technical Specifications
    setValue('edit-rig-capacity', rig.rig_capacity_hp);
    setValue('edit-rig-drilling-capacity', rig.drilling_capacity_m);
    setValue('edit-rig-bop-stack', rig.bop_stack);
    setValue('edit-rig-tds', rig.tds_availability);
    setValue('edit-rig-hpht', rig.hpht_suitability);

    // Cost Information
    setValue('edit-rig-daily-cost', rig.daily_cost_inr);
    setValue('edit-rig-ilm-fixed', rig.ilm_cost_fixed);
    setValue('edit-rig-ilm-per-km', rig.ilm_cost_per_km);
    setValue('edit-rig-ilm-cluster', rig.ilm_cost_cluster);

    // Additional Information
    setValue('edit-rig-mobilization', rig.mobilization_time_days);
    setValue('edit-rig-maintenance', rig.maintenance_schedule);
    setValue('edit-rig-crew', rig.crew_availability);
}

/**
 * Populate the well edit form with existing data
 * @param {Object} well - The well data object
 */
function populateWellEditForm(well) {
    // Helper function to safely set input values
    const setValue = (id, value) => {
        const element = document.getElementById(id);
        if (element) {
            element.value = value || '';
        }
    };

    // Helper function to format timestamps
    const formatTimestamp = (dateString) => {
        if (!dateString) return 'Unknown';
        try {
            const date = new Date(dateString);
            return date.toLocaleString('en-GB', { 
                day: '2-digit', 
                month: 'short', 
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
            });
        } catch {
            return 'Invalid date';
        }
    };

    // Update timestamps in header
    const timestampsElement = document.getElementById('edit-well-timestamps');
    if (timestampsElement) {
        if (well.created_at || well.updated_at) {
            timestampsElement.innerHTML = `
                ${well.created_at ? `<span><i class="bi bi-calendar-plus"></i> Created: ${formatTimestamp(well.created_at)}</span>` : ''}
                ${well.updated_at ? `<span><i class="bi bi-clock-history"></i> Updated: ${formatTimestamp(well.updated_at)}</span>` : ''}
            `;
            timestampsElement.style.display = 'flex';
        } else {
            timestampsElement.style.display = 'none';
        }
    }

    // Basic Information
    setValue('edit-well-id', well.id);
    setValue('edit-well-sn', well.sn);
    setValue('edit-well-name', well.name);
    setValue('edit-well-asset-id', well.asset_id);
    setValue('edit-well-latitude', well.latitude);
    setValue('edit-well-longitude', well.longitude);
    setValue('edit-well-type', well.well_type);
    setValue('edit-well-profile', well.well_profile);
    setValue('edit-well-priority', well.priority);
    setValue('edit-well-footprint', well.footprint);

    // Technical Specifications
    setValue('edit-well-depth', well.depth);
    setValue('edit-well-duration', well.duration);
    setValue('edit-well-drl-days', well.drl_days);
    setValue('edit-well-pt-days', well.pt_days);
    setValue('edit-well-rtd', well.rtd);

    // Requirements
    setValue('edit-well-rig-capacity', well.rig_capacity_required_hp);
    setValue('edit-well-bop-stack', well.bop_stack);
    setValue('edit-well-tds', well.tds_requirement);

    // Optional Information
    setValue('edit-well-preferred-rig', well.preferred_rig);
    setValue('edit-well-expected-potential', well.expected_potential);
}

// ===== UPDATE FUNCTIONS =====

/**
 * Update rig data via API
 */
async function updateRig() {
    const rigId = document.getElementById('edit-rig-id').value;
    if (!rigId) {
        showAlert('Error: No rig ID found', 'error');
        return;
    }

    // Collect form data
    const formData = new FormData(document.getElementById('editRigForm'));
    const rigData = {};
    
    // Convert FormData to object
    for (let [key, value] of formData.entries()) {
        if (key !== 'id') { // Don't include ID in update data
            rigData[key] = value;
        }
    }

    try {
        // Show loading state
        const updateButton = document.querySelector('#editRigModal .btn-primary');
        const originalText = updateButton.innerHTML;
        updateButton.innerHTML = '<i class="spinner-border spinner-border-sm me-1"></i>Updating...';
        updateButton.disabled = true;

        // Send update request
        const response = await fetch(`${ENDPOINTS.rigs}${rigId}/`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify(rigData)
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
        }

        const updatedRig = await response.json();

        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('editRigModal'));
        modal.hide();

        // Refresh the rigs table
        await loadRigsTable();

        // Show success message
        showAlert(`Rig "${updatedRig.name}" updated successfully!`, 'success');

    } catch (error) {
        console.error('Error updating rig:', error);
        showAlert(`Error updating rig: ${error.message}`, 'error');
    } finally {
        // Reset button state
        const updateButton = document.querySelector('#editRigModal .btn-primary');
        updateButton.innerHTML = '<i class="bi bi-check-lg me-1"></i>Update Rig';
        updateButton.disabled = false;
    }
}

/**
 * Update well data via API
 */
async function updateWell() {
    const wellId = document.getElementById('edit-well-id').value;
    if (!wellId) {
        showAlert('Error: No well ID found', 'error');
        return;
    }

    // Collect form data
    const formData = new FormData(document.getElementById('editWellForm'));
    const wellData = {};
    
    // List of read-only fields that should not be included in update
    const readOnlyFields = ['id', 'has_duration_mismatch', 'duration_validation_message', 'priority_code', 'created_at', 'updated_at'];
    
    // Convert FormData to object
    for (let [key, value] of formData.entries()) {
        if (!readOnlyFields.includes(key)) {
            // Convert empty strings to null for numeric fields
            if (value === '' && ['duration', 'drl_days', 'pt_days', 'depth'].includes(key)) {
                wellData[key] = null;
            } else {
                wellData[key] = value;
            }
        }
    }
    
    console.log('Sending well update data:', wellData);

    // Check duration mismatch and show warning (but don't block save)
    const duration = parseInt(wellData.duration);
    const drlDays = parseInt(wellData.drl_days);
    const ptDays = parseInt(wellData.pt_days);
    
    if (duration !== drlDays + ptDays) {
        console.warn(`Duration mismatch: ${duration} ≠ ${drlDays} + ${ptDays}`);
        // Don't block the save, just log a warning
    }

    try {
        // Show loading state
        const updateButton = document.querySelector('#editWellModal .btn-success');
        const originalText = updateButton.innerHTML;
        updateButton.innerHTML = '<i class="spinner-border spinner-border-sm me-1"></i>Updating...';
        updateButton.disabled = true;

        // Send update request
        const response = await fetch(`${ENDPOINTS.wells}${wellId}/`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify(wellData)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            console.error('Server error response:', errorData);
            
            // Try to extract meaningful error message
            let errorMessage = 'Unknown error';
            if (errorData.detail) {
                errorMessage = errorData.detail;
            } else if (errorData.non_field_errors) {
                errorMessage = errorData.non_field_errors.join(', ');
            } else if (typeof errorData === 'object') {
                // Field-specific errors
                errorMessage = Object.entries(errorData)
                    .map(([field, errors]) => `${field}: ${Array.isArray(errors) ? errors.join(', ') : errors}`)
                    .join('; ');
            }
            
            throw new Error(errorMessage || `HTTP ${response.status}: ${response.statusText}`);
        }

        const updatedWell = await response.json();

        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('editWellModal'));
        modal.hide();

        // Refresh the wells table
        await loadWellsTable();

        // Show success message
        showAlert(`Well "${updatedWell.name}" updated successfully!`, 'success');

    } catch (error) {
        console.error('Error updating well:', error);
        showAlert(`Error updating well: ${error.message}`, 'error');
    } finally {
        // Reset button state
        const updateButton = document.querySelector('#editWellModal .btn-success');
        updateButton.innerHTML = '<i class="bi bi-check-lg me-1"></i>Update Well';
        updateButton.disabled = false;
    }
}

// ===== WELL DETAILS FUNCTIONALITY =====

/**
 * Show well details in a modal
 * @param {string} wellId - The well ID to fetch details for
 */
async function showWellDetails(wellId) {
    if (!wellId) {
        console.error('No well ID provided to showWellDetails');
        return;
    }

    // Show modal with loading state
    const modal = new bootstrap.Modal(document.getElementById('wellDetailsModal'));
    modal.show();
    
    // Show loading state
    document.getElementById('wellDetailsLoading').style.display = 'block';
    document.getElementById('wellDetailsContent').style.display = 'none';
    document.getElementById('wellDetailsError').style.display = 'none';
    document.getElementById('editWellFromDetails').style.display = 'none';

    try {
        const response = await fetch(`/api/wells/${wellId}/`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const well = await response.json();
        
        // Hide loading state
        document.getElementById('wellDetailsLoading').style.display = 'none';
        document.getElementById('wellDetailsContent').style.display = 'block';
        
        // Populate the modal with well data
        populateWellDetailsModal(well);
        
        // Show edit button and store well ID
        document.getElementById('editWellFromDetails').setAttribute('data-well-id', wellId);
        document.getElementById('editWellFromDetails').style.display = 'inline-block';

    } catch (error) {
        console.error('Error fetching well details:', error);
        
        // Show error state
        document.getElementById('wellDetailsLoading').style.display = 'none';
        document.getElementById('wellDetailsError').style.display = 'block';
        document.getElementById('wellDetailsContent').style.display = 'none';
        document.getElementById('editWellFromDetails').style.display = 'none';
    }
}

/**
 * Populate the well details modal with data
 * @param {Object} well - The well data object
 */
function populateWellDetailsModal(well) {
    // Helper function to safely display values
    const displayValue = (value, defaultValue = 'Not specified') => {
        return value != null && value !== '' ? value : defaultValue;
    };

    // Helper function to format dates
    const formatDate = (dateString) => {
        if (!dateString) return 'Not specified';
        try {
            return new Date(dateString).toLocaleDateString('en-GB');
        } catch {
            return dateString;
        }
    };

    // Helper function to format timestamps
    const formatTimestamp = (dateString) => {
        if (!dateString) return 'Unknown';
        try {
            const date = new Date(dateString);
            return date.toLocaleString('en-GB', { 
                day: '2-digit', 
                month: 'short', 
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
            });
        } catch {
            return 'Invalid date';
        }
    };

    // Helper function to get badge classes
    const getBadgeClass = (type, value) => {
        if (type === 'wellType') {
            return value === 'EXP' ? 'bg-info' : 'bg-success';
        } else if (type === 'priority') {
            switch (value) {
                case 'HIGH': return 'bg-danger';
                case 'MEDIUM': return 'bg-warning';
                case 'LOW': return 'bg-secondary';
                default: return 'bg-secondary';
            }
        } else if (type === 'tds') {
            return value === 'Y' ? 'bg-success' : 'bg-secondary';
        }
        return 'bg-primary';
    };

    // Update timestamps in header
    const timestampsElement = document.getElementById('view-well-timestamps');
    if (timestampsElement) {
        if (well.created_at || well.updated_at) {
            timestampsElement.innerHTML = `
                ${well.created_at ? `<span><i class="bi bi-calendar-plus"></i> Created: ${formatTimestamp(well.created_at)}</span>` : ''}
                ${well.updated_at ? `<span><i class="bi bi-clock-history"></i> Updated: ${formatTimestamp(well.updated_at)}</span>` : ''}
            `;
            timestampsElement.style.display = 'flex';
        } else {
            timestampsElement.style.display = 'none';
        }
    }

    // Basic Information
    document.getElementById('wellDetailName').textContent = displayValue(well.name);
    document.getElementById('wellDetailAssetId').textContent = displayValue(well.asset_id);
    
    // Well Type Badge
    const wellTypeElement = document.getElementById('wellDetailType');
    wellTypeElement.textContent = displayValue(well.well_type);
    wellTypeElement.className = `badge ${getBadgeClass('wellType', well.well_type)}`;
    
    // Priority Badge
    const priorityElement = document.getElementById('wellDetailPriority');
    priorityElement.textContent = displayValue(well.priority);
    priorityElement.className = `badge ${getBadgeClass('priority', well.priority)}`;
    
    document.getElementById('wellDetailDuration').textContent = displayValue(well.duration) + ' days';
    document.getElementById('wellDetailDepth').textContent = displayValue(well.depth) + 'm';

    // Drilling & Testing Details
    document.getElementById('wellDetailDrlDays').textContent = displayValue(well.drl_days) + ' days';
    document.getElementById('wellDetailPtDays').textContent = displayValue(well.pt_days) + ' days';
    document.getElementById('wellDetailRtd').textContent = formatDate(well.rtd);

    // Requirements
    document.getElementById('wellDetailRigCapacity').textContent = displayValue(well.rig_capacity_required_hp) + ' HP';
    document.getElementById('wellDetailBopStack').textContent = displayValue(well.bop_stack);
    
    // TDS Badge
    const tdsElement = document.getElementById('wellDetailTds');
    const tdsValue = well.tds_requirement === 'Y' ? 'Required' : 'Not Required';
    tdsElement.textContent = tdsValue;
    tdsElement.className = `badge ${getBadgeClass('tds', well.tds_requirement)}`;

    // Location Information
    document.getElementById('wellDetailLatitude').textContent = displayValue(well.latitude);
    document.getElementById('wellDetailLongitude').textContent = displayValue(well.longitude);

    // Additional Information
    document.getElementById('wellDetailExpectedPotential').textContent = displayValue(well.expected_potential);
    document.getElementById('wellDetailNotes').textContent = displayValue(well.notes || '');
}

// Add event listener for edit button in well details modal
document.addEventListener('DOMContentLoaded', function() {
    const editButton = document.getElementById('editWellFromDetails');
    if (editButton) {
        editButton.addEventListener('click', function() {
            const wellId = this.getAttribute('data-well-id');
            if (wellId && typeof editWell === 'function') {
                // Close the details modal first
                const modal = bootstrap.Modal.getInstance(document.getElementById('wellDetailsModal'));
                if (modal) {
                    modal.hide();
                }
                // Open the edit modal
                editWell(wellId);
            }
        });
    }
});

// Make showWellDetails globally available
window.showWellDetails = showWellDetails;

// Debug: Log that the function is available
console.log('showWellDetails function loaded:', typeof showWellDetails);
console.log('showWellDetails available on window:', typeof window.showWellDetails);

// Make edit functions globally available
window.editRig = editRig;
window.editWell = editWell;
window.updateRig = updateRig;
window.updateWell = updateWell;
