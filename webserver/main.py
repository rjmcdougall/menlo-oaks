#!/usr/bin/env python3
"""
Google Cloud Function for serving an interactive map of license plate detections.

This function provides:
1. A web interface with Mapbox map showing detection events
2. API endpoints to query BigQuery for detection data with camera info
3. Interactive popups with detection metadata and thumbnails
"""

import os
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from flask import Flask, render_template, request, jsonify, send_from_directory
from google.cloud import bigquery
import functions_framework

app = Flask(__name__)

# Configuration from environment variables
PROJECT_ID = os.getenv('GCP_PROJECT_ID', 'your-project-id')
DATASET_ID = os.getenv('BIGQUERY_DATASET', 'license_plates')
MAPBOX_ACCESS_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN', 'your-mapbox-token')

# Initialize BigQuery client
client = bigquery.Client(project=PROJECT_ID)

def format_timestamp_as_utc(dt):
    """Ensure datetime is treated as UTC and format as ISO string with Z suffix."""
    if dt is None:
        return None
    
    # If datetime is naive (no timezone info), assume it's UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to UTC if it's not already
    dt_utc = dt.astimezone(timezone.utc)
    
    # Return ISO format with Z suffix to clearly indicate UTC
    return dt_utc.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

def query_detections(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    camera_location: Optional[str] = None,
    unknown_only: bool = False
) -> List[Dict[str, Any]]:
    """Query detection data with camera information from BigQuery.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        limit: Maximum number of results to return
        camera_location: Filter by camera location
        unknown_only: If True, only return plates seen < 20 times total
        
    Returns:
        List of detection records with camera metadata
    """
    try:
        # Build the base query - use CTE for unknown vehicles filter
        if unknown_only:
            base_query = f"""
            WITH known_plates AS (
                SELECT plate_number
                FROM `{PROJECT_ID}.{DATASET_ID}.detections_with_camera_info`
                WHERE plate_number IS NOT NULL AND plate_number != ''
                GROUP BY plate_number
                HAVING COUNT(*) >= 20
            )
            SELECT 
                record_id,
                plate_number,
                confidence,
                detection_timestamp,
                vehicle_type,
                vehicle_color,
                event_id,
                thumbnail_public_url,
                cropped_thumbnail_public_url,
                camera_name,
                camera_location,
                latitude,
                longitude,
                camera_model,
                camera_active,
                camera_notes
            FROM `{PROJECT_ID}.{DATASET_ID}.detections_with_camera_info`
            WHERE camera_active = true
            AND plate_number NOT IN (SELECT plate_number FROM known_plates)
            AND plate_number IS NOT NULL AND plate_number != ''
            """
        else:
            base_query = f"""
            SELECT 
                record_id,
                plate_number,
                confidence,
                detection_timestamp,
                vehicle_type,
                vehicle_color,
                event_id,
                thumbnail_public_url,
                cropped_thumbnail_public_url,
                camera_name,
                camera_location,
                latitude,
                longitude,
                camera_model,
                camera_active,
                camera_notes
            FROM `{PROJECT_ID}.{DATASET_ID}.detections_with_camera_info`
            WHERE camera_active = true
            """
        
        # Add filters
        conditions = []
        params = {}
        
        if start_date:
            conditions.append("DATE(detection_timestamp) >= @start_date")
            params['start_date'] = start_date
        
        if end_date:
            conditions.append("DATE(detection_timestamp) <= @end_date")
            params['end_date'] = end_date
            
        if camera_location:
            conditions.append("LOWER(camera_location) LIKE LOWER(@camera_location)")
            params['camera_location'] = f"%{camera_location}%"
        
        # Only include detections with valid coordinates
        conditions.append("latitude IS NOT NULL AND longitude IS NOT NULL")
        
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        base_query += f" ORDER BY detection_timestamp DESC LIMIT {limit}"
        
        # Configure query job
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(k, "STRING", v) 
                for k, v in params.items()
            ]
        )
        
        # Execute query
        query_job = client.query(base_query, job_config=job_config)
        results = query_job.result()
        
        # Convert to list of dictionaries
        detections = []
        for row in results:
            detection = {
                'record_id': row.record_id,
                'plate_number': row.plate_number,
                'confidence': float(row.confidence or 0),
                'detection_timestamp': format_timestamp_as_utc(row.detection_timestamp),
                'vehicle_type': row.vehicle_type,
                'vehicle_color': row.vehicle_color,
                'event_id': row.event_id,
                'thumbnail_public_url': row.thumbnail_public_url,
                'cropped_thumbnail_public_url': row.cropped_thumbnail_public_url,
                'camera_name': row.camera_name,
                'camera_location': row.camera_location,
                'latitude': float(row.latitude) if row.latitude is not None else None,
                'longitude': float(row.longitude) if row.longitude is not None else None,
                'camera_model': row.camera_model,
                'camera_active': row.camera_active,
                'camera_notes': row.camera_notes
            }
            detections.append(detection)
        
        return detections
        
    except Exception as e:
        print(f"Error querying detections: {str(e)}")
        return []

@app.route('/')
def index():
    """Serve the main map interface."""
    return render_template('map.html', mapbox_token=MAPBOX_ACCESS_TOKEN)

@app.route('/api/detections')
def api_detections():
    """API endpoint to get detection data."""
    try:
        # Get query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        limit = int(request.args.get('limit', 100))
        camera_location = request.args.get('camera_location')
        unknown_only = request.args.get('unknown_only', '').lower() == 'true'
        
        # Default to last 7 days if no dates specified
        if not start_date and not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        # Query detections
        detections = query_detections(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            camera_location=camera_location,
            unknown_only=unknown_only
        )
        
        return jsonify({
            'success': True,
            'count': len(detections),
            'detections': detections,
            'filters': {
                'start_date': start_date,
                'end_date': end_date,
                'limit': limit,
                'camera_location': camera_location,
                'unknown_only': unknown_only
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/cameras')
def api_cameras():
    """API endpoint to get camera locations for filtering."""
    try:
        query = f"""
        SELECT DISTINCT 
            camera_location,
            camera_name,
            latitude,
            longitude,
            COUNT(*) as detection_count
        FROM `{PROJECT_ID}.{DATASET_ID}.detections_with_camera_info`
        WHERE camera_active = true 
        AND latitude IS NOT NULL 
        AND longitude IS NOT NULL
        GROUP BY camera_location, camera_name, latitude, longitude
        ORDER BY detection_count DESC
        """
        
        query_job = client.query(query)
        results = query_job.result()
        
        cameras = []
        for row in results:
            cameras.append({
                'camera_location': row.camera_location,
                'camera_name': row.camera_name,
                'latitude': float(row.latitude),
                'longitude': float(row.longitude),
                'detection_count': row.detection_count
            })
        
        return jsonify({
            'success': True,
            'cameras': cameras
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/plates/search')
def api_plate_search():
    """API endpoint for plate number autocomplete search."""
    try:
        query_term = request.args.get('q', '').strip().upper()
        limit = int(request.args.get('limit', 10))
        
        # Build the query based on whether we have a search term or not
        if len(query_term) >= 2:
            # Search for plates that start with or contain the query term
            search_query = f"""
            SELECT DISTINCT 
                plate_number,
                COUNT(*) as detection_count,
                MAX(detection_timestamp) as last_seen,
                COUNT(DISTINCT camera_location) as location_count
            FROM `{PROJECT_ID}.{DATASET_ID}.detections_with_camera_info`
            WHERE UPPER(plate_number) LIKE UPPER(@query_term)
            AND plate_number IS NOT NULL
            AND plate_number != ''
            GROUP BY plate_number
            ORDER BY detection_count DESC, last_seen DESC
            LIMIT {limit}
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter('query_term', 'STRING', f'%{query_term}%')
                ]
            )
        else:
            # No search term - return all plates sorted by detection count
            search_query = f"""
            SELECT DISTINCT 
                plate_number,
                COUNT(*) as detection_count,
                MAX(detection_timestamp) as last_seen,
                COUNT(DISTINCT camera_location) as location_count
            FROM `{PROJECT_ID}.{DATASET_ID}.detections_with_camera_info`
            WHERE plate_number IS NOT NULL
            AND plate_number != ''
            GROUP BY plate_number
            ORDER BY detection_count DESC, last_seen DESC
            LIMIT {limit}
            """
            
            job_config = bigquery.QueryJobConfig()
        
        query_job = client.query(search_query, job_config=job_config)
        results = query_job.result()
        
        plates = []
        for row in results:
            plates.append({
                'plate_number': row.plate_number,
                'detection_count': row.detection_count,
                'last_seen': format_timestamp_as_utc(row.last_seen),
                'location_count': row.location_count
            })
        
        return jsonify({
            'success': True,
            'plates': plates
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/plates/<plate_number>/locations')
def api_plate_locations(plate_number):
    """API endpoint to get all detections of a specific plate at different locations."""
    try:
        plate_number = plate_number.strip().upper()
        
        location_query = f"""
        SELECT 
            camera_location,
            camera_name,
            latitude,
            longitude,
            COUNT(*) as detection_count,
            MAX(detection_timestamp) as last_seen,
            MIN(detection_timestamp) as first_seen
        FROM `{PROJECT_ID}.{DATASET_ID}.detections_with_camera_info`
        WHERE UPPER(plate_number) = @plate_number
        AND latitude IS NOT NULL 
        AND longitude IS NOT NULL
        GROUP BY camera_location, camera_name, latitude, longitude
        ORDER BY detection_count DESC, last_seen DESC
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter('plate_number', 'STRING', plate_number)
            ]
        )
        
        query_job = client.query(location_query, job_config=job_config)
        results = query_job.result()
        
        locations = []
        for row in results:
            locations.append({
                'camera_location': row.camera_location,
                'camera_name': row.camera_name,
                'latitude': float(row.latitude),
                'longitude': float(row.longitude),
                'detection_count': row.detection_count,
                'last_seen': format_timestamp_as_utc(row.last_seen),
                'first_seen': format_timestamp_as_utc(row.first_seen)
            })
        
        return jsonify({
            'success': True,
            'plate_number': plate_number,
            'locations': locations,
            'total_locations': len(locations),
            'total_detections': sum(loc['detection_count'] for loc in locations)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/plates/<plate_number>/detections')
def api_plate_detections(plate_number):
    """API endpoint to get detailed detection history for a specific plate at a specific location."""
    try:
        plate_number = plate_number.strip().upper()
        camera_location = request.args.get('location', '').strip()
        
        base_query = f"""
        SELECT 
            record_id,
            detection_timestamp,
            confidence,
            vehicle_type,
            vehicle_color,
            event_id,
            thumbnail_public_url,
            cropped_thumbnail_public_url,
            camera_name,
            camera_location,
            camera_model,
            latitude,
            longitude
        FROM `{PROJECT_ID}.{DATASET_ID}.detections_with_camera_info`
        WHERE UPPER(plate_number) = @plate_number
        """
        
        params = [bigquery.ScalarQueryParameter('plate_number', 'STRING', plate_number)]
        
        if camera_location:
            base_query += " AND camera_location = @camera_location"
            params.append(bigquery.ScalarQueryParameter('camera_location', 'STRING', camera_location))
        
        base_query += " ORDER BY detection_timestamp DESC LIMIT 100"
        
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        query_job = client.query(base_query, job_config=job_config)
        results = query_job.result()
        
        detections = []
        for row in results:
            detection = {
                'record_id': row.record_id,
                'detection_timestamp': format_timestamp_as_utc(row.detection_timestamp),
                'confidence': float(row.confidence or 0),
                'vehicle_type': row.vehicle_type,
                'vehicle_color': row.vehicle_color,
                'event_id': row.event_id,
                'thumbnail_public_url': row.thumbnail_public_url,
                'cropped_thumbnail_public_url': row.cropped_thumbnail_public_url,
                'camera_name': row.camera_name,
                'camera_location': row.camera_location,
                'camera_model': row.camera_model,
                'latitude': float(row.latitude) if row.latitude is not None else None,
                'longitude': float(row.longitude) if row.longitude is not None else None
            }
            detections.append(detection)
        
        return jsonify({
            'success': True,
            'plate_number': plate_number,
            'camera_location': camera_location or 'All locations',
            'detections': detections,
            'count': len(detections)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/unknown-activity')
def api_unknown_activity():
    """Return unknown plates that exceeded 10 detections in any 10-minute window
    within the past 24 hours, grouped by plate + camera location.

    'Unknown' means the plate has been seen on fewer than 20 distinct calendar days.
    Matches the same threshold used by the real-time Telegram alert logic.
    """
    try:
        query = f"""
        WITH unknown_plates AS (
            SELECT plate_number
            FROM `{PROJECT_ID}.{DATASET_ID}.detections`
            WHERE plate_number IS NOT NULL AND plate_number != ''
            GROUP BY plate_number
            HAVING COUNT(DISTINCT DATE(detection_timestamp)) < 20
        ),
        recent AS (
            SELECT
                d.plate_number,
                d.detection_timestamp,
                d.device_id,
                COALESCE(c.camera_name, d.device_id)  AS camera_name,
                COALESCE(c.camera_location, '')        AS camera_location,
                c.latitude,
                c.longitude
            FROM `{PROJECT_ID}.{DATASET_ID}.detections` d
            JOIN unknown_plates u ON d.plate_number = u.plate_number
            LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.camera_lookup` c ON d.device_id = c.device_id
            WHERE d.detection_timestamp >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR)
              AND d.plate_number IS NOT NULL AND d.plate_number != ''
        ),
        windowed AS (
            SELECT *,
                COUNT(*) OVER (
                    PARTITION BY plate_number
                    ORDER BY UNIX_SECONDS(TIMESTAMP(detection_timestamp))
                    RANGE BETWEEN 600 PRECEDING AND CURRENT ROW
                ) AS detections_in_10min
            FROM recent
        ),
        qualifying AS (
            SELECT * FROM windowed WHERE detections_in_10min > 10
        )
        SELECT
            plate_number,
            camera_name,
            camera_location,
            latitude,
            longitude,
            MAX(detections_in_10min)                                                    AS peak_in_window,
            COUNT(*)                                                                     AS location_hit_count,
            MIN(detection_timestamp)                                                     AS first_seen,
            MAX(detection_timestamp)                                                     AS last_seen,
            MAX(detection_timestamp) >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 10 MINUTE)
                                                                                         AS is_recent
        FROM qualifying
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        GROUP BY plate_number, camera_name, camera_location, latitude, longitude
        ORDER BY is_recent DESC, peak_in_window DESC, plate_number, last_seen DESC
        """
        rows = client.query(query).result()
        results = []
        for row in rows:
            results.append({
                'plate_number':     row.plate_number,
                'camera_name':      row.camera_name or '',
                'camera_location':  row.camera_location or '',
                'latitude':         float(row.latitude),
                'longitude':        float(row.longitude),
                'peak_in_window':   row.peak_in_window,
                'location_hit_count': row.location_hit_count,
                'first_seen':       format_timestamp_as_utc(row.first_seen),
                'last_seen':        format_timestamp_as_utc(row.last_seen),
                'is_recent':        row.is_recent,
            })
        return jsonify({'success': True, 'detections': results, 'count': len(results)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/camera-lookup', methods=['GET'])
def api_camera_lookup_list():
    """List all camera_lookup rows merged with every device_id seen in detections.
    Unregistered device_ids appear with blank fields so the user knows to fill them in."""
    try:
        query = f"""
        SELECT
            d.device_id,
            d.detection_count,
            c.camera_id,
            c.camera_name,
            c.camera_location,
            c.latitude,
            c.longitude,
            c.camera_model,
            c.is_active,
            c.notes,
            c.installation_date,
            (c.device_id IS NOT NULL) AS registered
        FROM (
            SELECT device_id, COUNT(*) AS detection_count
            FROM `{PROJECT_ID}.{DATASET_ID}.detections`
            WHERE device_id IS NOT NULL AND device_id != ''
            GROUP BY device_id
        ) d
        LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.camera_lookup` c ON d.device_id = c.device_id
        ORDER BY registered ASC, d.detection_count DESC, c.camera_location, c.camera_name
        """
        rows = client.query(query).result()
        cameras = []
        for row in rows:
            cameras.append({
                'device_id': row.device_id,
                'detection_count': row.detection_count,
                'registered': row.registered,
                'camera_id': row.camera_id or '',
                'camera_name': row.camera_name or '',
                'camera_location': row.camera_location or '',
                'latitude': float(row.latitude) if row.latitude is not None else None,
                'longitude': float(row.longitude) if row.longitude is not None else None,
                'camera_model': row.camera_model or '',
                'is_active': row.is_active,
                'notes': row.notes or '',
                'installation_date': str(row.installation_date) if row.installation_date else '',
            })
        return jsonify({'success': True, 'cameras': cameras})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/camera-lookup', methods=['POST'])
def api_camera_lookup_add():
    """Add a new row to camera_lookup."""
    try:
        data = request.get_json(force=True) or {}
        device_id = (data.get('device_id') or '').strip()
        camera_name = (data.get('camera_name') or '').strip()
        if not device_id:
            return jsonify({'success': False, 'error': 'device_id is required'}), 400
        if not camera_name:
            return jsonify({'success': False, 'error': 'camera_name is required'}), 400

        lat = f"{float(data['latitude'])}" if data.get('latitude') not in (None, '') else 'NULL'
        lng = f"{float(data['longitude'])}" if data.get('longitude') not in (None, '') else 'NULL'
        active = 'TRUE' if data.get('is_active', True) else 'FALSE'
        inst = f"'{data['installation_date']}'" if data.get('installation_date') else 'NULL'

        query = f"""
        INSERT INTO `{PROJECT_ID}.{DATASET_ID}.camera_lookup`
            (device_id, camera_id, camera_name, camera_location, latitude, longitude,
             camera_model, is_active, notes, installation_date, created_at, updated_at)
        VALUES
            (@device_id, @camera_id, @camera_name, @camera_location, {lat}, {lng},
             @camera_model, {active}, @notes, {inst}, CURRENT_DATETIME(), CURRENT_DATETIME())
        """
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter('device_id', 'STRING', device_id),
            bigquery.ScalarQueryParameter('camera_id', 'STRING', data.get('camera_id', '') or device_id),
            bigquery.ScalarQueryParameter('camera_name', 'STRING', camera_name),
            bigquery.ScalarQueryParameter('camera_location', 'STRING', data.get('camera_location', '')),
            bigquery.ScalarQueryParameter('camera_model', 'STRING', data.get('camera_model', '')),
            bigquery.ScalarQueryParameter('notes', 'STRING', data.get('notes', '')),
        ])
        client.query(query, job_config=job_config).result()
        return jsonify({'success': True}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/camera-lookup/<device_id>', methods=['PUT'])
def api_camera_lookup_update(device_id):
    """Update an existing camera_lookup row by device_id."""
    try:
        data = request.get_json(force=True) or {}
        lat = f"{float(data['latitude'])}" if data.get('latitude') not in (None, '') else 'NULL'
        lng = f"{float(data['longitude'])}" if data.get('longitude') not in (None, '') else 'NULL'
        active = 'TRUE' if data.get('is_active', True) else 'FALSE'
        inst = f"'{data['installation_date']}'" if data.get('installation_date') else 'NULL'

        query = f"""
        UPDATE `{PROJECT_ID}.{DATASET_ID}.camera_lookup`
        SET camera_name = @camera_name,
            camera_location = @camera_location,
            latitude = {lat},
            longitude = {lng},
            camera_model = @camera_model,
            is_active = {active},
            notes = @notes,
            installation_date = {inst},
            updated_at = CURRENT_DATETIME()
        WHERE device_id = @device_id
        """
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter('camera_name', 'STRING', data.get('camera_name', '')),
            bigquery.ScalarQueryParameter('camera_location', 'STRING', data.get('camera_location', '')),
            bigquery.ScalarQueryParameter('camera_model', 'STRING', data.get('camera_model', '')),
            bigquery.ScalarQueryParameter('notes', 'STRING', data.get('notes', '')),
            bigquery.ScalarQueryParameter('device_id', 'STRING', device_id),
        ])
        client.query(query, job_config=job_config).result()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/camera-lookup/<device_id>', methods=['DELETE'])
def api_camera_lookup_delete(device_id):
    """Delete a camera_lookup row by device_id."""
    try:
        query = f"""
        DELETE FROM `{PROJECT_ID}.{DATASET_ID}.camera_lookup`
        WHERE device_id = @device_id
        """
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter('device_id', 'STRING', device_id),
        ])
        client.query(query, job_config=job_config).result()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files."""
    return send_from_directory('static', filename)

# Cloud Functions entry point - use Flask app as WSGI
@functions_framework.http  
def detection_map(request):
    """Cloud Function entry point - serves the Flask app."""
    # Use the Flask WSGI app directly with a simple environ conversion
    import io
    import sys
    
    # Build WSGI environ from Cloud Functions request
    environ = {
        'REQUEST_METHOD': request.method,
        'SCRIPT_NAME': '',
        'PATH_INFO': request.path or '/',
        'QUERY_STRING': request.query_string.decode('utf-8') if request.query_string else '',
        'CONTENT_TYPE': request.headers.get('Content-Type', ''),
        'CONTENT_LENGTH': str(len(request.get_data())),
        'SERVER_NAME': 'localhost',
        'SERVER_PORT': '80',
        'wsgi.version': (1, 0),
        'wsgi.url_scheme': 'https',
        'wsgi.input': io.BytesIO(request.get_data()),
        'wsgi.errors': sys.stderr,
        'wsgi.multithread': True,
        'wsgi.multiprocess': False,
        'wsgi.run_once': False
    }
    
    # Add HTTP headers to environ
    for key, value in request.headers.items():
        key = key.upper().replace('-', '_')
        if key not in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            environ['HTTP_' + key] = value
    
    # Call Flask WSGI app
    response_data = []
    response_status = [None]
    response_headers = []
    
    def start_response(status, headers, exc_info=None):
        response_status[0] = status
        response_headers[:] = headers
        return lambda data: None
    
    # Get response from Flask WSGI app
    app_iter = app.wsgi_app(environ, start_response)
    response_body = b''.join(app_iter)
    
    # Convert status to int
    status_code = int(response_status[0].split(' ', 1)[0]) if response_status[0] else 200
    
    # Convert headers to dict
    headers_dict = {}
    for header_tuple in response_headers:
        headers_dict[header_tuple[0]] = header_tuple[1]
    
    return response_body, status_code, headers_dict

# For local development
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
