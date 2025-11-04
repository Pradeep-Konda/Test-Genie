Feature:Create a New User
  Scenario: Creating a new user with valid data
    When I send a POST request to "/users" with request body:
      | name      |
      | John Doe  |
    Then the response status should be 201
    And the response should contain "message" equal to "User created"
    And the response should contain a "user" object with "name" equal to "John Doe"