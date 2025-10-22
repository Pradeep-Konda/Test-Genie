Feature:Create a new user

  Scenario: Create a new user
    When I send a POST request to "/users" with JSON body:
      """
      {
        "name": "Charlie"
      }
      """
    Then the response status code should be 201
    And the response JSON should include:
      | message       | User created |
    And the response JSON at "user" should echo the input JSON