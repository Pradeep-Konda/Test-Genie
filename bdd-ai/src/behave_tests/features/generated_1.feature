Feature:Health check endpoint  
  Scenario: Check if the service is healthy  
    When I send a GET request to "/health"  
    Then the response status code should be 200  
    And the response JSON should contain "status" with value "ok"