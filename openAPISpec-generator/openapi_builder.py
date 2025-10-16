def build_openapi_spec(routes):
    paths = {}

    for route in routes:
        path = route["path"]
        method = route["method"].lower()
        paths.setdefault(path, {})[method] = {
            "summary": route["summary"],
            "responses": {
                "200": {
                    "description": "Success"
                }
            }
        }

    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Generated API",
            "version": "1.0.0"
        },
        "paths": paths
    }

    return spec
