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
from datetime import datetime, timedelta
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

def query_detections(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    camera_location: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Query detection data with camera information from BigQuery.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        limit: Maximum number of results to return
        camera_location: Filter by camera location
        
    Returns:
        List of detection records with camera metadata
    """
    try:
        # Base query using the joined view
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
                'detection_timestamp': row.detection_timestamp.isoformat() if row.detection_timestamp else None,
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
        
        # Default to last 7 days if no dates specified
        if not start_date and not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        # Query detections
        detections = query_detections(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            camera_location=camera_location
        )
        
        return jsonify({
            'success': True,
            'count': len(detections),
            'detections': detections,
            'filters': {
                'start_date': start_date,
                'end_date': end_date,
                'limit': limit,
                'camera_location': camera_location
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
