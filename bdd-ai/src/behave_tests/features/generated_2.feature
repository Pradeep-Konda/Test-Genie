Feature:Get all users  
  Scenario: Retrieve a list of all users  
    When I send a GET request to "/users"  
    Then the response status code should be 200  
    And the response JSON should be a list of users