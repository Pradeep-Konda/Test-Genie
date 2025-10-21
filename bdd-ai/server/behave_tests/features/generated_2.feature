Feature:Health Endpoint

  Scenario: Check health status
    When I send a GET request to "/health"
    Then the response status code should be 200
    And the response body should be:
      """
      {"status": "ok"}
      """