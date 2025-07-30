def extract_availability(response_data):
    try:
        availability = response_data.get('data', [])[0].get('availability', [])
        for item in availability:
            item.pop('photos', None)
        return {'availability': availability}
    except Exception:
        return {'availability': []}