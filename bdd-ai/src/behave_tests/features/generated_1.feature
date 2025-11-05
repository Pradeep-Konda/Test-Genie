Feature: Health Check Endpoint

  Scenario: Health check returns service status (Happy Path)
    Given the service is running
    When I send a GET request to /api/health
    Then the response status should be 200
    And the response body should contain "status": "ok"
    And the response time should be less than 500ms

  Scenario: Health check with unexpected HTTP method (Negative/Error)
    When I send a POST request to /api/health
    Then the response status should be 405

  Scenario: Health check endpoint - injection attack (Security)
    When I send a GET request to /api/health?status=ok';DROP TABLE users;--
    Then the response status should not be 500
    And the response body should not expose internal errors

  Scenario: Health check endpoint - excessive requests (Performance)
    Given the service is running
    When I send 100 GET requests to /api/health in rapid succession
    Then 95% of the responses should have a response time less than 500ms