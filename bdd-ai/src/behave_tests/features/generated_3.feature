Feature:Create a new user  
  Scenario: Successfully create a new user  
    Given the request body is  
      | name      |  
      | John Doe  |  
    When I send a POST request to "/users"  
    Then the response status code should be 201  
    And the response JSON should contain "message" with value "User created"  
    And the response JSON should contain "user" with "name" equal to "John Doe"