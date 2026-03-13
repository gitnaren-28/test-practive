def lambda_handler(event, context):
    try:
        results = []
        for item in event.get("findings"):
            if not isinstance(item, dict):
                continue

            payload = item.get("Payload") if "Payload" in item else item
            if not isinstance(payload, dict):
                continue

            finding_type = payload.pop("finding_type", None)
            if not finding_type:
                continue

            results.append({
                finding_type: payload
            })

        return results
        
    except Exception as e:
        raise Exception(f"Lambda failed: {e}")