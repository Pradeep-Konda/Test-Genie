Feature:Get user by ID  
  Scenario: Retrieve details of a user by ID  
    Given a user with id 1 exists  
    When I send a GET request to "/users/1"  
    Then the response status code should be 200  
    And the response JSON should contain "id" with value 1  
    And the response JSON should contain "name"