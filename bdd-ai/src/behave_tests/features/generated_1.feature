Feature:Service Health Check
  Scenario: Checking if the service is healthy
    When I send a GET request to "/health"
    Then the response status should be 200
    And the response should contain "status" equal to "ok"