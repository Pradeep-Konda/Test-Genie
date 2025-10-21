Feature:Create User

  Scenario: Create a new user with valid data
    Given I have user data:
      """
      {"name": "Charlie"}
      """
    When I send a POST request to "/users" with the provided data
    Then the response status code should be 201
    And the response body should be:
      """
      {"message": "User created", "user": {"name": "Charlie"}}
      """

  Scenario: Create a new user with missing or invalid data
    Given I have invalid or missing user data
    When I send a POST request to "/users" with null or malformed data
    Then the response status code should be 201
    And the response body should be:
      """
      {"message": "User created", "user": null}
      """