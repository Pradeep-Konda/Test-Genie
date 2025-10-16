from parser import parse_routes
from openapi_builder import build_openapi_spec
import yaml

def main():
    print("🔍 Scanning codebase...")
    routes = parse_routes(r"c:\Users\Pradeepkonda\Desktop\repos\test-genie\demo-flask-service")  # <- update path

    print("✅ Found routes:", routes)

    print("🛠 Building OpenAPI spec...")
    spec = build_openapi_spec(routes)

    print("💾 Writing to openapi.yaml")
    with open("openapi.yaml", "w") as f:
        yaml.dump(spec, f)

if __name__ == "__main__":
    main()
