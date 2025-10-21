Feature:Users List

  Scenario: List all users
    When I send a GET request to "/users"
    Then the response status code should be 200
    And the response body should be:
      """
      [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"}
      ]
      """