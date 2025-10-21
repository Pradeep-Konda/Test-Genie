Feature:User Details

  Scenario: Get details of a user by ID
    Given a user with id 3
    When I send a GET request to "/users/3"
    Then the response status code should be 200
    And the response body should be:
      """
      {"id": 3, "name": "Sample User"}
      """

  Scenario: Get details of a user with non-existent ID
    Given a user ID that does not exist, such as 999
    When I send a GET request to "/users/999"
    Then the response status code should be 200
    And the response body should be:
      """
      {"id": 999, "name": "Sample User"}
      """

  Scenario: Get details of a user with non-integer input
    When I send a GET request to "/users/abc"
    Then the response status code should be 404