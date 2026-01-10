#!/usr/bin/env python3
"""
Test script to verify license plate extraction from UniFi Protect webhook data
"""

import json
import sys
import os
from datetime import datetime

# Add the current directory to Python path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Sample webhook data from your actual UniFi Protect system
SAMPLE_WEBHOOK_DATA = {
    'alarm': {
        'name': 'LPR Webhook',
        'sources': [
            {'device': '28704E169362', 'type': 'include'},
            {'device': '942A6FD0AD1A', 'type': 'include'}
        ],
        'conditions': [
            {'condition': {'type': 'is', 'source': 'license_plate_unknown'}},
            {'condition': {'type': 'is', 'source': 'license_plate_known'}},
            {'condition': {'type': 'is', 'source': 'license_plate_of_interest'}}
        ],
        'triggers': [
            {
                'device': '942A6FD0AD1A',
                'value': '7ERF019',
                'key': 'license_plate_unknown',
                'group': {'name': '7ERF019'},
                'zones': {'loiter': [], 'line': [], 'zone': [1]},
                'eventId': '68ce4d9c0202bb03e40cbdbc',
                'timestamp': 1758350753085
            }
        ],
        'thumbnail': 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAIBAQEBAQIBAQECAgICAgQDAgICAgUEBAMEBgUGBgYFBgYGBwkIBgcJBwYGCAsICQoKCgoKBggLDAsKDAkKCgr/2wBDAQICAgICAgUDAwUKBwYHCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgr/wAARCAFoAWgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD+f+iiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKK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L8RtNt0Ts8+Wb0wqgk81+aP/AAWE/wCC/Hws+Hnww1L4TfCrUXF9d2E0txdhnjeaLY6JGhHEZMhXO4EYIGMsAQD8fP8AguNe+Gx8b2tIdRivVkvbl3t7S5+W3uD8vmsQCCGVQNoP8B/Er4w+OHxh8TfGzx3d+NPEt8ZZLpxIqDomVGew5znJAxnpxiigCh8NPiDrXw28TW/iPQLsW91BPHJBctuIiYMOdoOGBGQQQcgnGDzX7Lf8EyP+DjTx98NfDej/AA6+JHieK6urmRhG7RFLYvnAgKkEghAArZ+Y5AC8CvxHq1pmsXmlXKXNsykp0R1yp+o/LnrwKAP7Cvg//wAFwPgD470trjXInsLlQHeGbehVT1OyRQ5CsdrEDCnGcZFdj4k/4LJfsh+FfDF3r2peM03W0DOqsGVZCOcK+3DHGeBzxX8fvgX9orxh8P7u31bw7BAuqQoUGqXWZHIJOCeMnAJGM7SPvK2Bi34k/ar+K+tajcaja+IJNPmnyJGsIY4S6kYILIobnJzzg/3eTQB+iX/Bbf8A4LT+Jf2rvFGqaF4FvdIg0wOkUFszSPcRRtENoVNxjODli5xkOFKkjj8pL29vNRu5L6/uXmmlcvLLIxLMx6kk0t9qWoalM9xqF7LO8krSu8shYs7HLOSerE8k96hoAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigCS1vLmzZntpNpeNkfgHKkYI5/yCARyK9Z+Bf7Y/xh+COtwX+geML2OG2VTbwCd8K4A/iB3ANjkZIBOcV5FRQB9UeMv+CqPx58XrJ9u8WapM8X7yxae8dlSUgqT5bFlTC9xk5xz2Hz98QvjD8QfideSXnjDxHcXfmSiVkkYYDgYyAAABycDtn8a5iigAJzyaKKKACiiigApWZnYu7Ek9ST1pKKACiiigAooooAKKKKACiiigArU8O6t4b02x1WDX/CY1Ka708w6XcG+eH7BceYh8/avEvyB12NgZcNn5cHLooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACp00vUH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XeaL+1F+0d4c8H23w+0H45eKbPQ7OBoLPSrfW5kggjZmZkRA2FBLucD+8fWuDooAfPPPdTvdXUzySyOWkkkYlmYnJJJ6knvTKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAor0r9mP9kr47ftd+Povh98EfA91qdy2GuroIRBax5wXd+g+gyT0Ar9dP2Yv+DSHxv4t0WHWfil4kustBE0iwX6QBpCSWUq0RIUYXo2Tk5245APxBor+lr4Y/8ABph8CfD8af8ACV6utzNDMZLd3ZbhoyQRt3TBgVB+bbwMknGevq2jf8Gv/wCxlYQsL/w/bXNxMoLXTK6NGfYRoFOcDtn0NAH8qBVgASCMjI96Sv6afjz/AMGkX7O3jzSrn/hANcj0m/LO8JtoABLkKArOTuXkZDfNjkbeTX4cf8FT/wDgld8c/wDglr8bI/hv8UEa90fVUM3h7Xlg8tLpAAWQjccMuQMg4bBI6EAA+XaKKKACiiigAooooAKKKKAPpL/gnl/wS4/aW/4KQeNz4Y+CuiiKxhdheavcwSNFHt27gNoO4gODjIGAec4B/VfwV/wZjaldaDFdeLvjPqMV6sai4iS4gCu+BkqoiO0derseenFfN/8AwQ3/AODjDwp/wS/+E9z+z/8AFn9nxdX0OS9NzbeIfD0EX2/5m3PHKHZN4PZt5xhfl4O79OtF/wCDx3/gl9qumRXt54V+IOnzvkSWl7oaF05PeKR1I6d+/SgD50H/AAZvaZBJ+5+Jlq0SrlkuJrh5O3OVVRnrxg12Oif8GfnwlvPD8Q8TeMjLcxD9y9kiwZGAMOm0FzxnJkB61734f/4O5v8AglVrTK09/wCK7dDnesmlKjr17Ssinp2bv+FeheGf+Dnn/gkP4pg26b8cdRS7Csf7Pn0Vlc4PQPu8ok8YAfv9cAHxuP8Agzu+CslzKy+L9VJkUeWZpNkMRAx0SRn56nO4emK8W/a+/wCDOD4zeGfh5e+Of2WfiRba1rVlayzHwrcybRebF+WOB2AIdj/fOMnHFfon4t/4Otv+CQPhCeazuvib4nu54QMxWHhl5cn0Db9uevfHvXyP+2Z/wehfDnTvCWseGv2J/gPe32t3Nm0Oj+I/FMojhsZiMec9uFPm7Sdyruw23DYzQB/Pd4p8MeIPBPibUPBvizSJtP1TSb2Wz1KxuU2yW88blJI2HZlYEH6VQq/4p8T69418Taj4x8U6lJe6nq19LeajeTH5555XLu59yzE/jVCgAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigD91P+DXL/gpD/wAE1P2evhdqfwV/aJtNK8IeNJNUN5b+KtaiMsVynlBSAwQ+UoC5yejSv0Xmv6C/BHxF+HXxA8MweMPAHjDS9V0q5A8i/wBPvEkifIBHzA4zgg+tfwQV3fw9/af/AGifhRZpp3w3+NfifRLeNNiwaZrU8C7f7vyMOOOnSgD+6G8+K/ww06Zra9+IeiRSJIUeOTVIlKsDgqQW4Oex5qvefG34RWEjw3PxI0ZXjXLxjUIyyjGckA8fWv4c779sH9qfUp5bm9/aC8WvJOpFw/8AbcwMwOc7yG+fOT97PWsu/wD2jPjtqdh/Zl58WNcNv3ijv2QH67SM/jQB/a38Qv8AgpF+wj8J4Jrn4jftVeDNIjt4vNlkutZQKExnIYZDdRnbnGR61/Pn/wAHPf8AwWv/AGUv+Citr4W/Zx/Ze8Krr1l4P1eS/ufiPcqY/MdlaNrS2jK7jGcK7SE4OAAOpr8kdc8deN/E9nFp/iXxjquo28BzBBfahLMkf+6rsQPwrKoAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAP/Z'
    },
    'timestamp': 1758350754119
}


def test_main_extraction():
    """Test the main extraction function"""
    print("=== Testing main extraction function ===")
    
    try:
        # Import the main extraction function
        from main import extract_plate_data
        
        # Test with our sample data
        result = extract_plate_data(SAMPLE_WEBHOOK_DATA)
        
        if result:
            print("✅ Successfully extracted license plate data!")
            print(f"Total plates found: {result['total_plates']}")
            
            for i, plate in enumerate(result['license_plates']):
                print(f"\nPlate {i+1}:")
                print(f"  Plate Number: {plate['plate_number']}")
                print(f"  Detection Type: {plate.get('detection_type', 'N/A')}")
                print(f"  Device ID: {plate.get('device_id', 'N/A')}")
                print(f"  Event ID: {plate.get('event_id', 'N/A')}")
                print(f"  Timestamp: {plate.get('timestamp', 'N/A')}")
                print(f"  Zones: {plate.get('zones', 'N/A')}")
                
        else:
            print("❌ No license plate data extracted")
            
    except Exception as e:
        print(f"❌ Error testing main extraction: {str(e)}")


def test_utility_extraction():
    """Test the utility extraction function"""
    print("\n=== Testing utility extraction function ===")
    
    try:
        # Import the utility extraction function
        from unifi_protect_client import extract_license_plate_from_webhook
        
        # Test with our sample data
        result = extract_license_plate_from_webhook(SAMPLE_WEBHOOK_DATA)
        
        if result:
            print("✅ Successfully extracted license plate data with utility function!")
            print(f"Primary Plate Number: {result['plate_number']}")
            print(f"Detection Type: {result.get('detection_type', 'N/A')}")
            print(f"Device ID: {result.get('device_id', 'N/A')}")
            print(f"Event ID: {result.get('event_id', 'N/A')}")
            print(f"Total plates found: {result.get('total_plates', 1)}")
            
            if 'all_plates' in result:
                print(f"\nAll plates:")
                for i, plate in enumerate(result['all_plates']):
                    print(f"  {i+1}. {plate['plate_number']} ({plate.get('detection_type', 'unknown')})")
                    
        else:
            print("❌ No license plate data extracted")
            
    except Exception as e:
        print(f"❌ Error testing utility extraction: {str(e)}")


def test_enrichment():
    """Test the enrichment function"""
    print("\n=== Testing enrichment function ===")
    
    try:
        # Import required functions
        from main import extract_plate_data, enrich_individual_plate_data
        
        # Extract plate data first
        plate_data = extract_plate_data(SAMPLE_WEBHOOK_DATA)
        
        if plate_data and plate_data['license_plates']:
            # Test enrichment with first plate
            first_plate = plate_data['license_plates'][0]
            enriched = enrich_individual_plate_data(first_plate, SAMPLE_WEBHOOK_DATA)
            
            print("✅ Successfully enriched license plate data!")
            print(f"Enriched fields:")
            for key, value in enriched.items():
                if key not in ['raw_detection', 'processing_timestamp', 'detection_timestamp']:  # Skip long/dynamic fields
                    print(f"  {key}: {value}")
                    
        else:
            print("❌ No plate data to enrich")
            
    except Exception as e:
        print(f"❌ Error testing enrichment: {str(e)}")


def main():
    """Run all tests"""
    print("🧪 Testing UniFi Protect License Plate Extraction")
    print("=" * 60)
    
    print(f"Sample webhook data contains:")
    print(f"  - Alarm name: {SAMPLE_WEBHOOK_DATA['alarm']['name']}")
    print(f"  - Triggers: {len(SAMPLE_WEBHOOK_DATA['alarm']['triggers'])}")
    print(f"  - Expected plate: {SAMPLE_WEBHOOK_DATA['alarm']['triggers'][0]['value']}")
    print()
    
    # Run tests
    test_main_extraction()
    test_utility_extraction() 
    test_enrichment()
    
    print("\n" + "=" * 60)
    print("✅ Testing completed!")


if __name__ == "__main__":
    main()
